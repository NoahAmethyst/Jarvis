# 11 Agent 编排与 Worker Agent

## 本章目标

学完本章，你应该能：

- 区分 `AgentDefinition`、Jarvis 主 Agent Runtime、Worker Agent 和 Agent Orchestrator。
- 解释“选择领域指令”“委派子任务”和“编排多个 Agent”为什么不是同一件事。
- 判断一个执行单元应该是普通 Node、Tool、Worker Agent，还是独立服务。
- 设计 Worker Agent 的输入输出契约、状态边界和失败语义。
- 画出包含任务依赖、并行 fan-out、结果 fan-in 和 reducer 的执行图。
- 准确说明 Jarvis 当前具备什么，以及演进为多 Agent 系统还缺什么。

## 1. 先处理 `Agent` 这个重载术语

`Agent` 在不同项目里可能指完全不同的东西。看到这个词时，不要先按名字判断能力，而要检查它是否拥有以下运行时要素：

```text
目标 + 上下文 + 状态 + 模型决策 + 可用工具 + 执行循环 + 终止条件 + 结果契约
```

常见层级如下：

| 概念 | 主要职责 | 是否独立执行任务 | 是否拥有自己的循环 |
|---|---|---:|---:|
| LLM | 根据 context 生成消息或工具调用 | 否 | 否 |
| Tool | 执行一个边界明确的动作 | 是，但不是自主任务 | 否 |
| Node | 完成图中的一个步骤 | 是 | 通常否 |
| Skill / Persona | 给主 Agent 增加领域指令或知识 | 否 | 否 |
| Agent Runtime | 围绕目标运行模型、工具和状态循环 | 是 | 是 |
| Worker Agent | 接收编排器委派的子任务并返回结果 | 是 | 通常是 |
| Orchestrator / Supervisor | 分解、调度、协调和汇总多个执行单元 | 负责全局任务 | 可能是 |

这里最重要的判断不是“文件名里有没有 agent”，而是：

> 它拿到的是一段提示词配置，还是一个可以独立执行并返回结果的任务契约？

## 2. Jarvis 中必须分开的三层

### 2.1 `AgentDefinition`：领域提示词配置

Jarvis 的 `AgentDefinition` 只有四个字段：

```python
@dataclass
class AgentDefinition:
    name: str
    description: str
    instructions: str
    source_file: str
```

它表达的是一个可被选择的领域能力说明：

- `description` 用于判断用户问题是否匹配。
- `instructions` 被注入主 Agent 的 system prompt。
- `source_file` 记录定义来源。
- 它没有独立状态、工具集、执行图、生命周期或结果协议。

因此，`AgentDefinition` 更接近：

```text
动态选择的 Skill / Persona / Prompt Specialization
```

这个命名在项目内部可以继续使用，但在架构讨论和面试中必须补充它的真实语义，不能把 `AgentDefinition` 描述成独立 Worker Agent。

### 2.2 Jarvis 主 Agent Runtime：当前真正的可执行 Agent

Jarvis 主体是一个可执行 Agent Runtime。`jarvis/agent/graph.py` 组合了：

- `AgentState`。
- LLM 决策。
- Tool Calling 回路。
- RAG 和 Memory。
- Reflection 评分与有限重试。
- 终止和持久化路径。

所以不能笼统地说“Jarvis 当前没有可执行 Agent”。准确说法是：

> Jarvis 已有一个可执行的主 Agent Runtime，但 `.agents/skills` 中加载的 `AgentDefinition` 只是注入主 Runtime 的领域指令，不是多个独立 Worker。

### 2.3 Worker Agent：被委派的子任务执行单元

Worker Agent 是被委派子任务的可执行单元。它通常具备：

- 明确的子任务目标。
- 经过裁剪的上下文。
- 自己允许使用的工具。
- 局部执行状态和有限循环。
- 超时、重试、预算和终止条件。
- 结构化结果或失败信息。

可以把它抽象成：

```text
TaskSpec -> Worker Agent -> TaskResult
```

Worker Agent 不等于独立微服务。它可以是：

- 同一进程中的 Agent Runtime。
- LangGraph 中的一个子图。
- 后台任务队列中的 Worker。
- 通过 HTTP、gRPC 或消息队列调用的远程服务。

“是不是 Worker Agent”描述的是执行职责，“是不是独立服务”描述的是部署边界，两者正交。

## 3. Agent Orchestrator

Agent Orchestrator 负责全局控制，不是简单调用几个函数。典型职责包括：

