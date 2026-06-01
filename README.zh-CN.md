# 🧠 Memstash

[English](README.md) | **简体中文**

**给任意大模型加持久记忆 + 完整成本/可观测 —— 本地优先,全在一个 SQLite 文件里。**
不用服务器、不用账号、零遥测。你的数据永远不出本机。

[![PyPI](https://img.shields.io/pypi/v/memstash.svg)](https://pypi.org/project/memstash/)
[![Downloads](https://img.shields.io/pypi/dm/memstash.svg)](https://pypi.org/project/memstash/)
[![CI](https://github.com/zionfly/memstash/actions/workflows/ci.yml/badge.svg)](https://github.com/zionfly/memstash/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Local-first](https://img.shields.io/badge/local--first-100%25-orange.svg)

```bash
pipx install 'memstash[all]'      # 或:pip install 'memstash[openai]'
```

---

Memstash 给任意大模型加上**持久记忆**,并记录**每次调用花了多少钱** —— 全在一个本地 SQLite 文件里。

把你的偏好和事实教给它一次,之后它会自动把相关的那些注入到你的提示词里,跨会话、跨模型都有效。每次调用的 token、成本、延迟都会被记录,让你看清——并能设上限——自己的花费。它完全跑在你本机:不用服务器、不用账号,什么都不离开你的电脑。

### 它能帮你做什么

- 给聊天机器人或 agent 一份**长期记忆**,重启、换模型都不丢。
- 把上下文从 GPT → Claude → 本地 Ollama **一路带着走,不用重新解释自己**。
- **看清并控制 token 花费** —— 按调用、按模型、按天。
- 让你的**笔记/文档可被助手检索**(`memstash ingest file.md`)。
- 让 **Claude Desktop / Cursor** 通过 MCP 读写同一份记忆。
- 把**现有 LangChain / OpenAI-SDK 应用**的调用收进本地日志。

### 能力清单

**🧠 记忆**
- 持久记忆,自动注入到 prompt;跨会话、跨模型
- 混合检索 —— 语义(embeddings)+ BM25(SQLite FTS5),RRF 融合
- 相关性 gate(`memory_min_score`)+ top-k 注入 —— 只注入相关的
- 自动捕获(启发式中英文,或可选 LLM 抽取)
- **类型化记忆** —— `note`/`preference`/`fact`/`decision`/`constraint`/`event`/`lesson`,外加 `confidence` 与 `source`
- **冲突消解**(opt-in)—— ADD/UPDATE/DELETE/NOOP,事实保持最新
- **生命周期** —— 命中追踪、新近度排序、软遗忘、`prune`
- **双时态** —— `list --at <时间>`:查某个历史时刻有效的记忆
- **graph-lite** —— (主-谓-宾)关系 + 图谱感知检索(不用图数据库)
- 编辑、精确 + 相似度去重、来源追溯、JSON 导出/导入
- **scope 隔离**(按项目)+ **自动 scope**(按 git 仓库/目录)
- 文档摄入(`.md`/`.txt`/`.pdf`)
- embedding:本地模型 **或** 任意 OpenAI 兼容接口(Ollama / LM Studio,免 PyTorch)

**🛡️ 写入防火墙(防污染)**
- 不可信写入进隔离区(存为 inactive、永不注入),等你 `approve`/`reject`
- 来源信任分级 + 注入特征启发式(中英文);模式:quarantine / warn / off

**💬 对话**
- 22 个 provider 一套接口(OpenAI 兼容、Claude、Gemini、DeepSeek/Qwen/Kimi/GLM…、本地 Ollama/LM Studio)
- 流式、多轮历史、交互式 REPL(`memstash chat`)、prompt 模板

**📊 可观测 / 成本**
- 每调用 token/成本/延迟;`stats`、`recent`、逐轮**调用树**
- 日预算警告 + 可选硬上限;维护型、可覆盖的定价表
- 质量**评测**(规则检查 + LLM judge、可存套件、chat 后自动评)
- 本地网页面板;opt-in OpenTelemetry 导出
- `instrument()` —— 把现有 LangChain / OpenAI-SDK 的调用收进本地账本

**🔌 平台 / 可靠性**
- MCP server(Claude Desktop / Cursor 读写同一份记忆)
- 自定义 provider 插件机制;可复现 benchmark(`memstash benchmark`)
- 库 API + 40+ CLI 命令;100% 本地、单 SQLite(WAL);重功能全是 opt-in

```
┌──────────────┐     ┌─────────────────────────────┐
│  任意模型     │     │  Memstash(本地 SQLite)      │
│  GPT / Claude│ ◄──►│  • 记忆   → 自动注入          │
│  DeepSeek/Qwen│    │  • 追踪   → token & 成本      │
└──────────────┘     └─────────────────────────────┘
            什么都不离开你的电脑
```

## 快速上手(30 秒)

```bash
# 推荐:一条命令把 CLI 和全部功能装好
pipx install 'memstash[all]'        # 或:uv tool install 'memstash[all]'

# 或按需安装(base = 关键词记忆 + 追踪,无重依赖):
pip install 'memstash[openai]'      # GPT / DeepSeek / Qwen / OpenAI 兼容
#   pip install 'memstash[anthropic]'   # Claude
#   pip install 'memstash[gemini]'      # Gemini
#   pip install 'memstash[embeddings]'  # 语义检索(首次会下载一个模型)
#   pip install 'memstash[dashboard]'   # 网页面板
#   pip install 'memstash[mcp]'         # MCP server
#   pip install 'memstash[otel]'        # OpenTelemetry 导出
#   pip install memstash                # 仅 base(关键词 + 追踪)
```

```bash
# 0.(可选)向导式初始化:选默认模型、检测 API key
memstash init

# 1. 教它认识你(一次即可)
memstash add "我喜欢简洁、带表格的回答" --tags style
memstash add "我在做 A 股和港股量化研究" --tags work

# 2. 用任意模型聊天 —— 它已经认识你,且这次调用被记账
export OPENAI_API_KEY=sk-...
memstash chat openai gpt-4o-mini "你该怎么回复我?"
#   ↑ 同时会自动捕获你新提到的偏好

# 配好默认值后,直接:
memstash chat "我在做什么?"

# 或进入交互式多轮聊天(记忆 + 追踪都开着):
memstash chat

# 3. 看清楚你花了多少(以及预算)
memstash stats
```

```
memstash stats

Memories stored : 2
Model calls     : 1
Tokens          : 312 in / 88 out
Total cost      : $0.0001
Avg latency     : 740 ms
```

换个模型,记忆和账本都不变:

```bash
export ANTHROPIC_API_KEY=sk-...
memstash chat anthropic claude-3-5-sonnet "提醒我一下我在做什么"
# → 依然记得你的 A 股 / 港股量化工作
```

## 当作库使用

```python
from memstash import Memstash

r = Memstash()
r.remember("我喜欢简洁的回答", tags=["style"])

out = r.chat("openai", "gpt-4o-mini", "你该怎么回复我?")
print(out.text)          # 模型已经知道你的偏好

print(r.stats())         # {'calls': 1, 'cost_usd': ..., ...}
```

## 网页面板

```bash
pip install 'memstash[dashboard]'
memstash dashboard          # → http://127.0.0.1:8745
```

一个本地页面:记忆卡片、按模型的成本、最近调用。无构建步骤、无遥测、无云。

## 流式输出

回复默认流式 —— 边生成边显示,最后跟上成本/延迟信息。

```bash
memstash chat "写一首关于记忆的俳句"   # 逐字流式
memstash chat                          # 交互式多轮 REPL
memstash chat --no-stream "..."        # 改为等完整回复
memstash config set stream false       # 把非流式设为默认
```

REPL 里每一轮都保留本次会话的上下文,*同时*注入你的长期记忆 —— 输入 `/exit` 或按 Ctrl-D 退出。

库里传一个 `on_token` 回调即可流式,仍返回完整结果:

```python
out = r.stream("openai", "gpt-4o-mini", "讲个笑话",
               on_token=lambda t: print(t, end="", flush=True))
print(out.cost_usd, out.output_tokens)     # 流式结束后拿到完整账目
```

## 更聪明的记忆抽取(opt-in)

默认用快速、免费的启发式(正则线索,中英文)捕获记忆。打开 LLM 抽取后,让模型读每条消息、提取可长期保留的第一人称事实 —— 召回更高,代价是一次额外(便宜的)调用,且也计入预算。

```bash
memstash config set extraction_mode llm          # heuristic(默认)| llm
memstash config set extraction_model gpt-4o-mini # 可选;默认用对话模型
```

抽取调用一旦失败(无 key、网络、坏输出),memstash 会静默回退到启发式抽取,聊天永不中断。

## 整理你的记忆

```bash
memstash edit 3 "我喜欢简洁、带表格的回答"   # 改写一条记忆
memstash edit 3 --tags style,format           # 或只改标签

# 合并自动捕获堆积的近似重复(需要 embeddings)
memstash dedupe --dry-run        # 预览哪些会被合并
memstash dedupe --threshold 0.9  # 保留最早的、合并标签、删掉其余
memstash config set dedupe_similarity 0.95   # 也可在写入时就抑制近似重复
```

编辑会重新嵌入,保证语义检索准确。去重把相似度 ≥ 阈值的记忆归并,保留最早的为主、合并标签 —— 即使没装 embeddings,精确去重也照样生效。

## 语义检索免下大模型

默认语义检索用本地 `sentence-transformers` 模型(`pip install 'memstash[embeddings]'`,首次约 80MB)。不想引入 PyTorch 的话,把 memstash 指向任意 **OpenAI 兼容的 `/embeddings` 接口** —— 比如你本机已经在跑的 Ollama 或 LM Studio:

```bash
memstash config set embedding_backend api
memstash config set embedding_base_url http://localhost:11434/v1   # Ollama
memstash config set embedding_model nomic-embed-text
# 云端接口:再设 embedding_api_key_env 指向存放 key 的环境变量名
```

这样 `memstash add` / `memstash search` 走 HTTP 拿语义向量,无重型本地依赖。接口不可达时,memstash 自动回退到关键词/BM25 检索。

## MCP server —— 接进任意 agent

把你的本地记忆暴露给任意 MCP 客户端(Claude Desktop、Claude Code、Cursor …),让 agent 读写你在 CLI 里用的*同一份*大脑。

```bash
pip install 'memstash[mcp]'
memstash mcp        # 以 stdio 跑一个 MCP server
```

接进你的 MCP 客户端配置:

```json
{
  "mcpServers": {
    "memstash": { "command": "memstash", "args": ["mcp"] }
  }
}
```

暴露的工具:`remember`、`recall_search`、`list_memories`、`forget`、`usage_stats`。同一个本地 SQLite,什么都不离开你的电脑。

## 接管你现有应用的 LLM 调用

已经在用 LangChain、LlamaIndex 或 OpenAI SDK?把 memstash 当成它们调用的**本地汇聚点** —— 无服务器、无云(相当于本地版的 Phoenix/Langfuse 自动埋点):

```python
import memstash
memstash.instrument()                     # 之后 span 落到 ~/.memstash/memstash.db

from openinference.instrumentation.openai import OpenAIInstrumentor
OpenAIInstrumentor().instrument()       # (装了的话 memstash 会自动启用)
# ...你平常的 OpenAI/LangChain 代码现在都出现在 `memstash recent` / `stats` 里。
```

需要 `pip install 'memstash[otel]'` 以及你所用的 OpenInference instrumentor。被捕获的调用标记为 `kind="instrumented"`。

## 支持的模型(22 个 provider)

跨云、国产、快速推理、本地模型随意组合 —— 你的记忆和成本账本到哪都跟着。

| Provider | `provider` 参数 | 示例模型 | API key 环境变量 |
|---|---|---|---|
| OpenAI | `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-3-5-sonnet`, `claude-3-5-haiku` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini` | `gemini-1.5-pro`, `gemini-2.0-flash` | `GEMINI_API_KEY` |
| DeepSeek | `deepseek` | `deepseek-chat`, `deepseek-reasoner` | `DEEPSEEK_API_KEY` |
| 通义千问(DashScope) | `qwen` | `qwen-plus`, `qwen-max` | `DASHSCOPE_API_KEY` |
| 月之暗面(Kimi) | `moonshot` | `moonshot-v1-8k`, `moonshot-v1-32k` | `MOONSHOT_API_KEY` |
| 智谱(GLM) | `zhipu` | `glm-4`, `glm-4-flash` | `ZHIPU_API_KEY` |
| MiniMax | `minimax` | `abab6.5s` | `MINIMAX_API_KEY` |
| 百川 | `baichuan` | `Baichuan4` | `BAICHUAN_API_KEY` |
| 零一万物(Yi) | `yi` | `yi-large`, `yi-lightning` | `YI_API_KEY` |
| 阶跃星辰 | `stepfun` | `step-1` | `STEPFUN_API_KEY` |
| Mistral | `mistral` | `mistral-large`, `mistral-small` | `MISTRAL_API_KEY` |
| xAI(Grok) | `xai` | `grok-2`, `grok-beta` | `XAI_API_KEY` |
| Groq | `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| Together | `together` | 开源模型 | `TOGETHER_API_KEY` |
| Fireworks | `fireworks` | 开源模型 | `FIREWORKS_API_KEY` |
| DeepInfra | `deepinfra` | 开源模型 | `DEEPINFRA_API_KEY` |
| Perplexity | `perplexity` | `sonar`, `sonar-pro` | `PERPLEXITY_API_KEY` |
| OpenRouter | `openrouter` | 400+ 模型,一个 key | `OPENROUTER_API_KEY` |
| Ollama(本地) | `ollama` | `llama3`, `qwen2.5` | — |
| LM Studio(本地) | `lmstudio` | 任意已加载模型 | — |
| 任意 OpenAI 兼容 | `openai-compatible` | 设 `--base-url` | `MEMSTASH_API_KEY` |

```bash
memstash models   # 列出所有 provider + key 环境变量 + base URL
```

> 大多数 provider 说的是 OpenAI 协议,共用一个适配器 —— 指向正确的 base URL 即可(已自动处理)。Gemini 有自己的原生适配器。本地模型(Ollama / LM Studio)无需 key、无需云。

## Scope、预算与配置

```bash
# 按项目隔离记忆
memstash scope work            # 切换当前 scope
memstash add "周五截止"        # 存入 'work'
memstash scope                 # 列出所有 scope
memstash list --all            # 查看所有 scope
memstash config set scope_auto true   # 或:按当前 git 仓库 / 目录自动选 scope

# 只注入相关记忆(调高更严格;没有相关的就不注入)
memstash config set memory_min_score 0.3

# 设置每日花费上限(80% 和 100% 时警告)
memstash config set daily_budget_usd 1.0
memstash config set budget_enforce true   # 硬上限:到顶后直接拒绝调用

# 设默认值,之后直接 `memstash chat "..."`
memstash config set default_provider deepseek
memstash config set default_model deepseek-chat
memstash config show

# 备份 / 迁移你的大脑
memstash export my-brain.json
memstash import my-brain.json
```

## CLI 速查

| 命令 | 作用 |
|---|---|
| `memstash init` | 向导式首次设置 |
| `memstash doctor` | 查看哪些 provider 已配 key |
| `memstash add "..." [--type decision] [--confidence 0.9] [--source ref] [--tags a,b]` | 存一条(带类型的)记忆 |
| `memstash ingest <file.md/.txt/.pdf>` | 把文档摄入可检索记忆 |
| `memstash search "..." [--all]` | 语义(或关键词)检索 |
| `memstash list [--all] [--type T] [--at WHEN]` | 列出记忆(按类型 / 当前有效 / 历史时间点) |
| `memstash show <id>` | 查看一条记忆 + 来源(出处对话) |
| `memstash edit <id> ["新内容"] [--tags ...]` | 原地编辑一条记忆 |
| `memstash forget <id> [--soft]` | 删除(或软遗忘)一条记忆 |
| `memstash prune [--older-than DAYS] [--unused] [--all]` | 软遗忘陈旧记忆 |
| `memstash dedupe [--threshold 0.9] [--all] [--dry-run]` | 合并近似重复记忆 |
| `memstash graph [entity] [--add "s\|p\|o"]` | 查看 / 新增实体关系 |
| `memstash scope [name]` | 切换 / 列出 scope |
| `memstash chat [provider model] "..." [-T tmpl -V k=v] [--no-stream]` | 带记忆 + 追踪 + 自动记忆地聊天 |
| `memstash chat` | 交互式多轮聊天(REPL) |
| `memstash stats` | token、成本与预算总览 |
| `memstash recent` | 最近调用(含 trace ID) |
| `memstash trace` | 最近若干轮的调用树 |
| `memstash eval <id> [--contains/--regex/--judge/--suite ...]` | 给某次回复打分(规则 / LLM 评判) |
| `memstash evals [--trace id]` | 列出评测结果 |
| `memstash eval-suite save/list/rm` | 管理可复用的评测套件 |
| `memstash pricing [model]` | 显示某模型每百万 token 的解析价格 |
| `memstash benchmark` | 可复现的检索/抽取质量跑分 |
| `memstash models` | 支持的 provider |
| `memstash prompt save/list/show/use/rm` | 管理 prompt 模板 |
| `memstash export/import <file>` | 备份 / 恢复记忆 |
| `memstash config show/set/path` | 查看与修改配置 |
| `memstash dashboard` | 启动本地网页面板 |
| `memstash mcp` | 作为 MCP server(stdio)供任意 agent 使用 |

## 我的数据在哪?

就一个 SQLite 文件:`~/.memstash/memstash.db`(可用 `MEMSTASH_HOME` 覆盖)。没了。无账号、无服务器、无遥测。你可以备份它、版本管理它、自己同步它、删掉它 —— 它是你的。

## 为什么本地优先?

- **隐私** —— 你的记忆和提示词都留在你自己的磁盘上。
- **可携带** —— 一个文件,自己随便搬、版本化、同步。
- **不锁定** —— 跨 provider,随意换模型。

## Benchmark

memstash 自带一个可复现、无需 key 的质量基准:

```bash
memstash benchmark
```

它种入一组手工标注的固定记忆,衡量检索质量(recall@1、recall@k、precision@k、MRR)以及启发式抽取的 fact-recall —— 并诚实标注本次用的是 **semantic** 还是 **keyword/BM25** 模式。关键词基线:`recall@1 ≈ 0.50, MRR ≈ 0.69`,抽取 fact-recall `1.00`、误捕 `0`;装上 `[embeddings]`(或 api 后端)分数更高。数字是确定性的,可用于跨版本追踪。

## 路线图

见 [ROADMAP.md](ROADMAP.md):已完成的内容,以及接下来的计划。

- [x] 从对话自动抽取记忆
- [x] 预算提醒("你今天花了 $X")
- [x] Gemini + 本地 Ollama / LM Studio 适配器
- [x] 记忆导出 / 导入
- [x] 记忆 scope
- [x] 流式聊天输出
- [x] 基于 LLM 的记忆抽取(opt-in,更高召回)
- [x] MCP server,任意 agent 可读写 memstash 记忆
- [x] PyPI 发布(`pip install memstash`)—— 打 tag 自动发布
- [x] 记忆编辑 & 按相似度合并 / 去重

## 贡献

欢迎提 issue 和 PR。运行测试:

```bash
pip install 'memstash[dev]'
pytest
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

MIT © [zionfly](https://github.com/zionfly)
