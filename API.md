# Jarvis API 接入文档

本文档面向需要接入 Jarvis 的其他项目和负责实现接入的 Codex Agent。
内容以当前仓库实现为准，覆盖 HTTP 与 gRPC 接口、错误处理、调用示例和
接入约束。

## 1. 接口概览

Jarvis 同时提供 HTTP 和 gRPC 两套同步接口：

| 协议 | 本机客户端示例 | 服务默认监听 | 接口 |
|---|---|---|---|
| HTTP | `http://localhost:8080` | `0.0.0.0:8080` | `/chat`、`/ingest`、`/memory/{uid}` |
| gRPC | `localhost:9090` | `[::]:9090` | `Chat`、`Generate`、`Ingest`、`GetMemory`、`DeleteMemory` |

`localhost` 只是同机客户端示例，不代表服务只监听 loopback。默认进程绑定
全网卡，仓库中的 Kubernetes Service 还使用 NodePort；在没有应用鉴权和 TLS
的当前状态下，启动前必须通过防火墙、私网或可信反向代理隔离访问。

生产环境的域名、TLS 和端口由部署方提供。接入项目不要硬编码示例地址，建议
分别使用环境变量：

```dotenv
JARVIS_HTTP_BASE_URL=http://localhost:8080
JARVIS_GRPC_TARGET=localhost:9090
```

当前接口版本为 `0.1.0`，HTTP 路径尚未增加 `/v1` 版本前缀。

## 2. 重要接入约束

> **生产阻塞：默认 `web_scrape` 工具存在 SSRF 风险。** 当前工具会将模型生成
> 的任意 URL 直接交给 `requests.get()`，没有校验协议、DNS 解析结果、私网、
> loopback、link-local、云元数据地址或重定向目标。返回内容还可能进入模型
> 回答，并在超过知识长度阈值时写入 Qdrant。面向不可信用户或公网开放前，
> 必须禁用该工具，或完成逐次解析/重定向校验并配置网络层 egress allowlist
> 或受控代理。还必须使用流式硬字节/解压后上限、Content-Type 白名单、总
> deadline、重定向次数和抓取并发限制，防止巨大响应、压缩膨胀和慢速响应耗尽
> worker。鉴权、TLS 和 `user_id` 校验不能替代这些防护。
>
> 当前没有单独关闭 `web_scrape` 的运行时开关。将 `answer.tools` 设为
> `disabled` 会关闭全部工具；如需保留其他工具，必须增加服务端工具 allowlist
> 或停止在 `jarvis/agent/graph.py` 中注册 scraper。

- HTTP 请求和响应使用 UTF-8 JSON；发送 JSON 时设置
  `Content-Type: application/json`。
- HTTP `/chat` 与所有 gRPC RPC 都是同步 unary 调用，不支持 SSE、
  WebSocket、流式 Token 或流式 gRPC。
- `/chat` 可能执行 RAG、工具调用和最多多轮回答反思，客户端应使用可配置且
  明显长于普通 REST 请求的超时，不要使用过短的默认超时。
- gRPC `Generate` 是一次性生成接口，不加载或写入 PostgreSQL 对话历史，也不
  进入 LangGraph 反思、工具调用或 RAG 流程。需要严格机器可解析输出的调用方
  应优先使用 `Generate`，避免被历史对话格式污染。
- 当前应用层没有 API Key、JWT、Session 或租户鉴权。
- `user_id` 直接决定对话历史和知识数据的隔离范围。调用方必须生成稳定、
  不可由其他用户任意冒用的标识，并在对外暴露 Jarvis 前通过网关补充鉴权和
  `user_id` 所有权校验。
- HTTP memory 路由只接受单个 path segment。`user_id` 不得包含 `/`，
  即使编码为 `%2F` 也无法匹配当前路由。建议限制为
  `^[A-Za-z0-9._:@-]+$`，并继续对 path 参数进行 URL 编码。
- 应用本身没有配置 CORS 中间件。浏览器跨域直连需要由反向代理提供同源转发，
  或在服务端明确增加 CORS 策略。
