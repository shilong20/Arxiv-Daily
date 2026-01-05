#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

#
# 需要先设置环境变量（避免把密钥/密码写进仓库）：
#   export MODELSCOPE_API_KEY="..."
#   export SMTP_SENDER="xxx@qq.com"
#   export SMTP_RECEIVER="xxx@nudt.edu.cn"
#   export SMTP_PASSWORD="QQ 邮箱 SMTP 授权码"
#

uv run python main.py --categories cs.CV cs.AI \
  --base_url "https://api-inference.modelscope.cn/v1" \
  --api_key "${MODELSCOPE_API_KEY:-*}" \
  --model "deepseek-ai/DeepSeek-V3.2" \
         "XiaomiMiMo/MiMo-V2-Flash" \
         "Qwen/Qwen3-235B-A22B" \
         "Qwen/Qwen3-235B-A22B-Instruct-2507" \
  --smtp_server smtp.qq.com --smtp_port 465 \
  --sender "${SMTP_SENDER:-*}" --receiver "${SMTP_RECEIVER:-*}" \
  --sender_password "${SMTP_PASSWORD:-*}" \
  --lookback_hours 72 \
  --include_keywords diffusion flow \
  --exclude_keywords workflow workflows \
  --include_mode any \
  --llm_batch_size 5 \
  --weight_topic 0.45 --weight_method 0.25 --weight_novelty 0.15 --weight_impact 0.15 \
  --rerank_top_m 30 \
  --num_workers 5 \
  --temperature 0.7 \
  --title "Daily arXiv" \
  --description "description.txt" \
  --save --save_dir "./arxiv_history"
