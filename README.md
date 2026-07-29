# Jarvis

基于 LangGraph 构建的 LLM 智能助手后端服务。支持工具链（在线搜索、网页抓取）、跨会话记忆、RAG 检索增强和自评分反思机制，同时暴露 FastAPI（HTTP）和 gRPC 两套接口。

## 核心能力

- **可编排 Agent 工作流**：通过 LangGraph 串联记忆加载、领域 Agent 分发、
  RAG、工具调用、反思重试和持久化。
- **多供应商 LLM Gateway**：使用 Profile 统一管理 DeepSeek、OpenAI-compatible
  和 Anthropic 协议，支持请求级模型覆盖、能力校验和有界重试。
- **跨会话记忆与知识库**：PostgreSQL 保存对话历史，Qdrant 提供向量检索和
  工具结果知识沉淀。
- **双协议服务**：同时提供 FastAPI HTTP 与 gRPC 接口。
- **启动前模型检查**：仅检查 Profiles 实际引用的 Chat 供应商，并检查当前
  Embedding 模型的连通性和凭据有效性。
- **面向运维的可观测性**：INFO/WARN/ERROR 彩色显示，关键字段使用
  `【类别:值】` 标签，并提供独立的存活与就绪探针。

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

HTTP 服务默认监听 `0.0.0.0:8080`，gRPC 使用明文监听 `[::]:9090`，并非只
绑定 localhost。当前应用没有鉴权或 TLS；启动前应通过防火墙、私网或可信
反向代理隔离访问。

## 启动配置与连通性检查

Jarvis 在绑定 HTTP/gRPC 端口前检查凭据配置并执行模型连通性检查：

- 检查当前生效的 Chat、Embedding 及注册工具声明的 API Key 环境变量。已配置
  使用 `INFO`，未配置使用 `WARNING`；日志只包含环境变量名称和状态，不包含值。
- 扫描 `llm.yaml` 的 `profiles`，对每个实际引用的 Chat 供应商执行一次真实
  模型请求；多个 Profile 引用同一供应商时只检查一次。缺少对应凭据时跳过真实
  请求，避免发送无效鉴权。
- 对 `EMBED_MODEL` 指定的 Embedding 模型执行一次真实向量请求。默认配置因此
  会检查 DeepSeek Chat 和 SiliconFlow Embedding；缺少 Embedding 凭据时跳过
  探测，聊天流程沿用现有的无 RAG 降级。
- 工具只执行凭据存在性检查，不在启动阶段产生搜索等外部请求。缺少工具凭据时，
  该工具不会提供给大模型，其余对话能力不受影响。
- 单次探测使用 10 秒请求超时，Embedding 探测关闭 SDK 重试。探测会产生少量
  API 用量，并可能延迟端口开始监听。
- 失败按 `credential`、`timeout`、`connectivity`、`configuration` 等稳定类别
  记录，日志不会包含 API Key、供应商响应正文或完整异常详情。
- 模型检查失败不会阻止服务继续启动；PostgreSQL 或 Qdrant 初始化失败仍会阻止
  HTTP/gRPC 开始监听。

启动检查只覆盖当前生效配置，不会遍历 `llm.yaml` 中未被 Profile 引用的 Chat
供应商。Embedding 不属于 Chat Profiles，因此始终按当前 `EMBED_MODEL` 单独
检查。

## 日志与可观测性

默认日志等级使用颜色突出显示：

| 等级 | 终端颜色 | 典型用途 |
|------|----------|----------|
| `INFO` | 绿色 | 启动成功、Agent 选择、服务就绪 |
| `WARN` | 黄色 | 请求重试、节点降级、可恢复异常 |
| `ERROR` | 红色 | 凭据无效、供应商不可用、配置错误 |

不需要 ANSI 颜色时，可设置标准环境变量 `NO_COLOR`：

```bash
NO_COLOR=1 python jarvis/main.py
```

关键日志采用连续的 `【类别:值】` 标签，标签值保留配置和代码中的原始标识：

```text
【供应商:deepseek】【模型:deepseek-v4-pro】【类型:Chat】【结果:成功】 Startup connectivity check completed
【组件:web_search】【类型:Tool】【配置:TAVILY_API_KEY】【状态:未配置】 Required credential is not configured
【节点:agent_dispatch】【Agent:ai-agent-mentor】【评分:0.86】 Agent selected
【节点:rag_retrieve】【组件:Qdrant】【状态:降级】【错误:ResponseHandlingException】 Retrieval unavailable
【节点:tool_node】【工具:web_search】【状态:降级】【类别:credential】 Tool unavailable
【服务:gRPC】【端口:9090】【状态:就绪】 Server listening
```

