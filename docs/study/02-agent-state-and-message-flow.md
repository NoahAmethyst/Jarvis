# 02 AgentState 与消息流

## 本章目标

学完本章，你应该能：

- 解释 AgentState 在 LangGraph 中的作用。
- 区分 `messages`、`history` 和 `query`。
- 说明 `rag_context`、`reflection_score`、`retry_count`、`final_answer`、`low_confidence` 的意义。
- 追踪状态如何在节点间被读取和更新。

## 核心概念

AgentState 是 Agent 的运行时工作台。每个节点不需要知道整个系统如何启动，也不需要直接调用别的节点；它只读取 state 中自己关心的字段，然后返回要更新的字段。

Jarvis 的状态字段大致分为几类：

- 输入类：`messages`、`query`、`user_id`
- 上下文类：`history`、`rag_context`
- 控制类：`reflection_score`、`retry_count`、`low_confidence`
- 输出类：`final_answer`
- 配置覆盖类：`llm_override`、`reflect_llm_override`

`messages` 是本轮图执行中不断增长的消息列表。它使用 LangGraph 的 `add_messages` 聚合行为，节点返回的新消息会追加进去。

`history` 是从 PostgreSQL 加载的历史对话。它不等于本轮 `messages`，而是过去会话对当前回答的补充上下文。

`query` 是用户原始问题。即使 `messages` 后续追加了 AIMessage 和 ToolMessage，`query` 仍然保留原始任务，Reflection 节点用它判断答案有没有回答原问题。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/agent/state.py`：看 AgentState 字段定义。
2. `jarvis/api/http/routes.py`：看初始 state 如何创建。
3. `jarvis/agent/nodes/memory_load.py`：看 `history` 如何写入。
4. `jarvis/agent/nodes/rag_retrieve.py`：看 `rag_context` 如何写入。
5. `jarvis/agent/nodes/reflect.py`：看评分、重试和最终答案如何写入。

阅读重点：每个节点返回的是一个 dict，而不是直接操控整条流程。

## 关键设计问题

为什么要同时有 `messages` 和 `history`？

因为它们生命周期不同。`messages` 表示本次 graph 执行中的当前消息轨迹，可能包含工具调用和工具结果。`history` 表示过去保存下来的对话，只用于给模型提供上下文。把它们分开，能避免把历史误当成本轮新消息写回数据库。

为什么要保留 `query`？

Agent 运行后，消息列表会变复杂：AI 可能发起工具调用，ToolNode 会追加 ToolMessage，模型再生成答案。如果后面要评估“是否回答了原始问题”，直接从消息列表里反推不稳定。`query` 是稳定锚点。

为什么 `low_confidence` 是状态字段？

它不是模型输出文本的一部分，而是系统对结果质量的判断。API 可以把它作为结构化字段返回给调用方，让上层产品决定是否提示用户“答案可能不可靠”。

## 学习检查

1. `messages` 和 `history` 的区别是什么？
2. 为什么 Reflection 使用 `query`，而不是直接拿最后一条 HumanMessage？
3. 哪些字段属于控制流字段？
4. `llm_override` 和 `reflect_llm_override` 解决什么问题？
5. 如果要新增“当前请求 trace_id”，应该放进 AgentState 吗？为什么？

## 小练习

手写一份 `/chat` 请求进入 Jarvis 后的初始 AgentState。然后标注每个字段会被哪个节点读取或更新。

要求至少包含：

- `messages`
- `history`
- `query`
- `rag_context`
- `reflection_score`
- `retry_count`
- `final_answer`
- `low_confidence`
