# 08 API 边界与服务设计

## 本章目标

学完本章，你应该能：

- 解释 Agent 后端如何暴露能力。
- 理解 HTTP 和 gRPC 为什么可以共享同一个 graph。
- 说明 API request 如何变成 AgentState。
- 区分协议层错误和 Agent 内部错误。

## 核心概念

Agent 后端不是只有模型调用，还要对外提供稳定接口。接口层负责把外部世界的请求转换成内部可执行的状态，也负责把内部结果转换成外部响应。

Jarvis 当前暴露两套协议：

- HTTP：适合 Web 应用、调试、普通服务集成。
- gRPC：适合强类型、多语言、高性能服务间通信。

两套协议共享同一个 Agent Graph。这是关键设计：协议可以不同，核心 Agent 行为必须一致。

以 HTTP `/chat` 为例，请求体包含：

- `message`
- `user_id`
- `llm`
- `reflect_llm`

API 层把它们组装成 AgentState，然后调用 `graph.invoke(initial_state)`。Graph 返回结果后，API 只取 `final_answer` 和 `low_confidence` 返回。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/api/http/routes.py`：看 Pydantic request/response model 和 endpoint。
2. `jarvis/api/grpc/jarvis.proto`：看 gRPC 服务和消息定义。
3. `jarvis/api/grpc/servicer.py`：看 gRPC 方法如何调用同一套 graph 或 memory 函数。
4. `jarvis/main.py`：看 HTTP 和 gRPC 如何一起启动。
5. `jarvis/llm/router.py`：看 provider 错误如何映射到 API 错误。

## 关键设计问题

为什么 API 返回 `answer` 和 `low_confidence`，而不是返回完整 AgentState？

完整状态包含内部实现细节，比如历史、RAG 上下文、重试次数和模型覆盖字段。API 应该返回稳定、必要、面向调用方的字段。暴露过多内部状态会让未来重构变困难。

为什么 `llm` 和 `reflect_llm` 可以从请求传入？

这允许调用方按请求覆盖默认模型，用于实验、调试、成本控制或不同用户等级。默认值仍然放在配置中，保证普通请求不需要关心模型细节。

为什么 `/ingest` 绕过 Agent Graph？

手动上传文档入知识库是明确的后端操作，不需要模型参与决策。它直接调用 knowledge memory 更简单，也更可控。不是所有功能都应该做成 Agent 行为。

为什么错误要映射成合适状态码？

调用方需要知道错误归因。模型 provider 不存在是请求参数错误，适合 400。provider 暂时不可用是上游依赖问题，适合 502。存储操作失败则返回 500。

## 学习检查

1. `/chat` 请求如何变成 AgentState？
2. HTTP 和 gRPC 共享 graph 的好处是什么？
3. 为什么不应该把完整 AgentState 直接返回给用户？
4. `/ingest` 为什么不需要经过 Agent？
5. `ProviderNotFoundError` 和 `ProviderUnavailableError` 分别适合什么 HTTP 状态码？

## 小练习

设计一个新的 `/chat/debug` 接口，不写代码，只写 API 设计：

- 它应该比普通 `/chat` 多返回哪些字段？
- 哪些内部字段仍然不应该返回？
- 这个接口应该只在开发环境启用吗？
- gRPC 是否也需要对应方法？为什么？
