# 00 Agent 学习地图

## 本章目标

学完本章，你应该能：

- 解释 AI Agent 是什么。
- 区分 Agent、普通 Chatbot、Workflow 和 RAG 应用。
- 用“输入、状态、模型、工具、记忆、反思、输出”描述 Jarvis。
- 知道后续章节为什么按当前顺序展开。

## 核心概念

AI Agent 不是“会聊天的模型”本身，而是一个让模型参与决策和行动的系统。模型负责理解目标、选择下一步、生成文本或工具调用；系统负责保存状态、调度流程、执行工具、处理错误、读写记忆和暴露服务接口。

普通 Chatbot 通常是一次请求加一段上下文，然后模型直接回答。Workflow 更

像固定流水线，每一步由程序提前写死。RAG 应用重点在“先检索知识，再生成答案”。Agent 则更强调“模型参与控制流”：它可以根据当前状态决定是否调用工具、调用什么工具、是否需要重试、最后如何组织答案。

Jarvis 当前不是一个无限自治的 Agent，而是一个工程化的后端 Agent。它有清晰边界：外部通过 API 发请求；内部用 LangGraph 管理执行路径；工具和记忆由系统封装；模型通过 router 接入；结果通过 API 返回。

可以把 Jarvis 理解成这个闭环：

```text
用户输入
  -> AgentState
  -> 加载历史记忆
  -> 选择领域 Agent 指令
  -> 检索知识库
  -> LLM 规划和回答
  -> 必要时调用工具
  -> Reflection 评分
  -> 写入记忆
  -> 返回最终答案
```

## Jarvis 代码地图

建议阅读顺序：

1. `README.md`：先看项目目标和整体架构图。
2. `jarvis/api/http/routes.py`：看用户输入如何变成 AgentState。
3. `jarvis/agent/state.py`：看 Agent 运行时需要携带哪些信息。
4. `jarvis/agent/graph.py`：看完整执行闭环。

读代码时先看“有哪些模块”，不要先陷入实现细节。Agent 项目的第一层理解永远是边界和数据流。

## 关键设计问题

为什么 Agent 不是一个简单函数？

因为 Agent 过程里有分支和循环。Jarvis

可能直接回答，也可能先调用工具；答案评分低时可能回到规划节点重试；记忆系统可能可用，也可能降级跳过。如果写成一个长函数，控制流会越来越难看清。

为什么需要状态？

模型本身没有可靠的程序状态。每次调用模型时，系统必须明确告诉它当前问题、历史、RAG 结果、工具结果和重试情况。AgentState 就是系统和模型之间的“工作台”。

为什么 Agent 学习要结合代码？

Agent 概念很容易停留在抽象词上，比如 planning、memory、reflection。结合 Jarvis 代码后，这些词会变成具体问题：在哪个文件做规划？记忆什么时候读？工具怎么注册？评分不合格怎么回路？

## 学习检查

1. Jarvis 和普通 Chatbot 最大区别是什么？
2. Jarvis 和纯 RAG 应用最大区别是什么？
3. 为什么 Agent 需要状态对象？
4. Jarvis 中哪些部分由模型负责，哪些部分由程序负责？
5. 如果去掉 Reflection，Jarvis 的执行闭环会少掉什么能力？

## 小练习

不用改代码，画一张你自己的 Jarvis 流程图。要求图中至少包含：

- API 输入
- AgentState
- memory_load
- agent_dispatch
- rag_retrieve
- plan_and_call
- tool_node
- reflect
- memory_write
- 最终输出

画完后，用一句话解释每个节点为什么存在。