- HTTP 提供 `/health/live` 和 `/health/ready` 两个专用健康接口。
  健康探针不得使用 `/docs`，也不得在周期探测中调用 LLM、数据库、
  Qdrant 或其他外部服务。
- gRPC 当前使用明文监听，且没有启用 Server Reflection。生产环境的 TLS 和
  访问控制应由部署层提供。
- HTTP 字段目前没有长度限制，应用层也没有请求体、频率或并发限制。公网接入
  前必须在 Jarvis 或可信网关实施字段长度、请求体大小、速率和并发上限；
  客户端自我校验不构成服务端资源保护。
- 接入方不得依赖未声明字段、内部 LangGraph 状态或数据库结构。

## 3. HTTP API

### 3.1 OpenAPI

服务启动后可访问：

| 地址 | 用途 |
|---|---|
| `GET /openapi.json` | OpenAPI 3 Schema，适合 Codex 检查运行版本 |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc |

`API.md` 记录语义和运维约束，`/openapi.json` 记录运行版本的机器可读
Schema。当前 OpenAPI 并不完整：只有 `/chat` 声明了 200 响应模型；
`/ingest`、`GET /memory/{uid}` 和 `DELETE /memory/{uid}` 的 200 响应
Schema 是空对象，业务错误状态也未声明。生成客户端后必须按本文档补充类型和
错误处理，不能只依赖 OpenAPI。

### 3.2 接口清单

| 方法 | 路径 | 用途 | 成功状态 |
|---|---|---|---|
| `GET` | `/health/live` | 进程存活检查，不访问外部依赖 | `200` |
| `GET` | `/health/ready` | 启动初始化完成检查 | `200` |
| `POST` | `/chat` | 发起一次对话 | `200` |
| `POST` | `/ingest` | 写入用户私有知识 | `200` |
| `GET` | `/memory/{uid}` | 获取用户对话历史 | `200` |
| `DELETE` | `/memory/{uid}` | 删除用户对话历史 | `200` |

`/health/ready` 在启动初始化完成前返回 `503 {"detail":"not ready"}`。
两个健康接口都不访问 LLM、PostgreSQL、Qdrant 或其他外部依赖。

### 3.3 POST `/chat`

发起一次完整的 Jarvis Agent 执行。服务会按 `user_id` 加载最多 20 条历史
消息，执行 Agent 选择、RAG、模型回答、可选工具调用和回答反思，然后保存
本轮用户消息及非工具 AI 回答。

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `message` | `string` | 是 | 当前用户消息 |
| `user_id` | `string` | 是 | 对话历史与知识空间的隔离键 |
| `llm` | `string \| null` | 否 | 回答模型覆盖，格式为 `provider/model_id` |
| `reflect_llm` | `string \| null` | 否 | Reflection 与 Agent dispatch 模型覆盖 |

当前 Schema 没有为字符串配置最小长度或最大长度。客户端应保证 `message`
和 `user_id` 非空；服务端或可信网关还必须强制长度、请求体、频率和并发
限制，不能只依赖正常客户端主动限制。

不传覆盖字段时，服务使用 `llm.yaml` 中的 Profile。覆盖值引用的 Provider
必须已在服务端配置并具备相应 API Key：

```json
{
  "message": "请总结我们之前讨论的部署风险。",
  "user_id": "tenant-a:user-42",
  "llm": "deepseek/deepseek-v4-pro",
  "reflect_llm": "deepseek/deepseek-v4-flash"
}
```

回答模型必须支持工具调用。如果覆盖模型不支持 thinking，服务可以按
`answer` Profile 的策略关闭 thinking；不支持工具调用则请求失败。普通接入
项目建议不传模型覆盖字段，由 Jarvis 服务端统一控制模型。

#### 成功响应

