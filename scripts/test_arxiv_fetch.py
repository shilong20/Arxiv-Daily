import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from util.request import get_recent_arxiv_papers  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查点：仅测试 arXiv 抓取（不做关键词过滤、不调用 LLM）。"
    )
    parser.add_argument("--categories", nargs="+", required=True, help="例如 cs.CV cs.AI")
    parser.add_argument("--max_entries", type=int, default=50, help="每个分类最多拉取条目数")
    parser.add_argument(
        "--lookback_hours",
        type=int,
        default=24,
        help="仅保留过去 N 小时内的新论文（默认 24）",
    )
    parser.add_argument("--show", type=int, default=5, help="每个分类展示前 N 条标题（默认 5）")
    args = parser.parse_args()

    now_utc = datetime.now(timezone.utc)
    print(f"UTC 当前时间：{now_utc.isoformat()}")

    total = 0
    for category in args.categories:
        print(f"\n=== 分类 {category} ===")
        try:
            papers = get_recent_arxiv_papers(
                category=category,
                max_results=args.max_entries,
                lookback_hours=args.lookback_hours,
                now_utc=now_utc,
                include_keywords=None,
                exclude_keywords=None,
                include_mode="any",
            )
        except Exception as e:
            print(f"抓取失败：{e}")
            continue

        total += len(papers)
        print(f"抓取到 {len(papers)} 篇（过去 {args.lookback_hours} 小时内）")
        for i, p in enumerate(papers[: args.show], start=1):
            published = p.get("published_utc", "")
            arxiv_id = p.get("arXiv_id", "")
            title = p.get("title", "")
            print(f"{i}. [{arxiv_id}] {published} {title}")

    print(f"\n总计抓取到 {total} 篇（跨 {len(args.categories)} 个分类）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

