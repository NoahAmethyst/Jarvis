# 03 LangGraph 执行图

## 本章目标

学完本章，你应该能：

- 解释 LangGraph 中节点、边和条件路由的作用。
- 画出 Jarvis 的完整执行图。
- 说明为什么 Agent 适合用图表达。
- 理解工具调用回路和 Reflection 重试回路。

## 核心概念

LangGraph 把 Agent 流程建模成状态图。节点是具体步骤，边是执行顺序，条件边根据 state 决定下一步去哪。

Jarvis 的主流程是：

```text
memory_load
  -> rag_retrieve
  -> plan_and_call
  -> 如果模型请求工具：tool_node -> plan_and_call
  -> 如果模型直接回答：reflect
  -> 如果评分低且未达重试上限：plan_and_call
  -> 否则：memory_write
  -> END
```

这里有两个关键回路：

- 工具回路：模型提出工具调用，系统执行工具，再把工具结果交还给模型。
- 反思回路：模型给出答案，评分模型判断质量，低分时回到规划节点重试。

图结构的价值在于显式表达“可能发生什么”。如果这些分支藏在一个函数里，读者很难看出 Agent 的控制流。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/agent/graph.py`：看 `StateGraph(AgentState)`、节点注册、边注册和 compile。
2. `jarvis/agent/nodes/plan_and_call.py`：看模型如何生成 AIMessage 或工具调用。
3. `jarvis/agent/nodes/reflect.py`：看 Reflection 如何更新评分和重试次数。
4. `jarvis/tools/registry.py`：看 ToolNode 使用的工具来自哪里。

重点函数：

- `_route_after_plan`
- `_route_after_reflect`

它们是 Jarvis 的条件路由核心。

## 关键设计问题

为什么 `tool_node` 执行后回到 `plan_and_call`？

工具只负责返回外部信息，不负责组织最终答案。模型拿到工具结果后，需要再次思考：工具结果是否足够？是否还要调用别的工具？还是可以回答用户？所以工具节点之后回到规划节点。

为什么 Reflection 低分时也回到 `plan_and_call`？

因为低分说明当前答案可能不完整、不准确或没有回答问题。回到 `plan_and_call` 可以让模型在已有消息和上下文基础上重新生成答案。

为什么 `memory_write` 放在最后？

因为系统应该保存最终稳定结果，而不是保存中间失败尝试。Jarvis 当前会遍历 `messages` 保存人类消息和无工具调用的 AIMessage，并把较长 ToolMessage 存入知识库。

## 学习检查

1. Jarvis 的入口节点是什么？
2. `_route_after_plan` 根据什么决定是否进入 `tool_node`？
3. `_route_after_reflect` 根据哪些字段决定是否重试？
4. 工具执行后为什么不直接结束？
5. Agent 图比长函数更适合表达什么？

## 小练习

不用改代码，写一段伪代码表达 Jarvis 图：

```text
start at memory_load
then ...
if ...
else ...
end
```

写完后检查：你的伪代码是否包含工具回路和 Reflection 回路。
