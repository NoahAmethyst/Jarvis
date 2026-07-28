# Jarvis

基于 LangGraph 构建的 LLM 智能助手后端服务。支持工具链（在线搜索、网页抓取）、跨会话记忆、RAG 检索增强和自评分反思机制，同时暴露 FastAPI（HTTP）和 gRPC 两套接口。

## 架构

```
HTTP :8080 / gRPC :9090
         │
   LangGraph Agent
         │
  memory_load        ← 加载对话历史 + 用户档案
       ↓
  agent_dispatch     ← LLM 语义评分，选择最匹配的自定义 Agent（低于阈值则跳过）
       ↓
  rag_retrieve       ← Qdrant 检索相关知识
       ↓
  plan_and_call      ← LLM 决策：调工具 or 直接回答（注入 active_agent 指令）
       ↓
  tool_node          ← 搜索 / 抓取 / 第三方 API
       ↓
  reflect            ← 自评分，score < 0.7 则循环回 plan（最多 3 次）
       ↓
  memory_write       ← 写对话历史；工具内容 > 200 字自动入 Qdrant
         │
    ┌────┴────┐
  Qdrant  PostgreSQL
```

## 快速开始

### 1. 启动依赖

```bash
docker compose up -d
```

启动 PostgreSQL（:5432）和 Qdrant（:6333）。

### 2. 安装依赖

```bash
pip install -e .
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API Key
```

默认运行至少需要填写 `DEEPSEEK_API_KEY`（全部对话能力）和
`SILICONFLOW_API_KEY`（Embedding）。如启用搜索工具，还需填
`TAVILY_API_KEY`。

### 4. 启动服务

```bash
python jarvis/main.py
```

进程会在绑定端口前，对每个活跃 Chat Provider 执行一次真实模型请求，并对
Embedding 执行一次真实请求。探测会产生少量 API 用量并可能延迟端口监听；
失败只记录脱敏日志，不阻止后续启动。随后初始化 PostgreSQL 和 Qdrant，任一
存储初始化失败都会阻止服务监听。

HTTP 服务默认监听 `0.0.0.0:8080`，gRPC 使用明文监听 `[::]:9090`，并非只
绑定 localhost。当前应用没有鉴权或 TLS；启动前应通过防火墙、私网或可信
反向代理隔离访问。

## HTTP API

完整的 HTTP/gRPC 接入契约、错误码、客户端示例和 Codex 接入检查清单见
[`API.md`](API.md)。

### POST /chat

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "LangGraph 是什么？",
    "user_id": "user_001"
  }'
```

`llm` 和 `reflect_llm` 可选，不填则使用 `llm.yaml` 中的 Profile。
覆盖值仍使用 `provider/model_id` 格式，例如 `openai/gpt-4o`。回答
Profile 覆盖到不支持 thinking 的模型时会按配置显式关闭 thinking，
但覆盖模型仍必须支持工具调用。

响应：

```json
{
  "answer": "LangGraph 是...",
  "low_confidence": false
}
```

`low_confidence: true` 表示经过最大重试次数后答案评分仍低于阈值。

### POST /ingest

手动上传文档入知识库：

```bash
curl -X POST http://localhost:8080/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "文档内容...",
    "source_url": "https://example.com/doc",
    "user_id": "user_001"
  }'