- 理解全局目标。
- 拆解子任务并建立依赖关系。
- 为任务选择 Worker。
- 裁剪并分发上下文。
- 控制并发、预算、超时和取消。
- 收集部分结果。
- 处理失败、重试、降级和人工确认。
- 合并、校验并输出最终结果。

编排器可以是确定性工作流、LLM Supervisor，或两者的混合：

```text
确定性外壳：权限、依赖、预算、重试、终止
LLM 决策：任务拆解、Worker 选择、结果综合
```

生产系统通常更适合混合方式，因为关键约束不能只依赖模型自觉遵守。

## 4. 四者对比

| 对比维度 | `AgentDefinition` | Jarvis 主 Agent Runtime | Worker Agent | Agent Orchestrator |
|---|---|---|---|---|
| 本质 | 领域指令配置 | 用户请求执行闭环 | 子任务执行单元 | 全局任务控制单元 |
| 主要输入 | 名称、描述、instructions | 用户请求和 `AgentState` | `TaskSpec` | 用户目标、任务状态、Worker 注册表 |
| 主要输出 | 被选中的 instructions | 最终回答 | `TaskResult` | 汇总后的最终结果 |
| 独立上下文 | 否 | 有主会话 context | 有任务级 context | 保存全局 context 并决定下发内容 |
| 独立工具集 | 否 | 当前获得全部注册工具 | 通常有工具白名单 | 决定 Worker 和工具权限 |
| 独立执行循环 | 否 | 有 | 通常有 | 可有规划和校验循环 |
| 调度责任 | 无 | 只控制当前主流程 | 只执行自己的任务 | 依赖、并行、优先级、预算、取消 |
| 当前 Jarvis 是否具备 | 是 | 是 | 否 | 否 |

一句话记忆：

```text
AgentDefinition 改变“主 Agent 以什么领域方式工作”；
主 Agent Runtime 完成“当前用户请求的执行闭环”；
Worker Agent 负责“完成一个被委派的子任务”；
Orchestrator 决定“有哪些任务、谁来做、何时做、如何合并”。
```

## 5. Jarvis 当前代码映射

### 5.1 定义与加载

- `jarvis/agents/__init__.py`
  - `AgentDefinition` 只保存名称、描述、指令和来源文件。
- `jarvis/agents/loader.py`
  - 从 `agent.json`、`agent.yaml` 或 `SKILL.md` 加载定义。
  - 加载结果是元数据对象，不是可调用的 Agent Runtime。

### 5.2 领域指令选择

- `jarvis/agents/dispatcher.py`
  - 逐个调用 LLM 给每个 `AgentDefinition` 描述评分。
  - 只选择超过阈值的最高分定义。
  - 当前评分循环是串行执行。
- `jarvis/agent/nodes/agent_dispatch.py`
  - 把选择结果写入 `active_agent` 和 `agent_dispatch_score`。

这个过程完成的是“领域提示配置选择”，还没有发生 Worker 调度或任务委派。

### 5.3 使用

- `jarvis/agent/nodes/plan_and_call.py`
  - 读取 `active_agent.instructions`。
  - 把它追加到主 Agent 的 system prompt。
  - 仍然由同一个 `answer` Profile、同一个消息流和同一组注册工具完成请求。

### 5.4 主 Agent 控制流

`jarvis/agent/graph.py` 当前只有一条主 Agent 执行流：

```text
memory_load
  -> agent_dispatch
  -> rag_retrieve
  -> plan_and_call
  -> tool_node -> plan_and_call
  -> reflect -> plan_and_call 或 memory_write
  -> END
```

它具备：

- 单主 Agent 状态编排。
- 动态领域指令选择。
- 模型与工具循环。
- Reflection 有限重试。

当前 `AgentState` 只描述主 Agent 的会话和执行状态，没有任务 DAG、Worker 状态或聚合结果字段。当前实现也不具备：

- 可执行 Worker Agent 注册表。
- 多 Worker fan-out / fan-in。
- Worker 结果 reducer。
- Supervisor 对多个 Worker 的持续委派。
- Worker 级超时、取消、预算和状态隔离。

所以对当前架构最准确的描述是：

> Jarvis 是一个带领域指令路由、工具循环、RAG、Memory 和 Reflection 的单主 Agent Runtime，不是多 Agent 编排系统。

## 6. 选择、委派与编排

### 6.1 选择 Selection

```text
输入 -> 判断最匹配能力 -> 选择一个配置
```

