# AI Agent 阶段式学习计划

本计划不再以固定天数为边界，而是按能力成熟度分成初阶、中阶和高阶。每个阶段都有明确学习目标、能力要求、推荐资料、练习任务和进入下一阶段的判断标准。

阶段划分的核心原则：

- 初阶解决“能不能建立正确心智模型”。
- 中阶解决“能不能设计并实现 Agent 系统”。
- 高阶解决“能不能把 Agent 做成可靠、可扩展、可面试的工程项目”。

## 总体目标

完成三个阶段后，你应该能做到：

- 用机制级语言解释 LLM、RAG、Tool Calling、Memory、Agent 架构。
- 结合 Jarvis 代码讲清楚一个 Agent 后端系统如何运行。
- 独立设计一个可运行的多工具 Agent 后端。
- 把 Golang、微服务、Kubernetes 经验迁移到 AI 工程化表达中。
- 面试时能围绕项目讲清架构、取舍、失败场景、部署和扩展。

## 初阶：LLM 应用工程基础

### 阶段定位

初阶不是为了掌握复杂 Agent 框架，而是建立正确的 LLM 应用心智模型。这个阶段的核心问题是：

```text
LLM 到底是什么？
RAG 为什么有效？
Tool Calling 为什么需要系统执行？
Memory 为什么不是简单聊天记录？
```

### 学习目标

完成初阶后，你应该能：

- 解释 LLM 的本质是 `P(next_token | context)`。
- 解释 context、prompt、token、上下文窗口之间的关系。
- 解释 hallucination 的机制，而不是只说“模型会胡说”。
- 解释 RAG 为什么是改变 context，而不是改变模型参数。
- 解释 Function Calling / Tool Calling 中模型和系统的职责边界。
- 用自己的话讲清 Memory 的基本价值。

### 必须掌握

- Token 与上下文窗口。
- Prompt 与 context。
- temperature 与 top-p。
- LLM 的条件概率生成机制。
- Hallucination 的机制。
- RAG 基本流程。
- Function Calling / Tool Calling 基本流程。
- 多轮对话状态管理基础。

### 推荐学习顺序

1. LLM 本质：不是事实数据库，而是条件概率生成器。
2. Prompt：不是魔法，而是控制输入 context。
3. Hallucination：不是偶发错误，而是机制带来的风险。
4. RAG：通过外部检索改变 context。
5. Tool Calling：模型提出调用意图，系统执行工具。
6. Memory：让系统保留跨轮次、跨步骤上下文。

### 结合 Jarvis 阅读

- `docs/study/00-agent-learning-map.md`
- `docs/study/04-llm-router-and-model-abstraction.md`
- `docs/study/05-tool-calling-and-registry.md`
- `docs/study/06-memory-and-rag.md`
- `jarvis/llm/router.py`
- `jarvis/tools/registry.py`

### 练习任务

- 用一句话解释 LLM 为什么能表现出推理能力。
- 用机制级语言解释为什么 LLM 会 hallucination。
- 画出一次最小 Tool Calling 流程。
- 解释 RAG 为什么能降低 hallucination。
- 判断哪些信息应该通过 RAG 获取，哪些信息应该进入 Memory。

### 检查问题

1. LLM 为什么不是事实数据库？
2. `P(next_token | context)` 中的 context 包括哪些东西？
3. RAG 改变了模型的哪个输入变量？
4. Tool Calling 中，模型真正执行工具了吗？
5. Memory 和普通聊天历史有什么区别？

### 阶段完成标准

满足下面条件，可以进入中阶：

- 能在不看资料的情况下解释 LLM、RAG、Tool Calling、Memory 的基本机制。
- 能把“现象级回答”提升成“机制级回答”。
- 能看懂 Jarvis 中 LLM Router 和 Tool Registry 的基本职责。
- 能完成一个最小 demo：用户输入 -> 模型判断是否调用工具 -> 系统执行工具 -> 模型整合结果回答。

## 中阶：Agent 系统设计与项目落地

### 阶段定位

中阶开始进入真正的 Agent 系统。这个阶段的重点不是单点概念，而是把 RAG、Tool Calling、Memory、Planner、Executor、Reflection 组合成一个可运行流程。

核心问题是：

```text
Agent 如何从一次模型调用，变成一个可执行任务的系统？
```

### 学习目标

完成中阶后，你应该能：