```

### GET /memory/{uid}

查看用户对话历史：

```bash
curl http://localhost:8080/memory/user_001
```

### DELETE /memory/{uid}

仅清除用户在 PostgreSQL 中的对话历史，不会删除通过 `/ingest` 或工具结果写入
Qdrant 的知识；不能作为“删除用户全部数据”的接口。完整删除范围见
[`API.md`](API.md#36-delete-memoryuid)。

```bash
curl -X DELETE http://localhost:8080/memory/user_001
```

## gRPC API

Proto 定义见 `jarvis/api/grpc/jarvis.proto`，服务名 `JarvisService`，提供与 HTTP 对等的四个 RPC：`Chat`、`Ingest`、`GetMemory`、`DeleteMemory`。

## LLM 配置

对话模型由根目录 `llm.yaml` 配置。业务节点只引用 `answer`、
`reflection`、`agent_dispatch` 三个 Profile，供应商与协议差异由
LLM Gateway 和固定 Adapter 处理。

请求级模型覆盖使用 `"provider/model_id"` 格式：

| Provider | 示例 |
|----------|------|
| `deepseek` | `deepseek/deepseek-v4-pro` |
| `siliconflow` | `siliconflow/deepseek-ai/DeepSeek-V4-Pro` |
| `openai` | `openai/gpt-4o` |
| `claude` | `claude/claude-opus-4-1` |

默认 Profile：

| 用途 | 默认值 |
|------|--------|
| `answer` | `deepseek/deepseek-v4-pro`，thinking high，启用工具 |
| `reflection` | `deepseek/deepseek-v4-flash`，关闭 thinking 与工具 |
| `agent_dispatch` | `deepseek/deepseek-v4-flash`，关闭 thinking 与工具 |
| Embedding 模型 | `siliconflow/Qwen/Qwen3-Embedding-8B` |

同一协议族的新供应商只需在 `llm.yaml` 中选择
`openai_compatible` 或 `anthropic` Adapter。全新消息协议才需要新增一个
Adapter，LangGraph 节点无需修改。SiliconFlow Chat 的 10 条消息限制由
Gateway 按完整 assistant/tool 消息组裁剪；DeepSeek 不额外设置消息条数
上限，而遵循上下文 Token 限制。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HTTP_PORT` | `8080` | HTTP 监听端口 |
| `GRPC_PORT` | `9090` | gRPC 监听端口 |
| `LLM_CONFIG_PATH` | `llm.yaml` | LLM Provider 与 Profile 配置文件 |
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key（默认对话必填） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 接口地址 |
| `SILICONFLOW_API_KEY` | — | SiliconFlow API Key（默认 Embedding 必填） |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | SiliconFlow 接口地址 |
| `OPENAI_API_KEY` | — | OpenAI API Key |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key |
| `TAVILY_API_KEY` | — | Tavily 搜索 API Key |
| `EMBED_MODEL` | `siliconflow/Qwen/Qwen3-Embedding-8B` | Embedding 模型 |
| `VECTOR_SIZE` | `4096` | 向量维度（与 Embedding 模型匹配） |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 连接地址 |
| `POSTGRES_DSN` | `postgresql://postgres:postgres@localhost:5432/jarvis` | PostgreSQL 连接串 |
| `REFLECTION_SCORE_THRESHOLD` | `0.7` | 低于此分数触发重试 |
| `REFLECTION_MAX_RETRIES` | `3` | 最大重试次数 |
| `KNOWLEDGE_MIN_LENGTH` | `200` | 工具返回内容超过此长度自动入库 |
| `AGENTS_DIR` | `.agents/skills` | 自定义 Agent 定义文件目录 |
| `AGENT_DISPATCH_THRESHOLD` | `0.6` | Agent 匹配评分阈值，低于此值不激活 |

## 扩展工具

> **安全提示：** 默认 `web_scrape` 当前没有 SSRF 防护。面向不可信用户或
> 公网开放前，必须先禁用该工具，或实现 URL/DNS/重定向校验并通过网络层限制
> egress，同时限制响应字节、解压大小、Content-Type、总时间、重定向和并发。
> 当前没有单工具禁用开关；关闭 `answer.tools` 会关闭全部工具。完整接入安全
> 边界见 [`API.md`](API.md)。

新增工具只需在 `jarvis/tools/` 下创建文件并使用 `@register_tool` 装饰器：

```python
from jarvis.tools.registry import register_tool

@register_tool(name="my_tool", description="工具描述")
def my_tool(input: str) -> str:
    return "结果"
```

在 `jarvis/agent/graph.py` 顶部 import 该模块即可自动注册，无需修改图逻辑。

## 自定义 Agent

Jarvis 支持通过文件定义领域专属 Agent。每次对话时，`agent_dispatch` 节点用 LLM 对用户输入评分，选出最匹配的 Agent，其指令会注入 `plan_and_call` 的系统提示，改变模型行为。

### 目录结构

Agent 定义文件放在 `AGENTS_DIR`（默认 `.agents/skills/`），每个 Agent 独立子目录：

