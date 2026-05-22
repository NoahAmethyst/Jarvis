# Jarvis — LLM 智能助手设计文档

**日期：** 2026-05-22  
**状态：** 已确认

---

## 1. 项目概述

基于 LangGraph 构建的 LLM 智能助手后端服务，具备工具链、Memory、RAG 和 Self-critique Reflection 机制。对外同时暴露 FastAPI（HTTP）和 gRPC 两套接口，供上层应用接入。

**核心使用场景：**
- 个人知识管理 + 问答（文档检索、知识总结）
- 任务自动化（搜索、抓取、第三方 API 调用）

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────┐
│          API Layer（HTTP :8080 / gRPC :9090）         │
└──────────────────────┬──────────────────────────────┘
                       │
             ┌─────────▼──────────┐
             │   LangGraph Agent  │
             │                    │
             │  [memory_load]     │  ← 加载对话历史 + 用户档案
             │       ↓            │
             │  [rag_retrieve]    │  ← Qdrant 检索相关知识
             │       ↓            │
             │  [plan_and_call]   │  ← LLM 决策：调工具 or 直接回答
             │       ↓            │
             │  [tool_node]       │  ← 搜索 / 抓取 / 第三方 API
             │       ↓            │
             │  [reflect]         │  ← 自评分，不通过则循环回 plan
             │       ↓            │
             │  [memory_write]    │  ← 写对话历史；重要知识→Qdrant
             └────────┬───────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
      Qdrant       PostgreSQL    Tool Registry
   (向量知识库)   (对话历史/元数据)  (可插拔工具)
```

---

## 3. 目录结构

```
jarvis/
├── api/
│   ├── http/
│   │   └── routes.py              # FastAPI endpoints
│   └── grpc/
│       ├── server.py              # gRPC server 入口
│       ├── jarvis.proto           # 服务定义
│       └── servicer.py            # proto service 实现
├── agent/
│   ├── graph.py                   # LangGraph 图定义（节点 + 边）
│   ├── state.py                   # AgentState TypedDict
│   └── nodes/
│       ├── memory_load.py
│       ├── rag_retrieve.py
│       ├── plan_and_call.py
│       ├── reflect.py
│       └── memory_write.py
├── llm/
│   ├── base.py                    # BaseLLMProvider 抽象接口
│   ├── siliconflow.py             # SiliconFlow provider
│   ├── openai.py                  # OpenAI provider
│   ├── claude.py                  # Anthropic Claude provider
│   └── router.py                  # "provider/model_id" 解析 + 路由
├── tools/
│   ├── registry.py                # @register_tool 装饰器 + 注册中心
│   ├── search.py                  # 在线搜索（Tavily / SerpAPI）
│   ├── scraper.py                 # 网页抓取（Firecrawl / BeautifulSoup）
│   └── third_party/               # 第三方服务（按需扩展）
├── memory/
│   ├── conversation.py            # PostgreSQL 对话历史读写
│   └── knowledge.py               # Qdrant 向量知识读写 + 自动入库
├── config.py                      # 环境变量、模型配置
├── main.py                        # 服务入口（并行启动 HTTP + gRPC）
└── tests/
    ├── unit/
    │   ├── test_llm_router.py
    │   ├── test_reflect_node.py
    │   └── test_tool_registry.py
    ├── integration/
    │   ├── test_graph_flow.py
    │   └── test_rag_pipeline.py
    └── e2e/
        └── test_api.py
```

---

## 4. AgentState

```python
class AgentState(TypedDict):
    messages: list[BaseMessage]      # 完整对话历史（本次会话）
    user_id: str                     # 用于隔离多用户 Memory
    rag_context: str                 # 检索到的知识片段
    tool_results: list[dict]         # 工具执行结果
    reflection_score: float          # 自评分 0.0-1.0
    retry_count: int                 # 已重试次数（上限 3）
    final_answer: str                # 最终输出
```

---

## 5. LLM Provider 层

### 抽象接口

```python
class BaseLLMProvider(ABC):
    @abstractmethod
    def get_chat_model(self, **kwargs) -> BaseChatModel: ...
```

### 支持的 Provider

| Provider | 实现文件 | 底层 LangChain 类 |
|----------|---------|-----------------|
| siliconflow | `llm/siliconflow.py` | `ChatOpenAI`（自定义 base_url）|
| openai | `llm/openai.py` | `ChatOpenAI` |
| claude | `llm/claude.py` | `ChatAnthropic` |

### 路由格式

`"provider/model_id"` 例：`"siliconflow/Qwen3-14B"`、`"claude/claude-opus-4-7"`

### 错误处理

```python
# provider 不存在
logger.error(f"Provider not found: {provider_name}")
raise ProviderNotFoundError("provider not exist")
# → HTTP 400 / gRPC INVALID_ARGUMENT