Jarvis 当前的 `agent_dispatch` 属于这一层。结果是某组 instructions 被激活。

### 6.2 委派 Delegation

```text
主 Agent -> 构造 TaskSpec -> 调用 Worker -> 接收 TaskResult
```

委派要求被调用方是可执行单元，而不只是提示词。

### 6.3 编排 Orchestration

```text
目标
  -> 拆解任务
  -> 建立依赖
  -> 选择 Worker
  -> 顺序或并行执行
  -> 收集和校验
  -> 重试、降级或人工介入
  -> 汇总结果
```

一次调用一个 Worker 可以叫委派；管理多个任务的依赖、状态和结果，才构成编排。

## 7. 常见多 Agent 模式

### Skills

单个 Agent 按需加载专业提示词、知识或资源。它轻量、上下文集中，但不是独立 Worker。

Jarvis 当前的 `AgentDefinition` 机制最接近这个方向，只是由前置评分节点选择 Skill，而不是由主 Agent 在执行中主动加载。

### Router

Router 对输入分类，然后把任务发给一个或多个专业 Agent：

```text
query -> router -> worker A
                -> worker B
                -> worker C
             -> synthesize
```

Router 通常是一次分类步骤。它可以 fan-out 到多个 Worker，但不一定负责跨多轮持续规划。

Jarvis 当前只选一个领域指令，没有调用独立 Worker，也没有结果综合，因此还不是完整的多 Agent Router。

### Supervisor / Subagents

主 Agent 保存全局上下文，并把子任务委派给专业 Subagent：

```text
user <-> supervisor -> research worker
                    -> code worker
                    -> review worker
```

Worker 通常不直接面向用户。Supervisor 决定何时调用、给什么上下文，以及如何组合结果。

### Handoffs

控制权从一个 Agent 转交给另一个 Agent，新的 Agent 可以直接继续与用户交互。它适合客服阶段流转等需要“当前负责人”概念的多轮场景。

Handoff 关注“谁现在拥有控制权”，Supervisor 关注“主控如何委派并汇总”，不要混为一谈。

### Custom Workflow

使用显式图把确定性节点、Agent 节点、子图和人工确认组合起来。对于权限敏感、依赖明确、需要审计的投研任务，这通常比完全自由的 Agent 群更可靠。

## 8. Worker Agent 的任务契约

Worker Agent 应该通过稳定契约被调用，而不是接收一整段未经筛选的主对话。

### 8.1 `TaskSpec`

```text
task_id            唯一任务标识
parent_task_id     父任务或 trace 关系
objective          当前 Worker 要完成的单一目标
inputs             已验证的结构化输入
dependencies       必须先完成的任务 ID
constraints        权限、数据范围和业务限制
context_refs       允许读取的上下文或资料引用
allowed_tools      工具白名单
expected_schema    预期输出结构
deadline           最晚完成时间
retry_policy       可重试错误和次数
budget             token、费用、调用次数或资源上限
idempotency_key    供执行端实现重试幂等和结果复用
```

### 8.2 `TaskResult`

```text
task_id
status             succeeded / partial / failed / cancelled
output             结构化结果
evidence           来源、引用或工具证据
artifacts          代码、报告、数据文件等产物引用
metrics            latency、token、tool_calls、cost
error              稳定错误类型和安全错误信息
termination_reason 成功、失败、取消或预算终止原因
next_actions       建议的后续任务或人工确认点
```

### 8.3 契约的价值

- 编排器不需要理解 Worker 内部消息历史。
- Worker 可以从同进程子图替换成远程服务适配器。
- 结果可以被 reducer 稳定合并。
- 超时、重试、审计和评测有明确落点。
- 测试可以围绕输入输出边界，而不是依赖完整自然语言对话。

## 9. 状态与 Context 边界

多 Agent 系统不应该让每个 Worker 无限制复制全部上下文。

| 状态层 | 内容 | 主要所有者 |
|---|---|---|
| Conversation State | 用户消息、偏好、最终回复 | 主 Agent / Orchestrator |
| Task Graph State | 任务、依赖、状态、结果引用 | Orchestrator |
| Worker Local State | 当前子任务的 scratchpad、工具结果、局部重试 | Worker |

当前 Jarvis 的 `AgentState` 属于第一层和单主 Agent 执行状态，不能直接等同于未来的编排状态。

上下文下发遵循最小必要原则：

```text
全局目标
  -> 只取当前子任务需要的事实
  -> 加上允许使用的工具和输出契约
  -> 不复制无关历史和其他 Worker 的私有过程
```

