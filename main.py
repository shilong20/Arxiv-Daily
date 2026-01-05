from util.construct_email import send_email
from arxiv_daily import ArxivDaily
import argparse
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arxiv Daily")
    parser.add_argument("--categories", nargs="+", help="categories", required=True)
    parser.add_argument("--max_paper_num", type=int, help="max_paper_num", default=60)
    parser.add_argument(
        "--max_entries", type=int, help="max_entries to get from arxiv", default=100
    )
    parser.add_argument(
        "--lookback_hours",
        type=int,
        default=24,
        help="仅保留过去 N 小时内的新论文（默认 24）。",
    )
    parser.add_argument(
        "--include_keywords",
        nargs="+",
        default=None,
        help="关键词包含过滤（大小写不敏感）。命中规则由 --include_mode 控制。",
    )
    parser.add_argument(
        "--exclude_keywords",
        nargs="+",
        default=None,
        help="关键词排除过滤（大小写不敏感）。命中任一关键词则剔除。",
    )
    parser.add_argument(
        "--include_mode",
        type=str,
        default="any",
        choices=["any", "all"],
        help="include_keywords 的命中规则：any=命中任一；all=必须命中全部。",
    )
    parser.add_argument(
        "--llm_batch_size",
        type=int,
        default=5,
        help="LLM 批处理大小（每次调用处理 N 篇论文，默认 5）。",
    )
    parser.add_argument(
        "--weight_topic",
        type=float,
        default=0.45,
        help="加权评分中 topic 的权重（默认 0.45）。",
    )
    parser.add_argument(
        "--weight_method",
        type=float,
        default=0.25,
        help="加权评分中 method 的权重（默认 0.25）。",
    )
    parser.add_argument(
        "--weight_novelty",
        type=float,
        default=0.15,
        help="加权评分中 novelty 的权重（默认 0.15）。",
    )
    parser.add_argument(
        "--weight_impact",
        type=float,
        default=0.15,
        help="加权评分中 impact 的权重（默认 0.15）。",
    )
    parser.add_argument(
        "--rerank_top_m",
        type=int,
        default=30,
        help="最终全局重排的候选集大小（Top-M，默认 30；设为 0 可关闭）。",
    )
    parser.add_argument(
        "--model",
        nargs="+",
        type=str,
        help="model（支持多个；当某个 model 调用失败时会按顺序切换）",
        required=True,
    )
    parser.add_argument(
        "--save", action="store_true", help="Save the email content to a file."
    )
    parser.add_argument("--save_dir", type=str, default="./arxiv_history")

    parser.add_argument(
        "--base_url",
        nargs="+",
        type=str,
        help="base_url（支持多个；当某个 endpoint 调用失败时会按顺序切换）",
        default=None,
    )
    parser.add_argument(
        "--api_key",
        nargs="+",
        type=str,
        help="api_key（支持多个；当某个 endpoint 调用失败时会按顺序切换）",
        default=None,
    )

    parser.add_argument(
        "--description",
        type=str,
        help="Path to the file that describes your interested research area.",
        default="description.txt",
    )

    parser.add_argument("--smtp_server", type=str, help="SMTP server")
    parser.add_argument("--smtp_port", type=int, help="SMTP port")
    parser.add_argument("--sender", type=str, help="Sender email address")
    parser.add_argument("--receiver", type=str, help="Receiver email address")
    parser.add_argument("--sender_password", type=str, help="Sender email password")
    parser.add_argument("--temperature", type=float, help="Temperature", default=0.7)

    parser.add_argument("--num_workers", type=int, help="Number of workers", default=4)
    parser.add_argument(
        "--title", type=str, help="Title of the email", default="Daily arXiv"
    )

    args = parser.parse_args()

    assert args.base_url is not None and len(args.base_url) > 0, (
        "base_url is required (OpenAI-compatible API)."
    )
    assert args.api_key is not None and len(args.api_key) > 0, (
        "api_key is required (OpenAI-compatible API)."
    )

    with open(args.description, "r") as f:
        args.description = f.read()

    # Test LLM availability
    from llm.GPT import GPT

    try:
        model = GPT(args.model, args.base_url, args.api_key)
        model.inference("Hello, who are you?")
    except Exception as e:
        print(e)
        assert False, "Model not initialized successfully."

    if args.save:
        os.makedirs(args.save_dir, exist_ok=True)
    else:
        args.save_dir = None

    arxiv_daily = ArxivDaily(
        args.categories,
        args.max_entries,
        args.max_paper_num,
        args.lookback_hours,
        args.include_keywords,
        args.exclude_keywords,
        args.include_mode,
        args.llm_batch_size,
        args.weight_topic,
        args.weight_method,
        args.weight_novelty,
        args.weight_impact,
        args.rerank_top_m,
        args.model,
        args.base_url,
        args.api_key,
        args.description,
        args.num_workers,
        args.temperature,
        args.save_dir,
    )

    arxiv_daily.send_email(
        args.sender,
        args.receiver,
        args.sender_password,
        args.smtp_server,
        args.smtp_port,
        args.title,
    )
