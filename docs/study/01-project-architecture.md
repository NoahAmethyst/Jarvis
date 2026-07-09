# 01 项目架构

## 本章目标

学完本章，你应该能：

- 解释 Jarvis 的主要分层。
- 判断一个新能力应该放在哪一层。
- 说明 API Layer、Agent Graph、LLM Provider、Tools、Memory、Storage 的职责边界。
- 从入口文件追踪一次请求的大致路径。

## 核心概念

Agent 项目最怕边界混乱。常见坏味道是 API 里直接写模型调用，工具里直接改数据库，记忆层直接拼 prompt。这样短期能跑，长期会失控。

Jarvis 把职责拆成几层：

- API Layer：负责协议和请求响应格式。
- Agent Graph：负责执行流程和条件路由。
- Agent Nodes：负责每个步骤的局部行为。
- LLM Provider：负责模型接入和模型选择。
- Tools：负责可被模型调用的外部能力。
- Memory：负责对话历史和知识库。
- Config：负责环境变量和默认参数。

好的架构不是为了目录好看，而是为了让变化发生在正确位置。新增 HTTP 字段不应该改工具系统；更换模型厂商不应该改 Agent 图；新增工具不应该改 API 协议。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/main.py`：服务启动，初始化存储，并行启动 HTTP 和 gRPC。
2. `jarvis/api/http/routes.py`：HTTP 请求如何构造 AgentState 并调用 graph。
3. `jarvis/api/grpc/servicer.py`：gRPC 如何复用同一套能力。
4. `jarvis/agent/graph.py`：核心 Agent 流程。
5. `jarvis/config.py`：端口、模型、数据库、阈值等配置来源。

重点观察：API 层没有自己实现 Agent 逻辑，而是把请求转换成状态后交给 graph。

## 关键设计问题

为什么 HTTP 和 gRPC 应该共享同一个 Agent Graph？

因为 HTTP 和 gRPC 只是协议入口，不是业务逻辑本身。如果两边各自实现一套 Agent 流程，行为会漂移：HTTP 可能有 Reflection，gRPC 可能忘了；HTTP 可能写记忆，gRPC 可能不写。共享 graph 可以保证协议不同，核心行为一致。

为什么 LLM Provider 要独立成一层？

模型厂商会变，模型名会变，调用参数会变。如果业务节点直接依赖某个厂商 SDK，替换成本会很高。Jarvis 用 `"provider/model_id"` 的形式把“选择哪个模型”和“如何构造模型对象”隔离出去。

为什么 Tools 和 Memory 要分开？

工具是模型可以主动调用的外部能力，比如搜索和网页抓取。Memory 是系统为 Agent 提供上下文和长期状态的能力。工具回答“现在去做什么”，记忆回答“过去知道什么”。

## 学习检查

1. Jarvis 中哪个文件负责启动 HTTP 和 gRPC？
2. API 层为什么不直接调用 LLM？
3. 新增一个模型厂商时，应该优先改哪一层？
4. 新增一个天气查询工具时，应该优先改哪一层？
5. PostgreSQL 和 Qdrant 分别属于哪类存储？

## 小练习

假设你要给 Jarvis 增加“用户偏好设置”，比如回答语言、输出长短、是否允许搜索。只做设计，不写代码：

- 偏好从 API 传入，还是从数据库读取？
- 偏好应该放进 AgentState 的哪个位置？
- 哪些节点需要读取这个偏好？
- 这个能力不应该放在哪些层？为什么？