Worker 的内部过程不应直接拼回主对话。编排器通常只接收结构化结果、证据、错误和必要摘要。

## 10. 编排生命周期

```text
1. Plan       把全局目标拆成任务
2. Validate   校验任务是否允许、输入是否完整
3. Schedule   根据依赖、优先级和资源选择可运行任务
4. Dispatch   构造 TaskSpec 并调用 Worker
5. Execute    Worker 在边界内执行
6. Collect    收集 TaskResult
7. Reduce     合并并处理冲突或部分失败
8. Evaluate   校验结果是否满足全局目标
9. Replan     必要时补任务、重试或降级
10. Stop      成功、失败、取消或达到预算后终止
```

终止条件必须由系统显式定义，例如：

- 所有必需任务成功且最终结果通过校验。
- 达到最大任务数或最大循环次数。
- 超过 deadline、token 或费用预算。
- 发生不可恢复错误或收到取消请求。
- 等待用户批准或补充信息。

## 11. 任务 DAG、fan-out 与 fan-in

多任务不等于所有任务都能并行。先把依赖画成有向无环图：

```text
                 -> research_worker --\
user objective ->                     -> code_worker -> backtest_worker -> reducer -> final answer
                 -> data_worker ------/
```

- `research_worker` 和 `data_worker` 没有依赖，可以 fan-out 并行执行。
- `code_worker` 依赖数据字段和研究约束，必须等待上游。
- `backtest_worker` 依赖可执行代码和配置，不能提前运行。
- reducer 在 fan-in 点合并各分支结果。

这里需要区分两类容易都被叫作 reducer 的机制：

- LangGraph 字段 reducer：并行分支更新同一个 state key 时，定义这些更新如何合并。若分支只写互不重叠的 key，则不一定需要字段 reducer。
- 业务 fan-in 聚合器：读取多个 `TaskResult`，处理冲突、部分失败和证据，再生成下游输入或最终结果。它通常是一个明确的聚合节点。

业务 fan-in 聚合器需要定义：

- 列表结果是追加、去重还是排序。
- 同一字段冲突时谁优先。
- 合并顺序是否必须确定。
- 部分成功是否允许继续。
- 输出如何保留来源和任务 ID。

如果多个并行分支写同一个 state key 却没有字段 reducer，可能发生并发更新错误；如果没有明确的业务聚合规则，结果则可能冲突、丢失来源或难以复现。

## 12. 并行的条件与工程约束

只有满足下面条件的任务才适合并行：

- 子任务之间没有未满足的数据依赖。
- 不会竞争修改同一个外部资源。
- 结果存在明确的合并规则。
- 外部 Provider、工具和数据库允许相应并发。
- 总成本和资源预算允许。

并行执行还需要控制：

- `max_concurrency`：避免 Worker 数量失控。
- rate limit：遵守 LLM 和工具 Provider 限额。
- deadline propagation：子任务不能超过全局截止时间。
- cancellation propagation：全局取消后停止不再需要的 Worker。
- idempotency：执行端要基于幂等键做持久化去重、原子占位或复用已有结果，并要求下游副作用接口遵守该键。
- backpressure：下游处理不过来时限制上游派发。
- partial failure：定义 Worker 失败后是降级、重试还是终止。
- observability：每个 Worker 继承 `trace_id` 并产生自己的 `task_id`。

并行不是默认优化。LLM 调用并行会同时放大费用、限流风险和失败面，应先证明任务独立且延迟收益值得。

## 13. ToolNode 并行不等于多 Agent 并行

一次 AIMessage 可以包含多个 tool calls。具体 LangGraph 版本和执行模式可能并发运行这些工具，但即使工具同时执行，仍然是：

- 同一个主 Agent 做出的行动决策。
- 同一轮消息中的多个工具调用。
- 同一个主图状态和后续 `plan_and_call`。
- 工具只返回动作结果，没有独立目标和 Agent Loop。

所以：

```text
多个工具同时执行
  != 多个 Worker Agent 并行完成不同子任务
```

判断标准仍然是：执行单元有没有独立的任务契约、上下文、状态、循环和结果边界。

## 14. Memory 与持久化一致性

多 Worker 直接写共享 Conversation Memory 容易产生：

- 并发覆盖或顺序错乱。
- 中间草稿污染长期记忆。
- 未通过校验的结论被当成事实。
- 不同用户或任务的上下文串线。
- 重试造成重复写入。

更稳妥的默认策略是：

