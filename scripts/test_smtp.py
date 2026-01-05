import argparse
import getpass
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from util.construct_email import send_email  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="发送一封 SMTP 测试邮件（不依赖 LLM/arXiv）。")
    parser.add_argument("--smtp_server", required=True, help="例如 smtp.qq.com")
    parser.add_argument("--smtp_port", required=True, type=int, help="例如 465 或 587")
    parser.add_argument("--sender", required=True, help="发件人邮箱")
    parser.add_argument(
        "--receiver",
        required=True,
        help="收件人邮箱；如需多个可用英文逗号分隔，将逐个发送",
    )
    parser.add_argument(
        "--sender_password",
        default=None,
        help="SMTP 授权码/密码（不建议明文传参；若不提供则读取环境变量 SMTP_PASSWORD 或交互输入）",
    )
    args = parser.parse_args()

    password = (
        args.sender_password
        or os.environ.get("SMTP_PASSWORD")
        or getpass.getpass("请输入 SMTP 授权码/密码（不会回显）：")
    )

    html = """
    <div style="font-family: Arial, sans-serif;">
      <h2>SMTP 测试邮件</h2>
      <p>如果你看到这封邮件，说明 SMTP 配置可以正常发送。</p>
    </div>
    """.strip()

    receivers = [addr.strip() for addr in args.receiver.split(",") if addr.strip()]
    if not receivers:
        raise SystemExit("receiver 不能为空")

    for receiver in receivers:
        send_email(
            sender=args.sender,
            receiver=receiver,
            password=password,
            smtp_server=args.smtp_server,
            smtp_port=args.smtp_port,
            html=html,
            from_name="arxiv-daily",
        )
        print(f"已发送测试邮件到：{receiver}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