```json
{
  "answer": "需要关注配置密钥、镜像版本和回滚路径。",
  "low_confidence": false
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `answer` | `string` | 最终回答 |
| `low_confidence` | `boolean` | 达到最大反思次数后，最终评分是否仍低于阈值 |

`low_confidence: false` 不等于事实保证；调用方仍应按业务风险决定是否进行
人工审核。

#### cURL

```bash
curl --request POST "${JARVIS_HTTP_BASE_URL}/chat" \
  --header "Content-Type: application/json" \
  --data '{
    "message": "LangGraph 是什么？",
    "user_id": "tenant-a:user-42"
  }'
```

### 3.4 POST `/ingest`

将一段文本写入指定用户的 Qdrant 知识空间。后续同一 `user_id` 的 `/chat`
请求可通过 RAG 检索该内容。

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `content` | `string` | 是 | 要向量化并保存的完整文本 |
| `source_url` | `string` | 是 | 来源标识；当前实现不强制必须是合法 URL |
| `user_id` | `string` | 是 | 知识空间隔离键 |

```json
{
  "content": "退款申请应在订单完成后的七天内提交。",
  "source_url": "https://example.com/policies/refund",
  "user_id": "tenant-a:user-42"
}
```

#### 成功响应

```json
{
  "success": true
}
```

知识点 ID 当前由 `user_id`、`source_url` 和 `content` 使用冒号拼接后哈希并
截断生成。使用完全相同的三项内容重复调用会覆盖同一个知识点，但这不是严格的
唯一性保证：未经转义的跨字段冒号可能让不同三元组得到同一拼接值，截断哈希
本身也存在理论碰撞；Qdrant upsert 会覆盖该 Point。调用方不能把当前 Point ID
当作跨用户数据完整性边界。当前接口不会自动切分长文档，也没有批量写入接口，
调用方应自行按语义段落切分后逐段提交。

### 3.5 GET `/memory/{uid}`

按创建时间升序返回用户的全部 PostgreSQL 对话记录。当前接口不分页。

```bash
curl "${JARVIS_HTTP_BASE_URL}/memory/tenant-a%3Auser-42"
```

#### 成功响应

```json
[
  {
    "role": "human",
    "content": "LangGraph 是什么？",
    "created_at": "2026-07-28 10:30:00"
  },
  {
    "role": "ai",
    "content": "LangGraph 是一个用于构建有状态 Agent 工作流的框架。",
    "created_at": "2026-07-28 10:30:08"
  }
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `role` | `string` | 当前写入值为 `human` 或 `ai` |
| `content` | `string` | 消息文本 |
| `created_at` | `string` | PostgreSQL 时间戳文本；不要假设包含时区 |

没有历史记录时返回空数组 `[]`。调用方不要把 `role` 假设为 OpenAI 消息协议
中的 `user` 或 `assistant`。

### 3.6 DELETE `/memory/{uid}`

删除指定用户的全部 PostgreSQL 对话历史：

```bash
curl --request DELETE \
  "${JARVIS_HTTP_BASE_URL}/memory/tenant-a%3Auser-42"
```

#### 成功响应

```json
{
  "success": true
}
```

此接口只删除对话历史，不删除 Qdrant 中通过 `/ingest` 或长工具结果写入的
用户知识。当前项目尚未提供知识查询、知识删除或“删除用户全部数据”接口。

### 3.7 HTTP 错误

FastAPI 已处理的错误响应通常使用：

```json
{
  "detail": "error message"
}
```

缺少字段或字段类型错误时返回 `422`，`detail` 为 FastAPI 标准校验错误数组。

`/chat` 对已归一化的 LLM 错误采用以下映射：

| HTTP 状态 | 含义 | 客户端建议 |
|---|---|---|
| `400` | 模型规格、请求或上下文长度无效 | 修正请求，不要原样重试 |
| `429` | 模型供应商限流 | 仅在业务接受重复执行时退避重试 |
| `500` | Jarvis LLM 配置无效或内部错误 | 记录请求上下文并联系服务维护方 |
| `502` | 模型供应商返回无效响应 | 仅在业务接受重复执行时有限重试 |
| `503` | 模型供应商暂不可用 | 业务允许时退避重试或降级 |
| `504` | 模型调用超时 | 不默认重试；先处理结果未知风险 |

`/chat` 的已归一化 LLM 错误使用稳定、脱敏的公开消息。`/ingest` 和
`/memory` 当前会把捕获异常的 `str(e)` 放入 `500 detail`，这些错误文本
可能包含内部实现或敏感信息，不能视为安全、稳定的公开契约，也不应写入日志、
APM、UI 或下游响应。

各接口的重试语义不同：

1. 先按 HTTP 状态判断成功或失败，不依赖错误文本做程序分支。
2. `GET /memory/{uid}` 和 `DELETE /memory/{uid}` 可以安全重试。
3. `/ingest` 使用确定性知识点 ID；完全相同的
   `user_id + source_url + content` 可以覆盖式重试。
4. `/chat` 没有幂等键。客户端超时、连接断开等“结果未知”错误不得默认
   自动重试，否则可能重复执行模型/工具并追加重复历史。只有业务明确接受
   重复执行或自行实现去重时，才对可恢复状态进行有上限的退避重试。
5. 不自动重试 `400`、`422`，不在日志中记录错误响应正文、敏感请求正文、
   密钥或完整用户对话。

## 4. HTTP 客户端示例

### 4.1 Python

```python
import os
from urllib.parse import quote

import httpx


class JarvisClient:
    def __init__(self) -> None:
        self.base_url = os.environ["JARVIS_HTTP_BASE_URL"].rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0),
        )

    def chat(self, message: str, user_id: str) -> dict:
        response = self.client.post(
            "/chat",
            json={"message": message, "user_id": user_id},
        )
        response.raise_for_status()
        return response.json()

    def ingest(self, content: str, source_url: str, user_id: str) -> None:
        response = self.client.post(
            "/ingest",
            json={
                "content": content,
                "source_url": source_url,
                "user_id": user_id,
            },
        )
        response.raise_for_status()

    def memory(self, user_id: str) -> list[dict]:
        encoded_user_id = quote(user_id, safe="")
        response = self.client.get(f"/memory/{encoded_user_id}")
        response.raise_for_status()
        return response.json()
```

示例中的 120 秒只是客户端起点，不是服务 SLA。生产值应根据模型、工具调用、
反向代理和业务等待策略共同确定。

### 4.2 TypeScript

```typescript
type ChatResponse = {
  answer: string;
  low_confidence: boolean;
};

const baseUrl = process.env.JARVIS_HTTP_BASE_URL!.replace(/\/$/, "");

export async function chat(
  message: string,
  userId: string,
): Promise<ChatResponse> {
  const response = await fetch(`${baseUrl}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message, user_id: userId }),
    signal: AbortSignal.timeout(120_000),
  });

  if (!response.ok) {
    throw new Error(`Jarvis request failed with status ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}
```

服务端项目应进一步封装结构化错误、按接口区分的重试、日志脱敏和调用指标。
不要把非 2xx 响应正文直接拼入异常或日志。浏览器项目不要在前端直接信任或
传入任意 `user_id`。

## 5. gRPC API

Proto 源文件：

```text
jarvis/api/grpc/jarvis.proto
```

Proto package 为 `jarvis`，完整服务名为：

```text
jarvis.JarvisService
```

### 5.1 RPC 清单

| RPC | 请求 | 响应 | HTTP 对应接口 |
|---|---|---|---|
| `Chat` | `ChatRequest` | `ChatResponse` | `POST /chat` |
| `Generate` | `GenerateRequest` | `GenerateResponse` | 无 |
| `Ingest` | `IngestRequest` | `IngestResponse` | `POST /ingest` |
| `GetMemory` | `MemoryRequest` | `MemoryResponse` | `GET /memory/{uid}` |
| `DeleteMemory` | `MemoryRequest` | `DeleteResponse` | `DELETE /memory/{uid}` |

### 5.2 Proto 定义

```protobuf
syntax = "proto3";

package jarvis;

service JarvisService {
  rpc Chat(ChatRequest) returns (ChatResponse);
  rpc Generate(GenerateRequest) returns (GenerateResponse);
  rpc Ingest(IngestRequest) returns (IngestResponse);
  rpc GetMemory(MemoryRequest) returns (MemoryResponse);
  rpc DeleteMemory(MemoryRequest) returns (DeleteResponse);
}

message ChatRequest {
  string message = 1;
  string user_id = 2;
  string llm = 3;
  string reflect_llm = 4;
}

message ChatResponse {
  string answer = 1;
  bool low_confidence = 2;
}

message GenerateRequest {
  string prompt = 1;
  string user_id = 2;
  string llm = 3;
  string operation = 4;
}

message GenerateResponse {
  string text = 1;
}

message IngestRequest {
  string content = 1;
  string source_url = 2;
  string user_id = 3;
}

message IngestResponse {
  bool success = 1;
}

message MemoryRequest {
  string user_id = 1;
}

message MemoryResponse {
  repeated ConversationEntry entries = 1;
}

message ConversationEntry {
  string role = 1;
  string content = 2;
  string created_at = 3;
}

message DeleteResponse {
  bool success = 1;
}
```

`Generate` 只执行一次 `answer` Profile LLM 调用，`prompt` 作为唯一用户消息
发送，`llm` 可按 `provider/model_id` 覆盖模型，`operation` 只用于服务端日志
定位，不会传入模型。该 RPC 不加载、不保存 conversation history，也不使用
知识库或工具；适合日报章节、结构化 JSON、固定 marker 等机器可解析输出。

`proto3` 的未设置字符串字段在服务端表现为空字符串。虽然协议层不会报告
“缺少必填字段”，客户端仍应保证 `message`、`prompt`、`user_id`、`content`
和 `source_url` 等业务必填值非空。

gRPC Server 没有覆盖 grpcio 的默认接收消息大小，序列化后的整个请求不能
超过 4 MiB。长内容应按语义分块并为 protobuf 字段开销预留空间；超限请求在
进入 `Ingest` 方法前就会收到传输层 `RESOURCE_EXHAUSTED`。

gRPC Core 的默认接收上限也适用于客户端。Python 默认 Channel 接收超过
4 MiB 的 `ChatResponse` 或无分页 `MemoryResponse` 时同样会收到
`RESOURCE_EXHAUSTED`。接入方应优先限制历史规模；过渡期可与部署方约定一个
有界的客户端接收上限，不能设置为无限制。

### 5.3 grpcurl

服务器没有启用 Reflection，因此调用时需要提供 Proto：

```bash
grpcurl -plaintext \
  -import-path ./jarvis/api/grpc \
  -proto jarvis.proto \
  -d '{"message":"LangGraph 是什么？","user_id":"tenant-a:user-42"}' \
  "${JARVIS_GRPC_TARGET}" \
  jarvis.JarvisService/Chat
```

一次性生成示例：

```bash
grpcurl -plaintext \
  -import-path ./jarvis/api/grpc \
  -proto jarvis.proto \
  -d '{"prompt":"请严格输出 5 个章节 marker。","user_id":"go-cqhttp:wallstreet","operation":"wallstreet_summary_v2"}' \
  "${JARVIS_GRPC_TARGET}" \
  jarvis.JarvisService/Generate
```

生产环境是否使用 `-plaintext` 取决于部署层是否启用 TLS。

### 5.4 Python Stub

将 `jarvis.proto` 复制到接入项目的 `proto/` 后生成 Stub：

```bash
python -m grpc_tools.protoc \
  -I ./proto \
  --python_out=. \
  --grpc_python_out=. \
  ./proto/jarvis.proto
```

```python
import os

import grpc
import jarvis_pb2
import jarvis_pb2_grpc


max_response_bytes = int(
    os.getenv("JARVIS_GRPC_MAX_RECEIVE_BYTES", str(8 * 1024 * 1024))
)
channel = grpc.insecure_channel(
    os.environ["JARVIS_GRPC_TARGET"],
    options=(("grpc.max_receive_message_length", max_response_bytes),),
)
client = jarvis_pb2_grpc.JarvisServiceStub(channel)

response = client.Chat(
    jarvis_pb2.ChatRequest(
        message="LangGraph 是什么？",
        user_id="tenant-a:user-42",
    ),
    timeout=120,
)
print(response.answer, response.low_confidence)
```

示例将客户端接收上限显式设为 8 MiB，这只是有界示例，不是服务 SLA。生产值
应与部署方协商。启用 TLS 时应改用 `grpc.secure_channel` 和部署方提供的
证书配置。

### 5.5 gRPC 状态码

`Chat` 和 `Generate` 对 LLM 错误采用以下映射：

| gRPC 状态 | 含义 |
|---|---|
| `INVALID_ARGUMENT` | 请求或上下文长度无效 |
| `FAILED_PRECONDITION` | Jarvis LLM 配置无效 |
| `RESOURCE_EXHAUSTED` | 模型限流，或请求/客户端响应超过接收方的 gRPC 上限 |
| `DEADLINE_EXCEEDED` | 模型调用超时 |
| `UNAVAILABLE` | 模型供应商不可用 |
| `INTERNAL` | 已归一化的模型响应无效错误，或 Jarvis 捕获到的未预期内部异常 |

`Ingest`、`GetMemory` 和 `DeleteMemory` 进入 Servicer 后的内部失败当前
统一返回 `INTERNAL`；超过 4 MiB 等传输层失败不经过这套映射。只有标准化
LLM 错误以及 `Chat`、`Generate` 未预期异常的详情经过脱敏，其他 gRPC error
details 可能包含原始异常文本，不应记录或转发。重试策略应按 RPC 的幂等性
区分，并同时尊重客户端 deadline。

## 6. 数据与会话语义

### 6.1 `user_id`

同一 `user_id` 关联两个独立存储域：

- PostgreSQL 对话历史：由 `/chat` 写入，由 `/memory/{uid}` 查询或删除。
- Qdrant 知识：由 `/ingest` 和符合长度条件的工具结果写入，供 `/chat` 检索。

建议接入方使用符合 `^[A-Za-z0-9._:@-]+$` 的 `tenant_id:user_id` 或不可逆
内部 ID，避免不同租户碰撞。切勿直接信任浏览器提交的 `user_id`。如果
`/chat` 或 `/ingest` 写入了包含 `/` 的 ID，当前 HTTP memory 路由将无法查询
或删除对应对话。

### 6.2 对话记忆

- 每次 `/chat` 加载该用户最近 20 条对话消息作为上下文。
- `/memory/{uid}` 返回全部记录，不受 20 条加载限制影响。
- Tool call、ToolMessage 和模型 reasoning 不作为结构化对话历史持久化。
- 本轮所有没有 tool call 的 AIMessage 都会写入历史，包括反思低分后被后续
  回答替代的草稿。因此一次 `/chat` 可能产生连续多条 `ai` 记录，
  `/memory/{uid}` 也没有字段区分草稿和最终回答；`/chat` 响应中的 `answer`
  才是最终回答。
- 每条历史消息单独提交，写入不是整轮原子事务；存储故障时可能只保存部分消息。
- 服务成功启动后，如果 PostgreSQL 在单次请求期间不可用，`/chat` 会跳过
  历史加载或保存，仍可能返回成功。
- gRPC `Generate` 不读写 PostgreSQL 对话历史，固定格式输出、日报摘要等
  无状态任务不应复用 `/chat` 的历史上下文。

### 6.3 知识与 RAG

- 知识按 `user_id` 过滤，默认检索最相关的 5 条。
- `/ingest` 是整段文本向量化，不会自动分块。
- 服务成功启动后，如果 Qdrant 或 Embedding 在单次请求期间不可用，
  `/chat` 会跳过 RAG，仍可能继续回答。
- 当前没有列出、更新或删除知识的公开接口。

### 6.4 启动探测与依赖

Jarvis 在绑定 HTTP/gRPC 端口前执行真实模型探测：

- 对 `llm.yaml` Profile 引用的每个唯一 Chat Provider 调用一次模型；同一
  Provider 的多个 Profile 只探测第一个发现的模型。
- 对当前 Embedding 模型执行一次真实 `embed_query`。
- 探测会消耗供应商额度，并可能按供应商延迟推迟端口监听。
- 探测失败只记录脱敏日志，不阻止后续启动。
- 当前没有专用的探测禁用开关或探测级超时配置。

模型探测之后，Jarvis 同步初始化 PostgreSQL 表和 Qdrant Collection，再绑定
端口。PostgreSQL 和 Qdrant 在启动时都是硬依赖：任一初始化失败，服务不会
开始监听接口。上面的存储降级只适用于服务成功启动后的单次请求故障。

## 7. Codex 接入检查清单

将本文件提供给负责接入的 Codex Agent，并要求其逐项确认：

- [ ] 从环境变量读取 Jarvis 地址，不硬编码生产域名。
- [ ] 选择 HTTP 或 gRPC 作为唯一主接入协议，避免双实现行为漂移。
- [ ] 为请求和响应建立本地类型，不直接传播无类型字典。
- [ ] 公网接入前禁用 `web_scrape`，或完成 SSRF、响应资源和网络 egress 防护。
- [ ] 在服务端或可信网关强制字段长度、请求体、频率和并发限制。
- [ ] 在服务端从已认证身份派生稳定的 `user_id`。
- [ ] 为 `/chat` 或 `Chat` 配置适合 Agent 长任务的超时/deadline。
- [ ] 按接口幂等性设计重试；`Chat` 结果未知时默认不自动重试。
- [ ] 默认不发送 `llm` 和 `reflect_llm` 覆盖。
- [ ] 对 `low_confidence: true` 建立业务降级或人工审核路径。
- [ ] `user_id` 不含 `/` 且符合约定字符集，URL path 参数继续进行编码。
- [ ] 日志不记录密钥、完整对话或敏感知识正文。
- [ ] 不把删除对话历史误认为删除了 Qdrant 知识。
- [ ] 集成测试 mock Jarvis；部署验收再运行真实服务 smoke test。

推荐给接入任务的 Codex 提示：

```text
先阅读仓库中的 API.md，并把它视为 Jarvis 当前接入契约。
实现一个有类型的 Jarvis 客户端，地址来自环境变量，user_id 必须从已认证用户
身份派生，禁止包含 /。公网接入前确认 web_scrape 已禁用或完成 SSRF 与网络
egress 防护，并在服务端/网关限制字段长度、请求体、频率和并发。默认不要传
llm/reflect_llm。为 chat 配置可调整的长超时；Chat 没有幂等键，超时或断连后
不要默认自动重试。按其他接口的幂等性和状态码执行有上限的退避重试。处理
low_confidence，不读取或记录失败响应正文，并确保日志脱敏。为成功、校验
失败、超时、限流和服务不可用添加测试。
```

## 8. 当前未提供的能力

接入设计不要假设以下能力已经存在：

- API 鉴权或 `user_id` 所有权校验。
- 对 `web_scrape` 的 SSRF 防护和网络 egress 限制。
- 应用级字段长度、请求体、频率和并发限制。
- 仅关闭 `web_scrape`、但保留其他工具的运行时 allowlist 开关。
- HTTP/gRPC 流式回答。
- 对话分页。
- 知识列表、更新、删除或按用户清空。
- 单一接口删除用户的全部 PostgreSQL 与 Qdrant 数据。
- 幂等键、请求 ID、调用追踪 ID。
- 服务级 SLA 或固定响应时间。
- 业务健康检查接口。
- gRPC Server Reflection。

如接入项目依赖这些能力，应先在 Jarvis 中补充接口、测试和本文档，再进行
生产对接。
