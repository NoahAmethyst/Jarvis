# 10 节点设计与边界判断

## 本章目标

学完本章，你应该能：

- 解释 LangGraph 中"节点"是什么，它的职责边界在哪里。
- 区分"加一个节点"和"创建一个新 Agent"各自适合什么场景。
- 根据一个新需求，判断应该插入节点还是拆分服务。
- 用知识提取需求为例，独立设计节点位置和状态字段。

## 核心概念

### 节点是什么

节点（Node）是 LangGraph 图中的一个执行单元。它接收当前的 AgentState，做一件事，然后返回更新后的 AgentState。

```text
输入：AgentState（当前完整状态）
执行：一段逻辑（调用 LLM、读数据库、分类文本……）
输出：AgentState（更新后的状态）
```

节点不知道自己前面是谁、后面是谁。它只关心：从 state 里取我需要的字段，处理完，把结果放回 state。

节点的职责应该单一。"加载历史记忆"是一个节点，"检索知识库"是另一个节点，"让模型规划和调用工具"是另一个节点。不要把多件事塞进一个节点。

### 节点 vs Agent

这是初学者最容易混淆的边界。

| 对比维度 | 节点 | 独立 Agent |
|---------|------|-----------|
| 部署边界 | 同一个进程内 | 独立进程 / 独立服务 |
| 扩缩容 | 随主服务一起 | 独立扩缩 |
| 跨系统复用 | 仅限当前图 | 可被多个系统调用 |
| 通信方式 | 直接访问 AgentState | HTTP / gRPC / 消息队列 |
| 适合场景 | 流程内的一个步骤 | 独立域、独立团队、高流量分离 |

**判断规则：**

如果你能把需求描述成"在现有流程的某个位置，多做一件事"——那就是节点。

如果你能把需求描述成"这件事需要独立部署、独立扩容、或者被别的系统调用"——才考虑 Agent。

### 节点职责分离原则

每个节点只做一件事。

错误示范：把"分类用户输入"和"写入知识库"塞进同一个节点。

正确做法：

```text
knowledge_extract  →  分类用户输入，把事实内容挂到 state
memory_write       →  读取 state 里的待写内容，统一写入 Qdrant
```

`memory_write` 不应该做分类，`knowledge_extract` 不应该直接写数据库。这样每个节点可以独立测试、独立替换分类策略。

## 用知识提取需求练习判断

**需求：** 用户输入时，自动识别内容是"事实"（新闻、理论）还是"主观内容"（观点、偏好），把事实内容存入知识库。

**第一步：确认是节点还是 Agent**

这个需求是"在现有流程的某个位置，多做一件事（分类 + 挂到 state）"。不需要独立部署，不需要跨系统调用。结论：**新节点**。

**第二步：确认节点位置**

节点要在 `memory_write` 之前，因为 `memory_write` 负责实际写入，`knowledge_extract` 只负责判断"该不该写、写什么"。

```text
memory_load → rag_retrieve → plan_and_call ⇄ tool_node → reflect → knowledge_extract → memory_write
```

**第三步：确认 AgentState 需要新字段**

节点之间通过 AgentState 传递数据。`knowledge_extract` 处理完后需要把结果交给 `memory_write`，所以要在 state 里加一个字段：

```python
# jarvis/agent/state.py
@dataclass
class AgentState:
    # ...已有字段...
    pending_knowledge: list[str] = field(default_factory=list)  # 新增
```

`knowledge_extract` 写这个字段，`memory_write` 读这个字段并写 Qdrant。

**第四步：节点实现思路**

```python
# jarvis/agent/nodes/knowledge_extract.py

CLASSIFY_PROMPT = """
Classify the following text. Return JSON only.
{"type": "fact|subjective|both", "extracted_facts": ["..."]}

fact = objective, verifiable (news, theory, data)
subjective = opinion, preference, emotion

Text: {text}
"""

async def knowledge_extract(state: AgentState) -> AgentState:
    user_input = state["messages"][-1].content
    result = await llm.ainvoke(CLASSIFY_PROMPT.format(text=user_input))
    parsed = json.loads(result.content)

    if parsed["type"] in ("fact", "both"):
        state["pending_knowledge"] = parsed["extracted_facts"]

    return state
```

节点本身不写数据库，只把分类结果放进 state。`memory_write` 里消费 `pending_knowledge`，写入 Qdrant 时带上 `type: "fact"` 元数据标签。

## Jarvis 代码地图

理解节点设计，建议按此顺序阅读：

1. `jarvis/agent/state.py`：看 AgentState 有哪些字段，节点之间通过什么传递数据。
2. `jarvis/agent/graph.py`：看节点如何注册到图，边和条件路由如何连接节点。
3. `jarvis/agent/nodes/memory_load.py`：最简单的节点，看节点的标准结构。
4. `jarvis/agent/nodes/reflect.py`：有条件分支的节点，看 state 字段如何影响路由。
5. `jarvis/agent/nodes/memory_write.py`：写操作节点，看节点如何与外部存储交互。

## 关键设计问题

**为什么不在 `memory_write` 里直接做分类？**

职责混叠。`memory_write` 的职责是"把该写的内容写进去"，分类是推理逻辑，属于不同层次的关注点。混在一起后，想替换分类策略（比如换一个 LLM、换成规则分类）时，要改到存储逻辑里，违反单一职责。

**节点数量多了会不会很乱？**

不会，反而更清晰。每个节点一个文件、一个职责，比一个大函数里写 300 行条件分支更容易读懂和维护。图结构本身就是显式的执行路径文档。

**节点里可以直接访问数据库吗？**

可以，但要注意：节点应该通过依赖注入或全局客户端访问数据库，不要在节点内部创建连接。Jarvis 里数据库客户端在启动时初始化，节点直接使用。

## 学习检查

1. 节点的输入和输出分别是什么？
2. "用户输入分类"这个能力，放节点还是独立 Agent？判断依据是什么？
3. 两个节点之间如何传递数据？
4. 为什么 `knowledge_extract` 不直接写 Qdrant，而是先放进 `pending_knowledge`？
5. 节点职责单一有什么好处？

## 小练习

不用写代码，只做设计判断：

假设 Jarvis 需要新增一个能力：**检测用户输入是否包含敏感词，如果包含则直接返回拒绝回复，不进入后续流程**。

回答以下问题：

1. 这个能力是新节点还是新 Agent？
2. 应该插入在图的哪个位置？（提示：尽可能早）
3. 需要在 AgentState 加字段吗？加什么？
4. 节点检测到敏感词后，如何让图跳过后续节点直接结束？（提示：看 `_route_after_reflect` 的做法）
