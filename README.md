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

至少需要填写 `SILICONFLOW_API_KEY`（主模型和 Embedding）。如启用搜索工具，还需填 `TAVILY_API_KEY`。

### 4. 启动服务

```bash
python jarvis/main.py
```

HTTP 服务监听 `:8080`，gRPC 服务监听 `:9090`。

## HTTP API

### POST /chat

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "LangGraph 是什么？",
    "user_id": "user_001",
    "llm": "siliconflow/deepseek-ai/DeepSeek-V4-Pro",
    "reflect_llm": "siliconflow/moonshotai/Kimi-K2.6"
  }'
```

`llm` 和 `reflect_llm` 可选，不填则使用环境变量默认值。

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

### GET /memory/{user_id}

查看用户对话历史：

```bash
curl http://localhost:8080/memory/user_001
```

### DELETE /memory/{user_id}

清除用户记忆：

```bash
curl -X DELETE http://localhost:8080/memory/user_001
```

## gRPC API

Proto 定义见 `jarvis/api/grpc/jarvis.proto`，服务名 `JarvisService`，提供与 HTTP 对等的四个 RPC：`Chat`、`Ingest`、`GetMemory`、`DeleteMemory`。

## LLM 配置

模型通过 `"provider/model_id"` 格式指定：

| Provider | 示例 |
|----------|------|
| `siliconflow` | `siliconflow/deepseek-ai/DeepSeek-V4-Pro` |
| `openai` | `openai/gpt-4o` |
| `claude` | `claude/claude-opus-4-7` |

默认模型（可通过环境变量覆盖）：

| 用途 | 默认值 |
|------|--------|
| 主模型（生成回答） | `siliconflow/deepseek-ai/DeepSeek-V4-Pro` |
| 评分模型（Reflection） | `siliconflow/moonshotai/Kimi-K2.6` |
| Embedding 模型 | `siliconflow/Qwen/Qwen3-Embedding-8B` |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HTTP_PORT` | `8080` | HTTP 监听端口 |
| `GRPC_PORT` | `9090` | gRPC 监听端口 |
| `SILICONFLOW_API_KEY` | — | SiliconFlow API Key（必填） |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | SiliconFlow 接口地址 |
| `OPENAI_API_KEY` | — | OpenAI API Key |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key |
| `TAVILY_API_KEY` | — | Tavily 搜索 API Key |
| `ANSWER_LLM` | `siliconflow/deepseek-ai/DeepSeek-V4-Pro` | 主模型 |
| `REFLECT_LLM` | `siliconflow/moonshotai/Kimi-K2.6` | 评分模型 |
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

`agent_dispatch` 调用 `REFLECT_LLM` 对每个 Agent 的 description 和用户 query 打分（0–1）。超过 `AGENT_DISPATCH_THRESHOLD`（默认 `0.6`）的最高分 Agent 被激活；全部低于阈值则不激活任何 Agent，走默认行为。

## 降级策略

| 组件不可用 | 降级行为 |
|-----------|---------|
| Qdrant | 跳过 RAG，纯对话继续 |
| PostgreSQL | 内存临时存储当前会话，会话结束丢弃 |
| 工具执行失败 | 异常写入状态，LLM 基于失败信息重规划 |

## 运行测试

```bash
pytest tests/ -v
```

测试分三层：`tests/unit/`（mock LLM）、`tests/integration/`（真实 Qdrant/PostgreSQL）、`tests/e2e/`（FastAPI TestClient）。

## 目录结构

```
jarvis/
├── config.py              # 环境变量与默认配置
├── main.py                # 服务入口（并行启动 HTTP + gRPC）
├── llm/                   # LLM Provider 层
│   ├── base.py            # BaseLLMProvider 抽象接口
│   ├── siliconflow.py
│   ├── openai.py
│   ├── claude.py
│   └── router.py          # "provider/model_id" 路由
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
