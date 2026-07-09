# 07 Reflection 与自我修正

## 本章目标

学完本章，你应该能：

- 解释 Reflection 在 Agent 中的作用。
- 理解自评分、阈值和重试循环。
- 判断 Reflection 什么时候有价值，什么时候只是成本。
- 说明 `low_confidence` 的产品意义。

## 核心概念

Reflection 是让模型或另一个模型检查当前答案质量。它不是让系统变得绝对正确，而是增加一次质量控制机会。

Jarvis 的 Reflection 流程是：

```text
从 messages 中找最后一个非工具调用的 AI 答案
  -> 用 reflect_llm 评分 0.0 到 1.0
  -> 分数低于阈值且重试次数未达上限：回到 plan_and_call
  -> 否则写入 final_answer
  -> 达上限仍低分：low_confidence = true
```

这个设计把“回答生成”和“回答评估”拆开。主模型负责回答，评分模型负责判断准确性、完整性和是否回答原始问题。

Reflection 的价值在于处理明显不完整、偏题或格式失败的答案。它的成本是额外模型调用、额外延迟，以及评分模型本身也可能误判。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/agent/nodes/reflect.py`：看答案提取、评分 prompt、分数解析、低置信度判断。
2. `jarvis/agent/graph.py`：看 `_route_after_reflect` 如何决定重试或结束。
3. `jarvis/config.py`：看 `REFLECTION_SCORE_THRESHOLD` 和 `REFLECTION_MAX_RETRIES`。
4. `jarvis/api/http/routes.py`：看 `low_confidence` 如何返回给调用方。

重点观察：Reflection 不直接改写答案，而是通过状态字段影响 graph 路由。

## 关键设计问题

为什么 Reflection 不直接调用工具？

Reflection 的职责是评估当前答案，不是执行下一步行动。下一步仍然交给 `plan_and_call`，因为规划节点才拥有模型、工具和上下文的完整决策权。

为什么需要最大重试次数？

没有上限的自我修正会造成无限循环、成本失控和响应卡死。Agent 系统里，所有模型驱动的循环都必须有明确停止条件。

为什么 `low_confidence` 比“强行返回失败”更有用？

很多场景下，低置信答案仍然可能对用户有参考价值。结构化标记让上层产品可以选择展示提醒、触发人工审核或要求用户补充信息。

什么时候不该用 Reflection？

如果任务非常简单、模型稳定、延迟敏感或成本敏感，Reflection 可能不划算。工程设计不能把每个质量问题都交给另一个模型调用解决。

## 学习检查

1. Reflection 评分依据是什么？
2. Jarvis 如何避免 Reflection 无限循环？
3. `low_confidence` 在什么时候为 true？
4. Reflection 为什么更新 state，而不是直接控制 API 返回？
5. 哪些场景下 Reflection 成本可能大于收益？

## 小练习

设计一个更严格的 Reflection prompt，不写代码，只写设计：

- 它应该检查哪些维度？
- 是否应该要求评分模型输出理由？
- 如果输出理由，如何避免破坏当前只解析数字的代码？
- 评分失败时默认 0.5 是否合理？为什么？
