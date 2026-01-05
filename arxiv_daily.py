from llm import *
from util.request import get_recent_arxiv_papers
from util.construct_email import *
from tqdm import tqdm
import json
import os
from datetime import datetime, timezone
import time
import random
import smtplib
from email.header import Header
from email.utils import parseaddr, formataddr
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from loguru import logger


class ArxivDaily:
    def __init__(
        self,
        categories: list[str],
        max_entries: int,
        max_paper_num: int,
        lookback_hours: int,
        include_keywords: list[str] | None,
        exclude_keywords: list[str] | None,
        include_mode: str,
        llm_batch_size: int,
        weight_topic: float,
        weight_method: float,
        weight_novelty: float,
        weight_impact: float,
        rerank_top_m: int,
        model: str,
        base_url: None,
        api_key: None,
        description: str,
        num_workers: int,
        temperature: float,
        save_dir: None,
    ):
        self.model_name = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_paper_num = max_paper_num
        self.save_dir = save_dir
        self.num_workers = num_workers
        self.temperature = temperature
        self.run_datetime = datetime.now(timezone.utc)
        self.run_date = self.run_datetime.strftime("%Y-%m-%d")
        self.lookback_hours = lookback_hours
        self.include_keywords = include_keywords
        self.exclude_keywords = exclude_keywords
        self.include_mode = include_mode
        self.llm_batch_size = max(1, int(llm_batch_size))
        self.score_weights = {
            "topic": float(weight_topic),
            "method": float(weight_method),
            "novelty": float(weight_novelty),
            "impact": float(weight_impact),
        }
        self.rerank_top_m = max(0, int(rerank_top_m))
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = None
        if save_dir:
            self.cache_dir = os.path.join(base_dir, save_dir, self.run_date, "json")
            os.makedirs(self.cache_dir, exist_ok=True)
        self.papers = {}
        for category in categories:
            self.papers[category] = get_recent_arxiv_papers(
                category=category,
                max_results=max_entries,
                lookback_hours=self.lookback_hours,
                now_utc=self.run_datetime,
                include_keywords=self.include_keywords,
                exclude_keywords=self.exclude_keywords,
                include_mode=self.include_mode,
            )
            print(
                "{} papers on arXiv for {} are fetched.".format(
                    len(self.papers[category]), category
                )
            )
            # avoid being blocked
            sleep_time = random.randint(5, 15)
            time.sleep(sleep_time)

        self.model = GPT(model, base_url, api_key)
        print(f"Model initialized successfully. Using {model}.")

        self.description = description
        self.lock = threading.Lock()  # 添加线程锁

    def _clean_model_response(self, raw_text: str) -> str:
        cleaned = (raw_text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if "\n" in cleaned:
                first_line, rest = cleaned.split("\n", 1)
                if first_line.strip().lower() in ("json", "html"):
                    cleaned = rest
                else:
                    cleaned = first_line + "\n" + rest
        return cleaned.strip()

    def _compute_weighted_score(self, scores: dict) -> float:
        w = self.score_weights
        total_w = w["topic"] + w["method"] + w["novelty"] + w["impact"]
        if total_w <= 0:
            total_w = 1.0
        topic = float(scores.get("topic", 0))
        method = float(scores.get("method", 0))
        novelty = float(scores.get("novelty", 0))
        impact = float(scores.get("impact", 0))
        weighted = (
            w["topic"] * topic
            + w["method"] * method
            + w["novelty"] * novelty
            + w["impact"] * impact
        ) / total_w
        return max(0.0, min(10.0, weighted))

    @staticmethod
    def _label_from_score(score: float) -> str:
        if score >= 8:
            return "高度相关"
        if score >= 6:
            return "相关"
        if score >= 4:
            return "一般相关"
        return "不太相关"

    def _build_batch_prompt(self, papers: list[dict]) -> str:
        weights = self.score_weights
        weights_text = (
            f"topic={weights['topic']}, method={weights['method']}, "
            f"novelty={weights['novelty']}, impact={weights['impact']}"
        )
        items = []
        for p in papers:
            items.append(
                {
                    "arXiv_id": p.get("arXiv_id"),
                    "title": p.get("title"),
                    "abstract": p.get("abstract"),
                }
            )
        payload = json.dumps(items, ensure_ascii=False, indent=2)

        return f"""
你是一名严谨的学术研究助手。请只基于我提供的“研究兴趣描述”和每篇论文的“标题/摘要”进行判断，不要臆测论文未提供的实验细节或结论。

研究兴趣描述（包含感兴趣与不感兴趣方向）：
{self.description}

请对下面每篇论文输出（每篇都要输出）：
1) summary：用中文写 2-4 句摘要（<=120 字）。
2) scores：给出 4 个维度的 0-10 整数评分（越高越好）：
   - topic：主题/任务与我的研究兴趣匹配程度
   - method：方法/技术路线与我的研究兴趣匹配程度
   - novelty：新颖性/独特性（只基于摘要可判断的部分）
   - impact：潜在影响/可用性（对我后续研究的帮助）
3) recommend_reason：一句话推荐理由（中文）。
4) key_contribution：一句话关键贡献（中文）。

最终总分由程序按加权评分计算（你不需要计算总分）。权重为：{weights_text}。

输出要求（非常重要）：
- 只输出一个 JSON 数组（不要 Markdown、不要代码块、不要多余文字）。
- 数组长度必须与输入论文数一致；每个元素必须包含 arXiv_id 且与输入完全一致。
- scores.topic / scores.method / scores.novelty / scores.impact 必须为 0-10 的整数。
- 每个元素必须严格包含如下字段：
  {{
    "arXiv_id": "...",
    "summary": "...",
    "scores": {{"topic": 0, "method": 0, "novelty": 0, "impact": 0}},
    "recommend_reason": "...",
    "key_contribution": "..."
  }}

输入论文 JSON 数组如下：
{payload}

请直接输出 JSON 数组。
""".strip()

    def _load_cache(self, paper: dict) -> dict | None:
        if not self.cache_dir:
            return None
        cache_path = os.path.join(self.cache_dir, f"{paper['arXiv_id']}.json")
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as cache_file:
                return json.load(cache_file)
        except (json.JSONDecodeError, OSError) as e:
            print(f"缓存文件 {cache_path} 读取失败: {e}，将重新获取。")
            return None

    def _write_cache(self, result: dict) -> None:
        if not self.cache_dir:
            return
        cache_path = os.path.join(self.cache_dir, f"{result['arXiv_id']}.json")
        try:
            with self.lock:
                with open(cache_path, "w", encoding="utf-8") as cache_file:
                    json.dump(result, cache_file, ensure_ascii=False, indent=2)
        except OSError as write_error:
            print(f"写入缓存 {cache_path} 时失败: {write_error}")

    def process_paper_batch(self, papers: list[dict], max_retries: int = 3) -> list[dict]:
        for attempt in range(1, max_retries + 1):
            try:
                prompt = self._build_batch_prompt(papers)
                raw = self.model.inference(prompt, temperature=self.temperature)
                cleaned = self._clean_model_response(raw)
                data = json.loads(cleaned)
                if not isinstance(data, list) or len(data) != len(papers):
                    raise ValueError("LLM 输出不是等长 JSON 数组")

                results_by_id: dict[str, dict] = {}
                for item in data:
                    if not isinstance(item, dict):
                        raise ValueError("LLM 输出数组元素不是对象")
                    arxiv_id = item.get("arXiv_id")
                    if not arxiv_id or not isinstance(arxiv_id, str):
                        raise ValueError("LLM 输出缺少 arXiv_id")
                    scores = item.get("scores", {})
                    if not isinstance(scores, dict):
                        raise ValueError("scores 字段不是对象")
                    parsed_scores = {
                        "topic": int(scores.get("topic", 0)),
                        "method": int(scores.get("method", 0)),
                        "novelty": int(scores.get("novelty", 0)),
                        "impact": int(scores.get("impact", 0)),
                    }
                    for k, v in parsed_scores.items():
                        if v < 0 or v > 10:
                            raise ValueError(f"{k} 评分超出范围")
                    results_by_id[arxiv_id] = {
                        "summary": str(item.get("summary", "")).strip(),
                        "scores": parsed_scores,
                        "recommend_reason": str(item.get("recommend_reason", "")).strip(),
                        "key_contribution": str(item.get("key_contribution", "")).strip(),
                    }

                results: list[dict] = []
                for paper in papers:
                    arxiv_id = paper["arXiv_id"]
                    if arxiv_id not in results_by_id:
                        raise ValueError(f"LLM 输出缺少论文 {arxiv_id}")
                    r = results_by_id[arxiv_id]
                    score = self._compute_weighted_score(r["scores"])
                    result = {
                        "title": paper.get("title", ""),
                        "arXiv_id": arxiv_id,
                        "abstract": paper.get("abstract", ""),
                        "summary": r["summary"],
                        "relevance_score": score,
                        "relevance_label": self._label_from_score(score),
                        "recommend_reason": r["recommend_reason"] or "未提供推荐理由",
                        "key_contribution": r["key_contribution"] or "未提供关键贡献",
                        "pdf_url": paper.get("pdf_url", ""),
                        "scores": r["scores"],
                    }
                    self._write_cache(result)
                    results.append(result)
                return results
            except Exception as e:
                print(f"批处理 LLM 推理第 {attempt} 次失败: {e}")
                if attempt == max_retries:
                    return []
                time.sleep(1)

    def _build_rerank_prompt(self, papers: list[dict]) -> str:
        items = []
        for p in papers:
            items.append(
                {
                    "arXiv_id": p.get("arXiv_id"),
                    "title": p.get("title"),
                    "abstract": p.get("abstract"),
                }
            )
        payload = json.dumps(items, ensure_ascii=False, indent=2)
        return f"""
你是一名严谨的学术研究助手。请只基于我提供的“研究兴趣描述”和每篇论文的“标题/摘要”进行判断，不要臆测论文未提供的实验细节或结论。

研究兴趣描述（包含感兴趣与不感兴趣方向）：
{self.description}

任务：请对下面这批论文做“全局比较式”的最终排序（从最值得我优先阅读到最不值得），并给出更细粒度的最终分数用于区分同分与纠偏。

输出要求（非常重要）：
- 只输出一个 JSON 数组（不要 Markdown、不要代码块、不要多余文字）。
- 数组必须覆盖输入中的全部论文，且每篇论文只出现一次。
- 每个元素必须严格包含如下字段：
  {{
    "arXiv_id": "...",
    "score_100": 0,
    "reason": "..."
  }}
- score_100 为 0-100 的整数，越高越优先；请尽量避免大量相同分数（必要时可使用相邻分数）。
- reason 用中文一句话说明排序原因（<=40 字）。

输入论文 JSON 数组如下：
{payload}

请直接输出 JSON 数组。
""".strip()

    def rerank_top_papers(self, papers: list[dict], max_retries: int = 2) -> list[dict]:
        if len(papers) <= 1:
            return papers
        for attempt in range(1, max_retries + 1):
            try:
                prompt = self._build_rerank_prompt(papers)
                raw = self.model.inference(prompt, temperature=self.temperature)
                cleaned = self._clean_model_response(raw)
                data = json.loads(cleaned)
                if not isinstance(data, list) or len(data) != len(papers):
                    raise ValueError("重排输出不是等长 JSON 数组")

                expected_ids = [p.get("arXiv_id") for p in papers]
                expected_set = set(expected_ids)
                if None in expected_set:
                    raise ValueError("输入论文缺少 arXiv_id")

                seen: set[str] = set()
                ranked: list[dict] = []
                for item in data:
                    if not isinstance(item, dict):
                        raise ValueError("重排数组元素不是对象")
                    arxiv_id = item.get("arXiv_id")
                    if not arxiv_id or not isinstance(arxiv_id, str):
                        raise ValueError("重排输出缺少 arXiv_id")
                    if arxiv_id in seen:
                        raise ValueError("重排输出存在重复 arXiv_id")
                    if arxiv_id not in expected_set:
                        raise ValueError(f"重排输出包含未知论文 {arxiv_id}")
                    score_100 = int(item.get("score_100", 0))
                    if score_100 < 0 or score_100 > 100:
                        raise ValueError("score_100 超出范围")
                    reason = str(item.get("reason", "")).strip()
                    seen.add(arxiv_id)
                    ranked.append(
                        {
                            "arXiv_id": arxiv_id,
                            "score_100": score_100,
                            "reason": reason,
                        }
                    )

                if seen != expected_set:
                    missing = expected_set - seen
                    raise ValueError(f"重排输出缺少论文：{sorted(missing)}")

                by_id = {p["arXiv_id"]: p for p in papers}
                out: list[dict] = []
                for idx, r in enumerate(ranked, start=1):
                    p = by_id[r["arXiv_id"]]
                    p["rerank_score_100"] = r["score_100"]
                    p["rerank_reason"] = r["reason"]
                    p["rerank_rank"] = idx
                    # 统一使用 0-10 的 relevance_score 继续后续排序/展示
                    p["relevance_score"] = float(r["score_100"]) / 10.0
                    out.append(p)
                return out
            except Exception as e:
                print(f"Top-M 重排第 {attempt} 次失败: {e}")
                if attempt == max_retries:
                    return papers
                time.sleep(1)

    def get_recommendation(self):
        recommendations = {}
        for category, papers in self.papers.items():
            for paper in papers:
                recommendations[paper["arXiv_id"]] = paper

        print(
            f"Got {len(recommendations)} non-overlapping papers from recent arXiv."
        )

        cached_results: list[dict] = []
        pending: list[dict] = []
        for paper in recommendations.values():
            cached = self._load_cache(paper)
            if cached:
                cached_results.append(cached)
            else:
                pending.append(paper)

        recommendations_: list[dict] = []
        recommendations_.extend(cached_results)
        print("Performing LLM inference...")

        with ThreadPoolExecutor(self.num_workers) as executor:
            futures = []
            batch_size = self.llm_batch_size
            for i in range(0, len(pending), batch_size):
                batch = pending[i : i + batch_size]
                futures.append(executor.submit(self.process_paper_batch, batch))
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Processing batches",
                unit="batch",
            ):
                batch_results = future.result()
                if batch_results:
                    recommendations_.extend(batch_results)

        recommendations_ = sorted(
            recommendations_, key=lambda x: x.get("relevance_score", 0), reverse=True
        )[: self.max_paper_num]

        # Top-M 全局重排（用于减少同分与纠偏）
        if self.rerank_top_m > 0 and len(recommendations_) > 1:
            for p in recommendations_:
                if "base_relevance_score" not in p:
                    p["base_relevance_score"] = p.get("relevance_score", 0)
            m = min(self.rerank_top_m, len(recommendations_))
            top = recommendations_[:m]
            tail = recommendations_[m:]
            reranked_top = self.rerank_top_papers(top)
            recommendations_ = reranked_top + tail
            recommendations_ = sorted(
                recommendations_, key=lambda x: x.get("relevance_score", 0), reverse=True
            )[: self.max_paper_num]

        # Save recommendation to markdown file
        if self.save_dir:
            current_time = self.run_datetime
            save_path = os.path.join(
                self.save_dir, self.run_date, f"{current_time.strftime('%Y-%m-%d')}.md"
            )
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("# Daily arXiv Papers\n")
                f.write(f"## Date: {current_time.strftime('%Y-%m-%d')}\n")
                f.write(f"## Description: {self.description}\n")
                f.write("## Papers:\n")
                for i, paper in enumerate(recommendations_):
                    f.write(f"### {i + 1}. {paper.get('title','')}\n")
                    f.write("#### Abstract:\n")
                    f.write(f"{paper.get('abstract','')}\n")
                    f.write("#### Summary:\n")
                    f.write(f"{paper.get('summary','')}\n")
                    f.write(f"#### Relevance Score: {paper.get('relevance_score',0)}\n")
                    f.write(f"#### PDF URL: {paper.get('pdf_url','')}\n")
                    f.write("\n")

        return recommendations_

    def summarize(self, recommendations):
        recommendations = sorted(
            recommendations, key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        top_k = 5
        top = recommendations[:top_k]

        weights = self.score_weights
        weight_note = (
            "总分=加权评分（topic/method/novelty/impact），权重："
            f"topic={weights['topic']}, method={weights['method']}, "
            f"novelty={weights['novelty']}, impact={weights['impact']}。"
        )
        summary_data = {
            "recommendations": [
                {
                    "title": p.get("title", ""),
                    "relevance_label": p.get("relevance_label")
                    or self._label_from_score(float(p.get("relevance_score", 0))),
                    "recommend_reason": p.get("recommend_reason", "未提供推荐理由"),
                    "key_contribution": p.get("key_contribution", "未提供关键贡献"),
                }
                for p in top
            ],
            "additional_observation": f"每日固定展示评分最高的前 {min(top_k, len(recommendations))} 篇论文；{weight_note}",
        }
        return render_summary_sections(summary_data)

    def render_email(self, recommendations):
        if self.save_dir:
            save_file_path = os.path.join(
                self.save_dir, self.run_date, "arxiv_daily_email.html"
            )
            if os.path.exists(save_file_path):
                with open(save_file_path, "r", encoding="utf-8") as f:
                    print(f"邮件已渲染，从缓存文件 {save_file_path} 读取邮件。")
                    return f.read()
        parts = []
        if len(recommendations) == 0:
            return framework.replace("__CONTENT__", get_empty_html())
        recommendations = sorted(
            recommendations, key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        for i, p in enumerate(tqdm(recommendations, desc="Rendering Emails")):
            score = float(p.get("relevance_score", 0))
            rate = get_stars(score)
            parts.append(
                get_block_html(
                    str(i + 1) + ". " + p.get("title", ""),
                    rate,
                    p.get("arXiv_id", ""),
                    p.get("summary", ""),
                    p.get("pdf_url", ""),
                )
            )
        summary = self.summarize(recommendations)
        # Add the summary to the start of the email
        content = summary
        content += "<br>" + "</br><br>".join(parts) + "</br>"
        email_html = framework.replace("__CONTENT__", content)
        # 保存渲染后的邮件到 save_dir
        if self.save_dir:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_path = os.path.join(base_dir, self.save_dir, self.run_date, "arxiv_daily_email.html")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(email_html)
        return email_html

    def send_email(
        self,
        sender: str,
        receiver: str,
        password: str,
        smtp_server: str,
        smtp_port: int,
        title: str,
    ):
        recommendations = self.get_recommendation()
        html = self.render_email(recommendations)

        def _format_addr(s):
            name, addr = parseaddr(s)
            return formataddr((Header(name, "utf-8").encode(), addr))

        msg = MIMEText(html, "html", "utf-8")
        msg["From"] = _format_addr(f"{title} <%s>" % sender)

        # 处理多个接收者
        receivers = [addr.strip() for addr in receiver.split(",")]
        print(receivers)
        msg["To"] = ",".join([_format_addr(f"You <%s>" % addr) for addr in receivers])

        today = self.run_datetime.strftime("%Y/%m/%d")
        msg["Subject"] = Header(f"{title} {today}", "utf-8").encode()

        try:
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
        except Exception as e:
            logger.warning(f"Failed to initialize SMTP connection. {e}")
            raise

        server.login(sender, password)
        server.sendmail(sender, receivers, msg.as_string())
        server.quit()


if __name__ == "__main__":
    categories = ["cs.CV"]
    max_entries = 100
    max_paper_num = 50
    lookback_hours = 24
    include_keywords = None
    exclude_keywords = None
    include_mode = "any"
    llm_batch_size = 5
    weight_topic = 0.45
    weight_method = 0.25
    weight_novelty = 0.15
    weight_impact = 0.15
    model = "gpt-4o-mini"
    base_url = ["https://api.openai.com/v1"]
    api_key = ["*"]
    description = """
        I am working on the research area of computer vision and natural language processing. 
        Specifically, I am interested in the following fieds:
        1. Object detection
        2. AIGC (AI Generated Content)
        3. Multimodal Large Language Models

        I'm not interested in the following fields:
        1. 3D Vision
        2. Robotics
        3. Low-level Vision
    """

    arxiv_daily = ArxivDaily(
        categories,
        max_entries,
        max_paper_num,
        lookback_hours,
        include_keywords,
        exclude_keywords,
        include_mode,
        llm_batch_size,
        weight_topic,
        weight_method,
        weight_novelty,
        weight_impact,
        30,
        model,
        base_url,
        api_key,
        description,
        4,
        0.7,
        "./arxiv_history",
    )
    recommendations = arxiv_daily.get_recommendation()
    print(recommendations)
