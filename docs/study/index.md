# Jarvis AI Agent 学习路线

这套资料面向已经会 Python、但希望从 0 系统学习 AI Agent 开发的人。学习方式不是按文件逐行读代码，而是用两条线并行推进：

- 学习轨：理解 Agent 的概念、边界、设计思想和工程判断。
- 项目轨：把每个概念映射回 Jarvis 当前代码，知道真实项目里这些思想如何落地。

Jarvis 是一个基于 LangGraph 的 Agent 后端。它接收 HTTP 或 gRPC 请求，把请求转换成 AgentState，然后经过记忆加载、RAG 检索、LLM 规划、工具调用、反思评分和记忆写入，最后返回答案。

## 推荐阅读顺序

1. [00 Agent 学习地图](00-agent-learning-map.md)
2. [01 项目架构](01-project-architecture.md)
3. [02 AgentState 与消息流](02-agent-state-and-message-flow.md)
4. [03 LangGraph 执行图](03-langgraph-execution-graph.md)
5. [04 LLM Router 与模型抽象](04-llm-router-and-model-abstraction.md)
6. [05 Tool Calling 与工具注册表](05-tool-calling-and-registry.md)
7. [06 Memory 与 RAG](06-memory-and-rag.md)
8. [07 Reflection 与自我修正](07-reflection-and-self-correction.md)
9. [08 API 边界与服务设计](08-api-boundary-and-service-design.md)
10. [09 Agent 工程思维](09-engineering-thinking.md)
11. [10 节点设计与边界判断](10-nodes-and-graph-design.md)
12. [互动学习档案](interaction/index.md)

## 项目架构地图

```text
外部调用
  -> jarvis/api/http/routes.py 或 jarvis/api/grpc/servicer.py
  -> jarvis/agent/graph.py
  -> jarvis/agent/nodes/*
  -> jarvis/llm/router.py
  -> jarvis/tools/*
  -> jarvis/memory/*
  -> PostgreSQL / Qdrant / LLM API / Tavily
```

核心文件阅读顺序：

1. `jarvis/api/http/routes.py`：看一次请求如何进入系统。
2. `jarvis/agent/state.py`：看 Agent 在流程中携带哪些状态。
3. `jarvis/agent/graph.py`：看节点和条件路由如何组成执行图。
4. `jarvis/agent/nodes/plan_and_call.py`：看 LLM 如何拿到上下文、历史、工具。
5. `jarvis/tools/registry.py`：看工具如何注册给模型。
6. `jarvis/memory/conversation.py` 和 `jarvis/memory/knowledge.py`：看长期记忆和知识检索。
7. `jarvis/agent/nodes/reflect.py`：看答案如何被评分和重试。

## 每章学习产出

学完这套资料后，你应该能做到：

- 解释 Agent、Chatbot、Workflow、RAG 应用之间的区别。
- 画出 Jarvis 的执行路径和状态流转。
- 判断一个能力应该放在 API、Graph、Node、Tool、Memory 还是 LLM Provider 层。
- 解释为什么 Agent 需要状态、工具、记忆、反思和降级策略。
- 面对一个新需求时，先做边界设计，再让实现者写代码。

## 学习方法

每章建议按这个顺序学：

1. 先读“核心概念”，不要急着进代码。
2. 再按“Jarvis 代码地图”打开对应文件。
3. 用“关键设计问题”反推作者为什么这样拆。
4. 回答“学习检查”，确认自己能闭卷解释。
5. 做“小练习”，练的是设计判断，不是机械改代码。

学习 Agent 开发时，重点不是记住某个框架 API，而是形成判断：

- 状态应该放在哪里？
- 模型该看到哪些上下文？
- 工具调用失败怎么办？
- 记忆什么时候读，什么时候写？
- 哪些错误能降级，哪些错误必须返回给调用方？
- 哪些能力应该写死，哪些能力应该抽象成接口？

Jarvis 适合拿来练这些判断，因为它包含 Agent 后端常见的最小闭环：模型、工具、记忆、RAG、反思、API、配置和测试。

## 互动学习档案

如果你想从“当前学习进度”继续，而不是从 Jarvis 代码章节开始，可以先看 [interaction/index.md](interaction/index.md)。这个目录保存了共享对话中整理出的学习画像、知识图谱、阶段式学习计划、面试项目框架和后续教学协议。