```text
Worker 写局部结果或临时 artifact
  -> Orchestrator 收集
  -> Validator / Reducer 校验
  -> 统一提交最终 Conversation Memory
```

如果 Worker 必须写持久化数据，需要命名空间隔离、幂等键或版本号、来源时间戳、冲突策略、审计记录，以及敏感写操作的权限或人工确认。

## 15. 失败语义

| 失败类型 | 常见处理 |
|---|---|
| 输入不完整 | 请求用户补充，不盲目重试 |
| Worker 不匹配 | 重新路由或重新规划 |
| 临时网络/限流 | 有退避的有限重试 |
| 工具参数错误 | 修正参数后重试 |
| 权限不足 | 立即停止并返回可审计错误 |
| Worker 超时 | 取消、降级或转后台任务 |
| 部分分支失败 | reducer 根据必需/可选任务决定 |
| 结果互相冲突 | 启动验证任务或人工审查 |
| 超出预算 | 停止新增任务并返回部分结果 |

重试策略应归属正确层级：

- Worker 内部重试局部、可恢复错误。
- Orchestrator 决定是否重新委派、更换 Worker 或修改任务。
- Provider SDK、Worker 和 Orchestrator 不能各自无上限重试，否则会形成重试放大。

## 16. 可观测性与评测

多 Agent trace 至少需要：

```text
trace_id
task_id
parent_task_id
worker_name
task_status
dependency_ids
started_at / finished_at
model / tool_calls
token_usage / cost
retry_count
termination_reason
result_schema_valid
error_type
```

关键指标包括全局任务完成率、Worker 成功率和超时率、平均 fan-out 数量、关键路径延迟、并行延迟收益、Worker 成本、重新规划率、人工接管率、reducer 冲突率和证据覆盖率。

## 17. Jarvis 的推荐演进路径

不要直接从当前单主 Agent 跳到分布式 Agent 集群。

### 阶段 0：保持当前语义清晰

- 明确 `AgentDefinition` 是领域指令定义。
- 区分它与 Jarvis 主 Agent Runtime。
- 记录 `agent_dispatch` 的选择结果、耗时和成本。

### 阶段 1：能力清单配置化

逐步让定义包含默认模型 Profile、允许工具、领域知识来源和输入输出描述。这一阶段仍然可以是单主 Agent Runtime。

### 阶段 2：引入 Worker 契约

- 定义 `TaskSpec` 和 `TaskResult`。
- 先实现一个同进程 Worker 或子图。
- 让主流程通过稳定接口委派。
- 加入 Worker 级超时、预算、trace 和测试。

### 阶段 3：Supervisor 顺序委派

- 先支持任务拆解和顺序依赖。
- 让 Supervisor 收集 Worker 结果并统一回答。
- 验证 context 裁剪、错误处理和 Memory 所有权。

### 阶段 4：受控并行

- 引入任务 DAG、fan-out / fan-in 和 reducer。
- 为外部 Provider 设置并发预算。
- 实现取消、部分失败和确定性合并。

### 阶段 5：按需要拆分远程 Worker

只有在独立扩缩容、资源隔离、团队边界或长任务队列确实需要时，再把某类 Worker 拆成远程服务。

## 18. 量化投研场景示例

用户目标：

```text
比较成交量、波动率和估值三个因子，生成研究结论和可复现回测。
```

一种任务图是：

```text
plan -> research_worker --------------------------------\
     -> data_worker -> factor_code_worker -> backtest_worker -> review_worker -> synthesize
```

- `data_worker`：确认字段、时间范围、缺失值和数据权限。
- `research_worker`：检索因子定义、历史研究和风险说明。
- `factor_code_worker`：基于已确认的数据契约生成代码和测试。
- `backtest_worker`：在沙箱中运行回测并返回结构化指标。
- `review_worker`：检查数据泄漏、未来函数、结论证据和可复现性。
- Orchestrator：管理依赖、并行、预算、人工确认和最终汇总。

这里 `research_worker` 可以与 `data_worker` 并行，但 `backtest_worker` 不能早于代码和数据契约。是否并行由依赖决定，不由“有几个 Agent”决定。

## 19. Node、Tool、Worker 和服务的判断规则

| 需求特征 | 更适合 |
|---|---|
| 单一、确定性的图内步骤 | Node |
| 一个边界明确的外部动作 | Tool |
| 需要局部目标、上下文、工具和执行循环 | Worker Agent |
| 需要管理多个任务和结果 | Orchestrator |
| 需要独立扩缩容、资源隔离或跨系统复用 | 独立服务 |