# provider 不可用
logger.error(f"Provider unavailable: {provider_name}, reason: {e}")
raise ProviderUnavailableError(f"provider not working:{e}")
# → HTTP 502 / gRPC UNAVAILABLE
```

### 默认模型配置（config.py）

```python
ANSWER_LLM  = "siliconflow/deepseek-ai/DeepSeek-V4-Pro"   # 主模型，生成回答
REFLECT_LLM = "siliconflow/moonshotai/Kimi-K2.6"          # 评分模型
```

---

## 6. Reflection 机制

```
生成答案
  → REFLECT_LLM 评分（prompt 包含：准确性 / 完整性 / 是否回答原始问题）
  → score < 0.7 且 retry_count < 3  →  返回 plan_and_call 重规划
  → score ≥ 0.7 或 retry_count == 3 →  进入 memory_write
     （retry_count == 3 时附加 low_confidence: true 标记）
```

---

## 7. 知识自动入库

`memory_write` 节点判断：工具返回内容来自搜索/抓取且长度 > 200 字 → 自动 embed 存入 Qdrant，元数据包含 `source_url`、`timestamp`、`user_id`。

Embedding 模型通过环境变量 `EMBED_MODEL` 配置（默认 `siliconflow/Qwen/Qwen3-Embedding-8B`），调用 SiliconFlow Embeddings API，接口与 OpenAI Embeddings 兼容。

---

## 8. 工具扩展机制

```python
# 新增工具只需：
@register_tool(name="my_tool", description="...")
def my_tool(input: str) -> str: ...
```

`tool_node` 通过 `registry.get_tools()` 动态加载，图逻辑无需修改。

---

## 9. API 接口

### HTTP（FastAPI，默认端口 8080）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 主对话 |
| POST | `/ingest` | 手动上传文档入知识库 |
| GET | `/memory/{uid}` | 查看用户对话历史 |
| DELETE | `/memory/{uid}` | 清除用户记忆 |

**POST /chat 请求体：**
```json
{
  "message": "...",
  "user_id": "...",
  "llm": "claude/claude-opus-4-7",      // 可选，覆盖默认 ANSWER_LLM
  "reflect_llm": "openai/gpt-4o-mini"   // 可选，覆盖默认 REFLECT_LLM
}
```

### gRPC（默认端口 9090）

```protobuf
service JarvisService {
  rpc Chat(ChatRequest) returns (ChatResponse);
  rpc Ingest(IngestRequest) returns (IngestResponse);
  rpc GetMemory(MemoryRequest) returns (MemoryResponse);
  rpc DeleteMemory(MemoryRequest) returns (DeleteResponse);
}
```

HTTP 和 gRPC 共用同一 `agent/graph.py`，`main.py` 并行启动两个 server。

---

## 10. 端口与环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `HTTP_PORT` | `8080` | FastAPI 监听端口 |
| `GRPC_PORT` | `9090` | gRPC 监听端口 |
| `ANSWER_LLM` | `siliconflow/deepseek-ai/DeepSeek-V4-Pro` | 主模型 |
| `REFLECT_LLM` | `siliconflow/moonshotai/Kimi-K2.6` | 评分模型 |
| `QDRANT_URL` | — | Qdrant 连接地址 |
| `POSTGRES_DSN` | — | PostgreSQL 连接串 |
| `EMBED_MODEL` | `siliconflow/Qwen/Qwen3-Embedding-8B` | 知识库 Embedding 模型 |

---

## 11. 降级策略

| 组件不可用 | 降级行为 |
|-----------|---------|
| Qdrant | 跳过 RAG，纯对话继续，记录告警 |
| PostgreSQL | 内存临时存储当前会话，会话结束丢弃 |
| 工具执行失败 | 捕获异常写入 `tool_results`，LLM 基于失败信息重规划 |
| LLM API 超时/限速 | 指数退避重试 3 次，失败返回 503 |

---

## 12. 测试策略

- **单元测试**：LLM 调用全部 mock，覆盖 router 路由、reflect 阈值、工具注册
- **集成测试**：真实 Qdrant（Docker），验证完整 LangGraph 流程和 RAG 管线
- **E2E 测试**：FastAPI TestClient 验证所有 HTTP endpoints；gRPC 用 `grpc_testing` 验证所有 rpc 方法
