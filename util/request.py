"""
抓取 arXiv 最近论文列表，并在本地做轻量过滤（不依赖 LLM）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


def get_yesterday_arxiv_papers(category: str = "cs.CV", max_results: int = 100):
    url = f"https://arxiv.org/list/{category}/new?skip=0&show={max_results}"

    response = requests.get(url)

    soup = BeautifulSoup(response.text, "html.parser")

    try:
        entries = soup.find_all("dl", id="articles")[0].find_all(["dt", "dd"])
    except Exception as e:
        return []

    papers = []
    for i in range(0, len(entries), 2):
        title_tag = entries[i + 1].find("div", class_="list-title")
        title = (
            title_tag.text.strip().replace("Title:", "").strip()
            if title_tag
            else "No title available"
        )

        abs_url = "https://arxiv.org" + entries[i].find("a", title="Abstract")["href"]

        pdf_url = entries[i].find("a", title="Download PDF")["href"]
        pdf_url = "https://arxiv.org" + pdf_url

        abstract_tag = entries[i + 1].find("p", class_="mathjax")
        abstract = (
            abstract_tag.text.strip() if abstract_tag else "No abstract available"
        )

        comments_tag = entries[i + 1].find("div", class_="list-comments")
        comments = (
            comments_tag.text.strip() if comments_tag else "No comments available"
        )

        paper_info = {
            "title": title,
            "arXiv_id": pdf_url.split("/")[-1],
            "abstract": abstract,
            "comments": comments,
            "pdf_url": pdf_url,
            "abstract_url": abs_url,
        }

        papers.append(paper_info)

    return papers


def get_recent_arxiv_papers(
    category: str = "cs.CV",
    max_results: int = 100,
    lookback_hours: int = 24,
    *,
    now_utc: datetime | None = None,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    include_mode: str = "any",
):
    """
    使用 arXiv Atom API 拉取最近论文（按 submittedDate 倒序），并筛选出过去 lookback_hours 小时内的条目。

    说明：
    - 过去 24 小时的判断以 UTC 时间为准（arXiv API 的 published/updated 通常为 UTC）。
    - include/exclude 关键词匹配为大小写不敏感，匹配范围：title + abstract + comments（如有）。
    - include_mode：
      - "any"：命中任一 include 关键词即可保留
      - "all"：必须命中全部 include 关键词才保留
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    if lookback_hours <= 0:
        raise ValueError("lookback_hours 必须为正整数")

    include_mode = include_mode.lower().strip()
    if include_mode not in ("any", "all"):
        raise ValueError("include_mode 仅支持 'any' 或 'all'")

    threshold = now_utc - timedelta(hours=lookback_hours)

    params = {
        "search_query": f"cat:{category}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    headers = {
        "User-Agent": "customize-arxiv-daily (https://github.com; contact: local)",
    }
    resp = requests.get(
        "https://export.arxiv.org/api/query",
        params=params,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(resp.text)
    entries = root.findall("atom:entry", ns)

    include_keywords_norm = [k.casefold().strip() for k in (include_keywords or []) if k.strip()]
    exclude_keywords_norm = [k.casefold().strip() for k in (exclude_keywords or []) if k.strip()]

    def _match_include(text: str) -> bool:
        if not include_keywords_norm:
            return True
        if include_mode == "all":
            return all(k in text for k in include_keywords_norm)
        return any(k in text for k in include_keywords_norm)

    def _match_exclude(text: str) -> bool:
        if not exclude_keywords_norm:
            return False
        return any(k in text for k in exclude_keywords_norm)

    papers: list[dict] = []
    for entry in entries:
        published_text = entry.findtext("atom:published", default="", namespaces=ns).strip()
        if not published_text:
            continue
        # 例：2026-01-05T08:12:34Z
        published = datetime.fromisoformat(published_text.replace("Z", "+00:00"))
        if published < threshold:
            break

        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        title = " ".join(title.split())
        abstract = entry.findtext("atom:summary", default="", namespaces=ns).strip()
        abstract = " ".join(abstract.split())
        abs_url = entry.findtext("atom:id", default="", namespaces=ns).strip()

        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            link_type = (link.get("type") or "").strip()
            link_title = (link.get("title") or "").strip().lower()
            if link_type == "application/pdf" or link_title == "pdf":
                pdf_url = link.get("href") or ""
                break

        comments = entry.findtext("arxiv:comment", default="", namespaces=ns).strip()
        arxiv_id = abs_url.rsplit("/", 1)[-1] if abs_url else ""

        haystack = "\n".join([title, abstract, comments]).casefold()
        if not _match_include(haystack):
            continue
        if _match_exclude(haystack):
            continue

        papers.append(
            {
                "title": title or "No title available",
                "arXiv_id": arxiv_id,
                "abstract": abstract or "No abstract available",
                "comments": comments or "No comments available",
                "pdf_url": pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""),
                "abstract_url": abs_url or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
                "published_utc": published.isoformat(),
            }
        )

    return papers


if __name__ == "__main__":
    papers = get_yesterday_arxiv_papers()
    print(len(papers))
