# 学习画像与目标定位

## 个人背景

你当前是一名后端开发工程师：

- 主要语言：Golang。
- 熟悉语言：Java、Python。
- 工程经验：微服务、Kubernetes、后端服务化。
- 目标方向：AI Agent 开发工程师，或 AI 模型部署平台、推理平台、Kubernetes 相关 AI 工程岗位。

这意味着你学习 AI Agent 时不应该走“从 Python Web 基础学起”的路线，而应该走“把已有后端工程能力迁移到 LLM 应用工程”的路线。

## 目标

短期目标：

- 先补齐初阶和中阶 AI Agent 工程能力，再逐步形成可面试的项目表达。
- 能讲清楚一个完整、可信、可落地的 AI Agent 项目。
- 能回答面试中围绕 LLM、RAG、Tool Calling、Memory、Agent 架构、工程化部署的机制级问题。

长期目标：

- 能独立设计 AI Agent 后端系统。
- 能判断一个 AI 功能应该落在 API、Agent Graph、Tool、Memory、RAG、LLM Provider 还是部署层。
- 能把 Kubernetes、微服务、服务治理、监控、成本控制等后端经验转化成 AI 工程化竞争力。

## 当前优势

### 后端工程能力

你已经具备服务端工程基础，理解接口、状态、服务边界、部署、扩展和可维护性。这是 AI Agent 工程中非常重要的基础。

很多 AI 初学者会卡在工程落地，而你的优势正好在这里：

- 服务如何暴露 API。
- 如何拆模块。
- 如何做容器化。
- 如何部署到 K8s。
- 如何考虑扩展性、稳定性、日志和监控。

### 可迁移能力

AI Agent 不是单纯调用 LLM API，而是一个包含模型、工具、记忆、检索、状态、重试和部署的后端系统。你的后端经验可以迁移到：

- Agent 服务边界设计。
- Tool Calling 的接口设计。
- Memory 的状态管理。
- RAG 的数据管线。
- 推理服务的部署与扩缩容。
- Agent 执行过程的可观测性。

## 当前短板

### LLM 应用抽象能力

对话中已经明确：你当前缺的不是“会不会写服务”，而是能否把 LLM 能力抽象成工程系统。

需要补齐：

- LLM 的本质：条件概率模型，`P(next_token | context)`。
- Prompt、上下文窗口、temperature、top-p 的作用。
- RAG 为什么能降低幻觉。
- Function Calling 和 Tool Calling 的工程边界。
- Memory 与 RAG 的机制差异。
- Planner、Executor、Reflection、Validation 的职责。

### 机制级表达能力

面试不会只问定义，而会问机制：

- 为什么 LLM 会幻觉？
- 为什么 RAG 能降低幻觉？
- 为什么 chunk 太大或太小都会影响效果？
- 为什么 top-k 不是越大越好？
- 为什么 embedding 检索之后还需要 rerank？
- 为什么 Agent 会失控或循环？
- 为什么 Memory 不是简单聊天历史？

你的学习重点应该从“记术语”转为“建立因果模型”。

## 当前学习阶段判断

你已经开始形成下面这些理解：

- LLM 本质是在给定 context 条件下预测下一个 token。
- LLM 的推理、规划、写代码能力来自大规模语料和 Transformer 对上下文依赖的建模，不等于模型内部有真实世界校验机制。
- RAG 的本质不是改变模型参数，而是改变进入模型的 context。
- RAG 可以降低幻觉，是因为外部事实进入 context 后，模型生成空间受到更强约束。
- Memory 的价值在于让 Agent 保持跨步骤、跨轮次的状态，而不是每一步都只做局部最优决策。
- RAG 与 Memory 都会影响 context，但触发机制和生命周期不同。

下一步要把这些理解落成：

- 可画出的架构图。
- 可讲出的项目故事。
- 可回答的面试追问。
- 可运行的 Jarvis 项目理解。