- 区分 Agent、Chatbot、Workflow 和 RAG 应用。
- 讲清 Planner / Executor 的职责边界。
- 设计一个多工具 Agent 的执行流程。
- 理解 Memory 如何支撑多步任务状态。
- 理解 RAG 在 Agent 流程中为什么通常发生在模型规划前。
- 理解 Reflection / Validation 如何提高可靠性。
- 能结合 Jarvis 代码追踪一次完整请求。

### 必须掌握

- AgentState。
- Agent Graph / LangGraph。
- ReAct 基本思想。
- Planner。
- Executor。
- Tool Registry。
- ToolMessage。
- RAG 检索节点。
- Conversation Memory / State Memory / Long-term Memory。
- Reflection / Validation。
- 条件路由、循环、终止条件。

### 推荐学习顺序

1. Agent 与 Chatbot 的区别。
2. AgentState：为什么 Agent 需要显式状态对象。
3. Agent Graph：如何用节点和条件路由组织流程。
4. Tool Calling：工具注册、参数校验、结果回填。
5. RAG 全链路：chunk、embedding、top-k、rerank、prompt 注入。
6. Memory：对话历史、任务状态、长期偏好。
7. Planner / Executor：任务拆解与工具执行分离。
8. Reflection：结果校验、有限重试、终止条件。

### 结合 Jarvis 阅读

- `docs/study/01-project-architecture.md`
- `docs/study/02-agent-state-and-message-flow.md`
- `docs/study/03-langgraph-execution-graph.md`
- `docs/study/05-tool-calling-and-registry.md`
- `docs/study/06-memory-and-rag.md`
- `docs/study/07-reflection-and-self-correction.md`
- `jarvis/agent/state.py`
- `jarvis/agent/graph.py`
- `jarvis/agent/nodes/plan_and_call.py`
- `jarvis/agent/nodes/rag_retrieve.py`
- `jarvis/agent/nodes/memory_load.py`
- `jarvis/agent/nodes/memory_write.py`
- `jarvis/agent/nodes/reflect.py`
- `jarvis/memory/conversation.py`
- `jarvis/memory/knowledge.py`

### 练习任务

- 画出 Jarvis 的完整 Agent Graph。
- 用一次用户请求解释每个节点为什么存在。
- 设计一个新工具，并说明它应该如何注册、如何校验参数、如何返回结果。
- 设计一个 Memory 写入策略：什么应该写，什么不应该写。
- 解释 Reflection 为什么必须设置最大重试次数。
- 为“订餐 Agent”设计 Planner / Executor / Memory / Tool 的边界。

### 检查问题

1. Agent 为什么不是一个简单函数？
2. Planner 和 Executor 如果混在一起会有什么问题？
3. RAG、Memory、Tool Result 都会进入 context，它们的来源和生命周期有什么不同？
4. Agent Graph 中为什么需要条件路由？
5. 如果工具调用失败，Agent 应该如何处理？
6. Reflection 评分低时，系统应该直接无限重试吗？

### 阶段完成标准

满足下面条件，可以进入高阶：

- 能完整讲出 Jarvis 从 API 请求到最终回答的执行路径。
- 能设计一个多工具 Agent 的模块边界。
- 能解释 RAG、Memory、Tool Calling 在同一个 Agent 流程中的关系。
- 能写出或改造一个最小可运行 Agent 后端。
- 能对一个新 Agent 需求做边界判断：哪些逻辑放 API，哪些放 Graph，哪些放 Node，哪些放 Tool，哪些放 Memory。

## 高阶：工程化、平台化与面试竞争力

### 阶段定位

高阶不再只关注“Agent 能不能跑”，而是关注“Agent 能不能稳定、可观测、可扩展、成本可控地运行”。这正是你已有后端和 Kubernetes 经验最能形成差异化优势的阶段。

核心问题是：

```text
如何把不稳定、昂贵、慢速、依赖外部服务的模型能力，包装成可靠的后端系统？
```

### 学习目标

完成高阶后，你应该能：

- 把 Agent API 服务化，并设计稳定的请求响应边界。
- 设计 Agent 的日志、trace、监控和错误定位方案。
- 设计成本控制策略，包括模型选择、缓存、限流和重试上限。
- 设计外部依赖失败时的降级策略。
- 用 Docker / Kubernetes 部署 Agent 服务。
- 解释多实例部署下 Memory、向量库、数据库和工具服务的边界。
- 准备一个可面试、可追问、可落地的 AI Agent 项目。

### 必须掌握