```
.agents/skills/
└── my-agent/
    ├── agent.yaml       # 或 agent.json 或 SKILL.md
    └── agents/
        └── openai.yaml  # 可选：为 SKILL.md 提供显示名称和简短描述
```

### 定义格式

**agent.yaml**

```yaml
name: my-agent
description: 当用户问 X 类问题时激活此 Agent
---
# 系统指令
你是一个专注于 X 领域的助手。回答时...
```

**agent.json**

```json
{
  "name": "my-agent",
  "description": "当用户问 X 类问题时激活此 Agent",
  "instructions": "你是一个专注于 X 领域的助手。"
}
```

**SKILL.md**（frontmatter + Markdown 正文）

```markdown
---
name: my-agent
description: 当用户问 X 类问题时激活此 Agent
---

你是一个专注于 X 领域的助手。
```

当 `SKILL.md` 未提供 `name` 或 `description` 时，Jarvis 会尝试读取同目录下的
`agents/openai.yaml`，使用 `interface.display_name` 和
`interface.short_description` 作为元数据兜底；系统指令仍取 `SKILL.md` 正文。

### 评分与阈值

`agent_dispatch` 使用同名 LLM Profile 对每个 Agent 的 description 和用户
query 打分（0–1）。超过 `AGENT_DISPATCH_THRESHOLD`（默认 `0.6`）的最高分
Agent 被激活；全部低于阈值则不激活任何 Agent，走默认行为。请求中的
`reflect_llm` 会同时覆盖 Reflection 和 Agent dispatch 的目标模型，但各自
仍保留 Profile 的关闭 thinking/工具策略。

## 降级策略

PostgreSQL 和 Qdrant 在进程启动初始化阶段都是硬依赖；任一初始化失败时，
HTTP/gRPC 服务不会开始监听。下表描述的是服务已经成功启动后的单次请求降级：

| 组件不可用 | 降级行为 |
|-----------|---------|
| Qdrant | 跳过 RAG，纯对话继续 |
| PostgreSQL | 跳过历史加载和持久化；本次请求可继续，但本轮消息不会跨请求保留 |
| 工具执行失败 | 异常写入状态，LLM 基于失败信息重规划 |

## 运行测试

```bash
pytest tests/ -v
```

测试分三层：`tests/unit/`（配置、Adapter、Gateway 与节点单测）、
`tests/integration/`（以 mock 隔离外部 LLM/存储的图与 RAG 流程）、
`tests/e2e/`（FastAPI TestClient）。默认测试不会调用真实供应商 API。

## 目录结构

```
jarvis/
├── config.py              # 环境变量与默认配置
├── logging_config.py      # 进程日志格式与第三方日志级别
├── main.py                # 服务入口（并行启动 HTTP + gRPC）
├── startup_checks.py      # 启动前 Chat Provider 与 Embedding 真实探测
├── llm/                   # Profile Gateway 与协议 Adapter
│   ├── config.py          # llm.yaml 类型化加载
│   ├── gateway.py         # 统一 chat、能力、裁剪、重试与错误归一化
│   ├── errors.py          # 安全的 LLM 异常层
│   ├── adapters/          # DeepSeek / OpenAI-compatible / Anthropic
│   └── router.py          # 仅保留旧 raw-model API 兼容
├── tools/
│   ├── registry.py        # @register_tool 装饰器
│   ├── search.py          # Tavily 搜索
│   └── scraper.py         # BeautifulSoup 抓取
├── memory/
│   ├── conversation.py    # PostgreSQL 对话历史
│   └── knowledge.py       # Qdrant 向量知识库
├── agent/
│   ├── state.py           # AgentState TypedDict
│   ├── graph.py           # LangGraph 图定义
│   └── nodes/             # 6 个节点实现
├── agents/
│   ├── __init__.py        # AgentDefinition dataclass
│   ├── loader.py          # 扫描目录，解析 agent.json/yaml/SKILL.md
│   └── dispatcher.py      # LLM 语义评分 + 阈值决策
└── api/
    ├── http/routes.py     # FastAPI endpoints
    └── grpc/              # gRPC server + servicer + proto
```
