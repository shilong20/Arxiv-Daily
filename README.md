<h3 align="center">Customize-arXiv-Daily</h3>

---

<p align="center">基于你的研究兴趣描述，每日推荐你可能感兴趣的 arXiv 新论文，并通过邮件发送。<br></p>

> [!NOTE]
> 本项目借鉴并复用了一部分 [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) 的思路与实现，感谢原作者的工作。

## 主要特性

- 可自定义提示词（prompt），控制 LLM 摘要与相关性评分逻辑。
- 支持历史保存（`arxiv_history/`），便于回溯与复用缓存。
- 批量打分 + Top-M 重排（rerank），减少同分并提升排序稳定性。
- 邮件开头固定展示 Top-5，快速扫读。
- 支持 GitHub Actions 定时运行，每日自动发送邮件。
- 默认使用ModelScope提供的每日免费API（deepseek-ai/DeepSeek-V3.2）。

## 截图

![screenshot](./assets/screenshot.png)

## 使用方法

### 快速开始

1. 克隆仓库

```bash
git clone https://github.com/shilong20/Arxiv-Daily.git
cd customize-arxiv-daily
```

2. 安装依赖（推荐 `uv`；也可用 `pip`）

```bash
uv sync
# 或：pip install -r requirements.txt
```

> 运行环境：Python 3.12+（工作流默认使用 3.12）。

3. 配置你的研究兴趣（编辑 `description.txt`，中文/英文均可）

4. 准备 SMTP 邮箱并注入密钥（避免把密钥/密码写进仓库）

`main_gpt.sh` 默认通过环境变量读取密钥：

```bash
export MODELSCOPE_API_KEY="..."
export SMTP_SENDER="xxx@qq.com"
export SMTP_RECEIVER="yyy@gmail.com"
export SMTP_PASSWORD="你的 SMTP 授权码/密码"
```

5. 运行

```bash
bash main_gpt.sh
```

说明：
- `main_gpt.sh` 里可以直接改 `--categories/--include_keywords/--exclude_keywords/--model/--base_url` 等参数来定制你的每日推荐。
- 想查看完整参数说明：`uv run python main.py --help`。

## 部署到 GitHub Actions（每日自动运行）

仓库已包含工作流：`.github/workflows/daily.yml`，会定时执行 `bash main_gpt.sh`，并把 `state/seen_ids.json` 的更新提交回仓库，用于去重，防止重复处理/重复发邮件。

### 1) 准备仓库（重要）

GitHub 默认不会在“fork 的仓库”中触发 `schedule`（cron）事件。建议你用以下任一方式创建自己的仓库：

- 方式 A（推荐）：新建一个仓库，把本项目代码推上去（不要用 fork）。
- 方式 B：如果你必须 fork，请优先通过 `workflow_dispatch` 手动触发来验证，并确认你的仓库确实支持定时触发。

### 2) 配置 Secrets

进入你的 GitHub 仓库：`Settings -> Secrets and variables -> Actions -> New repository secret`，添加：

- `MODELSCOPE_API_KEY`：模型服务的 API Key（或你的 OpenAI 兼容服务的 key；并据此修改 `main_gpt.sh` 的 `--base_url/--model`）
- `SMTP_SENDER`：发件邮箱
- `SMTP_RECEIVER`：收件邮箱
- `SMTP_PASSWORD`：SMTP 授权码/密码

### 3) 赋予工作流写权限（用于回写 seen_ids）

进入：`Settings -> Actions -> General -> Workflow permissions`：

- 选择 `Read and write permissions`（否则工作流最后的 `git push` 会失败）。

### 4) 调整每日运行时间（可选）

`.github/workflows/daily.yml` 使用 UTC cron。当前默认配置是“北京时间 06:00”，对应：

- `cron: "0 22 * * *"`（UTC 22:00 = 北京时间次日 06:00）

你可以按需修改 `schedule`。

### 5) 验证一次（推荐）

进入 `Actions`，手动触发工作流（`workflow_dispatch`），确认：

- 工作流运行成功；
- 你能收到邮件；
- 仓库会出现一次对 `state/seen_ids.json` 的提交（若没有变化则不会提交）。

## 自定义提示词（可选）

可以在 `arxiv_daily.py` 中调整 `_build_batch_prompt(...)` / `_build_rerank_prompt(...)` 来修改 LLM 的摘要/打分逻辑。

## 工作原理

- `util/request.py`：根据你提供的 arXiv 分类抓取近期论文（arXiv Atom API），默认仅保留近 24 小时内的新论文。
- `arxiv_daily.py`：调用 LLM 生成摘要与相关性评分，并排序/重排。
- `util/construct_email.py`：组装 HTML 邮件并通过 SMTP 发送。

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

## 局限性

- LLM 的推荐与相关性评分存在不稳定性；不同模型之间的分数可比性也较弱，建议结合 `rerank` 与关键词过滤来提升稳定性与可控性。
