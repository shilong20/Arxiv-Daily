<h3 align="center">Customize-arXiv-Daily</h3>

---

<p align="center"> Recommend new arxiv papers of your interest daily according to your customized description.
    <br> 
</p>

> [!NOTE]
> This repo borrow the idea and some functions from [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily). Thanks for their great work!😊

## 🧐 Why I create this project <a name = "about"></a>

- During the use of [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily), I often find that the recommendation process didn't run in the way that I want. Since my study area has shifted, my Zotero include some papers that I'm not interested in anymore.
- For those who **do not use zotero as PDF reader**, get customized arxiv recommendation is still needed.
- For those that want to **set their own prompt** to guide LLM during paper selection and recommendation.

## ✨ Key Features Compared with [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily)

- Fully customized LLM prompt to guide your paper recommendation process.
- Ready-to-use leverage of recent models, include DeepSeek-R1/V3/...
- Save your arXiv recommendation history.
- Batch LLM scoring + rerank Top-M to reduce ties and stabilize ranking.
- Fixed Top-5 recommendations at the start of the email.
- Support multiple workers to speed up the recommendation process.

## 📷 Screenshot

![screenshot](./assets/screenshot.png)

## 🚀 Usage

### Quick Start

1. Run `git clone https://github.com/JoeLeelyf/customize-arxiv-daily.git`
2. Run `pip install -r requirements.txt` to install necessary packages.
   If you prefer using [`uv`](https://github.com/astral-sh/uv) for dependency management, run:

   ```bash
   uv sync
   ```

   This will create the virtual environment described by `pyproject.toml` and `uv.lock`.
3. Get your STMP server. Common STMP service provider includes [QQ mail box](https://service.mail.qq.com/detail/0/427)
4. Describe the research fields you're interested in, and the fields you're not. Edit the `description.txt`. For, example:

```txt
I am working on the research area of computer vision.
Specifically, I am interested in the following fieds:
1. Object detection
2. AIGC (AI Generated Content)
3. Multimodal Large Language Models

I'm not interested in the following fields:
1. 3D Vision
2. Robotics
3. Low-level Vision
```

5. Configure your own `arXiv catergories`, `api_key` and `models`. The repo supports **OpenAI-compatible** Chat Completions endpoints (including third-party services that expose the OpenAI API format). Meaning of different parameters:
   - `--categories`: arXiv categories that you are interested in, like `cs.CV` `cs.AI`
   - `--sender`: E-mail address that provide SMTP service, like, `123456@qq.com`
   - `--receiver`: The e-mails address that you want to receive your notice, like, `my_gmail@gmail.com`
   - `--save`: store_true, whether to save the arXiv results to local markdown files.

- `main_gpt.sh`: Example runner for OpenAI-compatible APIs (supports model failover list and endpoint failover list).

```bash
python main.py --categories cs.CV cs.AI \
    --model gpt-4o-mini \
    --base_url https://api.openai.com/v1 --api_key * \
    --smtp_server smtp.qq.com --smtp_port 465 \
    --sender * --receiver * \
    --sender_password * \
    --num_workers 16 \
    --lookback_hours 24 \
    --llm_batch_size 5 \
    --rerank_top_m 30 \
    --title "Daily arXiv" \
    --temperature 0.7 \
    --save
```

6. Choose to run one of the following command in your CLI.

```
bash main_gpt.sh
```


### Run with uv

After syncing dependencies you can execute the CLI through `uv run` (it will reuse the managed environment):

```bash
uv run python main.py --categories cs.CV cs.AI \
    --model gpt-4o-mini \
    --base_url https://api.openai.com/v1 --api_key * \
    --smtp_server smtp.qq.com --smtp_port 465 \
    --sender * --receiver * \
    --sender_password * \
    --num_workers 16 \
    --lookback_hours 24 \
    --llm_batch_size 5 \
    --rerank_top_m 30 \
    --title "Daily arXiv" \
    --temperature 0.7 \
    --save
```

7. \* **Run automatically everyday (GitHub Actions recommended).**

This repo is designed to run daily with a **longer window** (e.g. last 4 days) + a persistent `seen_ids` database to avoid re-processing/re-emailing papers:

- Window: `--lookback_hours 96` (covers weekend backlog)
- Seen DB: `--seen_db state/seen_ids.json --seen_retention_days 30 --seen_scope base`

Create GitHub Secrets:
- `MODELSCOPE_API_KEY` (or your OpenAI-compatible API key)
- `SMTP_SENDER`, `SMTP_RECEIVER`, `SMTP_PASSWORD`

Then enable the workflow file: `.github/workflows/daily.yml` (it runs `bash main_gpt.sh` and commits the updated `state/seen_ids.json` back to the repo).

8. \* **Adjust and customize your LLM prompt.** Edit `_build_batch_prompt(...)` / `_build_rerank_prompt(...)` in `arxiv_daily.py`.

## Results

### Running process in your CLI

![CLI](./assets/cli.png)

### Markdown saved

![Markdown](./assets/markdown.png)

### E-mail received

![Screenshot](./assets/screenshot.png)

## 📖 How it works

- `util/request.py` fetches recent arXiv papers given your provided arXiv categories (via arXiv Atom API), and keeps only papers within the last 24 hours by default.
- `arxiv_daily` will call LLM api to summarize every paper and get the relevance score.
- `util/construct_email.py` construct the content of the email in HTML form and send it using SMTP service.

## 🔧 与“获取论文/筛选论文”密切相关的超参数

下面这些参数会直接影响**抓取到的候选论文列表**以及 **LLM 的筛选/排序结果**（也会影响运行时间与成本）：

### 获取论文列表（抓取侧）

- `--categories`：要抓取的 arXiv 分类（例如 `cs.CV cs.AI`）。脚本会对每个分类拉取最近条目，然后合并去重。
- `--max_entries`：每个分类拉取的最大条目数（按提交时间倒序）。越大表示候选越多、LLM 调用越多。
- `--lookback_hours`：仅保留过去 N 小时内的新论文（默认 `24`）。建议配合“每天运行 1 次”使用，避免重复筛同一批论文。
- `--description`：研究兴趣描述文件路径（默认 `description.txt`）。该内容会进入提示词，直接影响 LLM 相关性判断。
- `--include_keywords`：关键词包含过滤（大小写不敏感）。用于在进入 LLM 前先缩小候选集。
- `--exclude_keywords`：关键词排除过滤（大小写不敏感）。命中任一关键词则剔除。
- `--include_mode`：`include_keywords` 的命中规则：`any`（命中任一）/ `all`（必须命中全部）。

### 筛选/排序（LLM 侧）

- `--max_paper_num`：最终保留并输出的 Top-N 论文数（按 `relevance_score` 降序截断）。注意：**这不会减少 LLM 调用次数**，它只决定最终输出数量。
- `--llm_batch_size`：LLM 批处理大小（默认 `5`）。每次调用会同时处理 N 篇论文，可减少请求次数并提升评分稳定性。
- `--num_workers`：并发 worker 数（线程池）。越大越快，但更容易触发 API 限流/本地模型资源不足。
- `--temperature`：LLM 采样温度。越高输出越“发散”，相关性评分与摘要稳定性越差；越低更稳定但可能更“保守”。
- `--weight_topic/--weight_method/--weight_novelty/--weight_impact`：多维度评分的加权系数（总分由四项加权得到，默认 `0.45/0.25/0.15/0.15`）。
- `--rerank_top_m`：最终对 Top-M 候选做一次“全局比较式重排”（默认 `30`，输入为 title+abstract）。用于减少同分与纠偏；设为 `0` 可关闭。
- `--base_url/--api_key/--model`：支持传入多个值（空格分隔）。当一次请求报错时会按列表顺序自动切换到下一个（可组成 base_url+api_key+model 的三元组列表；当 model 为列表时，会优先按三元组顺序切换）。
- `--seen_db/--seen_retention_days/--seen_scope`：长窗口模式下的“已处理论文 ID”去重机制。推荐 `--lookback_hours 96` + `--seen_retention_days 30` 覆盖周末堆积，同时避免重复处理/重复发邮件。

### 运行机制补充（便于理解上述参数的影响）

- **合并去重**：多分类抓取结果会按 `arXiv_id` 去重后再进入 LLM 阶段。
- **每日固定推荐**：邮件开头固定展示评分最高的前 5 篇论文（降序）。
- **缓存（开启 `--save` 时）**：每篇论文的 LLM 结果会缓存到 `arxiv_history/<date>/json/<arXiv_id>.json`，重复运行同一天通常会复用缓存，显著减少 LLM 调用。

## 📌 Limitations

- The recommendation process of LLM is unstable and the relevance score provided by different LLMs varies a lot.