同一个 Worker 可以作为图中的 Node 被调用，也可以被包装成 Tool，还可以部署成远程服务。这些是不同维度，不要做一一对应。

## 20. 面试表达

### 30 秒版本

> Jarvis 当前要区分两种 Agent 含义：主 LangGraph 是真正可执行的 Agent Runtime，而 `AgentDefinition` 只是动态选择的领域提示词配置。选中后，instructions 被注入同一个主 Agent 的 system prompt，并没有启动独立 Worker。Worker Agent 应该接收结构化 TaskSpec，拥有隔离的 context、工具和有限执行循环，并返回 TaskResult；Orchestrator 则负责拆任务、管理依赖、并行调度、汇总结果、处理失败和控制终止。

### 2 分钟版本

> Jarvis 的主 LangGraph 已经是可执行 Agent Runtime，它有状态、模型工具循环、RAG、Memory 和 Reflection。但 `.agents/skills` 加载的 `AgentDefinition` 只有 name、description、instructions 和 source_file。`agent_dispatch` 对这些定义逐个评分，选中一个后把 instructions 注入主 Runtime，所以这部分更接近 Skill 或领域 Persona 路由，而不是多 Agent 执行。
>
> Worker Agent 是可执行的子任务边界。它接收包含目标、输入、依赖、工具白名单、输出 schema、deadline 和预算的 TaskSpec，在隔离 context 里运行自己的模型工具循环，然后返回带状态、结果、证据、指标和错误的 TaskResult。Worker 可以是同进程子图，也可以是远程服务，部署方式不决定它是不是 Agent。
>
> Agent Orchestrator 负责全局控制：把目标拆成任务 DAG，根据依赖选择顺序或 fan-out 并行，向 Worker 下发最小必要 context，在 fan-in 点通过 reducer 合并结果，并统一处理重试、取消、预算、权限、Memory 和最终校验。Jarvis 如果演进到这一层，应该先做 Worker 契约和顺序委派，再增加受控并行，而不是直接拆成多个服务。

## 21. 学习检查

1. `AgentDefinition` 为什么不是 Worker Agent？
2. Jarvis 主 Agent Runtime 为什么仍然属于可执行 Agent？
3. `agent_dispatch` 完成的是选择、委派还是编排？
4. Worker Agent 是否必须独立部署？为什么？
5. Node 和 Worker Agent 的关键区别是什么？
6. ToolNode 同时执行多个工具为什么不等于多 Agent 并行？
7. 哪些并行状态更新需要 LangGraph 字段 reducer？它与业务 fan-in 聚合器有什么区别？
8. Conversation State、Task Graph State 和 Worker Local State 应由谁管理？
9. Worker 超时与 Provider 限流应该分别在哪一层处理？
10. Jarvis 演进到多 Agent 的第一步为什么不是拆微服务？

## 22. 练习

### 练习一：识别当前能力

沿着下面文件画出 Jarvis 当前执行路径，并标注“配置、路由、执行、校验或持久化”：

- `jarvis/agents/loader.py`
- `jarvis/agents/dispatcher.py`
- `jarvis/agent/nodes/agent_dispatch.py`
- `jarvis/agent/nodes/plan_and_call.py`
- `jarvis/agent/graph.py`

### 练习二：设计 Worker 契约

为“网页研究 Worker”写一份 `TaskSpec` 和 `TaskResult`，至少包含 URL 或研究问题、域名和工具权限、超时和最大网页数、引用和输出 schema，以及页面失败、内容冲突和提示注入的处理。

### 练习三：画任务 DAG

为下面目标画出依赖图，指出可以并行的任务和 reducer 规则：

```text
根据三份研报和一份行情数据，生成因子代码、运行回测并输出风险审查报告。
```

### 练习四：做架构判断

判断下面能力应该是 Node、Tool、Worker Agent 还是独立服务：

- 敏感词检查。
- 行情数据查询。
- 多轮代码生成、测试和修复。
- GPU 回测集群。
- 最终报告证据校验。

## 23. 官方延伸阅读

- [LangChain Multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent/index)
- [Subagents and supervisor pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)
- [Router pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/router)
- [Handoffs pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)
- [Skills pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)
- [LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)
- [LangGraph concurrent state update rules](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE)

阅读这些资料时继续使用本章的判断方法：框架把某个组件叫作 Agent，不代表它自动拥有独立任务契约、状态边界和编排能力。