可以使用完整标签快速定位，不依赖英文正文：

```bash
kubectl logs deployment/jarvis | grep -F '【供应商:deepseek】'
kubectl logs deployment/jarvis | grep -F '【节点:agent_dispatch】'
kubectl logs deployment/jarvis | grep -F '【组件:Qdrant】'
```

标签只包含供应商名、模型 ID、节点、组件、评分、状态和错误类型等稳定元数据，
不会记录 API Key、完整用户输入、完整模型响应或供应商异常正文。Uvicorn 的普通
访问日志保持原格式。

## 健康检查

健康端点不调用 LLM、Embedding、PostgreSQL 或 Qdrant，不会额外产生模型费用：

| Endpoint | 成功响应 | 未就绪/失败 | 用途 |
|----------|----------|-------------|------|
| `GET /health/live` | `200 {"status":"ok"}` | 进程不可访问 | 判断进程是否存活 |
| `GET /health/ready` | `200 {"status":"ready"}` | `503 {"detail":"not ready"}` | 判断启动初始化是否完成 |

Docker `HEALTHCHECK` 使用 `/health/live`。Kubernetes readinessProbe 使用
`/health/ready`，livenessProbe 使用 `/health/live`。这两个路径的
`uvicorn.access` 日志会被过滤，避免周期性探针刷屏；`/docs`、`/chat` 等普通
访问日志仍会正常保留。

## Kubernetes 部署

[`jarvis.yaml`](jarvis.yaml) 定义 ConfigMap、Deployment、Service 和专用健康
探针，镜像来自
`registry.cn-hangzhou.aliyuncs.com/lexmargin/jarvis:latest`。

清单引用的 `jarvis-secrets` 必须通过集群的安全凭据流程预先创建。不要把真实
API Key、数据库密码、Token 或 kubeconfig 写入 `jarvis.yaml`、`llm.yaml` 或
Git 提交。凭据准备完成后可应用清单：

```bash
kubectl apply -f jarvis.yaml
kubectl rollout status deployment/jarvis --timeout=180s
```

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

新增工具只需在 `jarvis/tools/` 下创建文件并使用 `@register_tool` 装饰器。
需要凭据的工具通过 `required_env_vars` 声明：

```python
from jarvis.tools.registry import register_tool

@register_tool(
    name="my_tool",
    description="工具描述",
    required_env_vars=("MY_TOOL_API_KEY",),
)
def my_tool(input: str) -> str:
    return "结果"
```

在 `jarvis/agent/graph.py` 顶部 import 该模块即可自动注册，无需修改图逻辑。
未配置声明的环境变量时，工具会自动从模型能力列表中移除。外部工具运行时遇到
鉴权失败、超时、连接失败或服务端 `5xx`，会记录脱敏 `WARNING`，在当前请求内
禁用该工具并让大模型直接回答；无效参数和程序错误仍会抛出。

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
├── logging_config.py      # 彩色等级、关键标签与健康访问日志过滤
├── main.py                # 服务入口（并行启动 HTTP + gRPC）
├── startup_checks.py      # 启动凭据审计及 Chat/Embedding 真实探测
├── llm/                   # Profile Gateway 与协议 Adapter
│   ├── config.py          # llm.yaml 类型化加载
│   ├── gateway.py         # 统一 chat、能力、裁剪、重试与错误归一化
│   ├── errors.py          # 安全的 LLM 异常层
│   ├── adapters/          # DeepSeek / OpenAI-compatible / Anthropic
│   └── router.py          # 仅保留旧 raw-model API 兼容
├── tools/
│   ├── registry.py        # 工具注册、凭据依赖与可用性过滤
│   ├── errors.py          # 可安全降级的工具异常
│   ├── search.py          # Tavily 搜索
│   └── scraper.py         # BeautifulSoup 抓取
├── memory/
│   ├── conversation.py    # PostgreSQL 对话历史
│   └── knowledge.py       # Qdrant 向量知识库
├── agent/
│   ├── state.py           # AgentState TypedDict
│   ├── graph.py           # LangGraph 图定义
│   └── nodes/             # 节点实现（含请求级安全工具执行）
├── agents/
│   ├── __init__.py        # AgentDefinition dataclass
│   ├── loader.py          # 扫描目录，解析 agent.json/yaml/SKILL.md
│   └── dispatcher.py      # LLM 语义评分 + 阈值决策
└── api/
    ├── http/routes.py     # FastAPI endpoints
    └── grpc/              # gRPC server + servicer + proto
```