- API 边界设计。
- 配置管理。
- 超时、重试、降级。
- 工具安全限制。
- 权限控制。
- 日志与 trace。
- 指标监控。
- 成本控制。
- 缓存策略。
- Docker 容器化。
- Kubernetes Deployment / Service / HPA。
- 向量数据库与关系数据库部署。
- 推理服务化基础。
- 面试项目叙事。

### 推荐学习顺序

1. API 边界：协议层不应该泄漏 Agent 内部状态。
2. 配置：模型、阈值、重试次数、数据库地址、API Key 外置。
3. 可观测性：记录每次 Agent 的节点路径、工具调用、模型调用、错误。
4. 可靠性：超时、重试、降级、最大循环次数。
5. 成本控制：模型路由、缓存、限流、调用预算。
6. 安全约束：工具白名单、参数校验、用户确认、权限边界。
7. 部署：Docker、K8s、多副本、扩缩容。
8. 平台化：模型 Provider 抽象、工具服务化、推理服务接入。
9. 面试表达：背景、架构、流程、取舍、故障处理、扩展方向。

### 结合 Jarvis 阅读

- `docs/study/08-api-boundary-and-service-design.md`
- `docs/study/09-engineering-thinking.md`
- `docs/study/interaction/interview-agent-project.md`
- `jarvis/api/http/routes.py`
- `jarvis/api/grpc/servicer.py`
- `jarvis/config.py`
- `jarvis/llm/base.py`
- `jarvis/llm/openai.py`
- `jarvis/llm/claude.py`
- `jarvis/llm/siliconflow.py`
- `docker-compose.yml`
- `Dockerfile`
- `tests/unit/test_llm_router.py`
- `tests/unit/test_tool_registry.py`
- `tests/integration/test_graph_flow.py`
- `tests/e2e/test_api.py`

### 练习任务

- 把“多工具 Agent + AI 推理平台部署”讲成 2 分钟项目介绍。
- 为 Agent 增加一套执行 trace 设计：每个节点记录什么。
- 设计一个成本控制方案：哪些调用需要缓存，哪些调用需要限流。
- 设计一个工具安全方案：哪些工具必须人工确认。
- 设计 Agent 在 Qdrant、PostgreSQL、搜索 API、LLM API 任一依赖失败时的降级策略。
- 画出 K8s 部署图：API 服务、工具服务、数据库、向量库、外部模型 API。

### 检查问题

1. Agent 系统有哪些外部依赖？
2. 哪些配置影响成本，哪些配置影响质量？
3. Agent 为什么必须有最大循环次数和最大重试次数？
4. 如何定位一次 Agent 回答错误发生在哪个节点？
5. 多副本部署时，Memory 应该放本地还是外部存储？
6. 哪些工具调用需要权限控制或人工确认？
7. 如果向量数据库不可用，系统应该完全失败还是降级回答？
8. 你如何在 K8s 中部署和扩展 Agent 服务？

### 阶段完成标准

达到下面状态，说明你已经具备高阶能力：

- 能讲清一个生产级 Agent 系统的可靠性、成本和安全约束。
- 能把 Agent 能力拆成 API、Graph、Node、Tool、Memory、LLM Provider、Storage、Deployment 等边界。
- 能围绕一个项目回答架构、流程、失败、扩展、部署、监控和成本问题。
- 能把已有 Golang、微服务、Kubernetes 经验转化成 AI 工程化优势。
- 能独立评审一个 Agent 需求是否值得做、应该怎么做、风险在哪里。

## 阶段推进建议

不要用固定天数判断学习是否完成。更好的方式是用输出物判断：

- 初阶输出物：概念解释卡片、最小 Tool Calling demo、RAG 机制说明。
- 中阶输出物：Jarvis 执行路径图、多工具 Agent 设计文档、最小 Agent 后端。
- 高阶输出物：面试项目讲解稿、部署架构图、可观测性方案、降级与成本控制方案。

## 日常学习节奏

建议每次学习按下面顺序进行：

1. 复习上一个概念。
2. 学习一个新概念。
3. 映射到 Jarvis 代码。
4. 用自己的话写一版面试表达。
5. 回答一个检查问题。
6. 做一个小练习或画一张小图。

## 最终产出物

完整学习周期结束后，建议形成这些产出：

- 一张 AI Agent 架构图。
- 一张 RAG 全链路图。
- 一张 Jarvis 请求执行路径图。
- 一个多工具 Agent 项目讲解稿。
- 一组常见面试追问与回答。
- 一个可运行、可演示、可部署的最小 Agent 后端。
- 一个 Agent 工程化方案：可观测性、降级、成本控制、安全约束、K8s 部署。
