# 04 LLM Router 与模型抽象

## 本章目标

学完本章，你应该能：

- 解释为什么 Agent 项目需要模型抽象层。
- 理解 `"provider/model_id"` 这种模型规格的设计。
- 区分主模型和反思模型。
- 判断新增模型厂商时应改哪些地方。

## 核心概念

Agent 项目通常不应该把业务逻辑绑定死在某一个模型厂商上。模型会迭代，价格会变化，调用稳定性会变化，不同任务也可能需要不同模型。

Jarvis 用 LLM Router 处理这件事。调用方可以传入类似：

```text
siliconflow/deepseek-ai/DeepSeek-V4-Pro
openai/gpt-4o
claude/claude-opus-4-7
```

Router 做两步：

1. 拆出 provider 和 model_id。
2. 找到对应 Provider，构造 LangChain ChatModel。

这样 Agent 节点只关心“我要一个可调用的模型”，不关心这个模型来自 OpenAI、Claude 还是 SiliconFlow。

Jarvis 还把主模型和反思模型分开：

- `ANSWER_LLM`：负责生成回答和工具调用。
- `REFLECT_LLM`：负责给答案评分。

这种拆分体现了一个 Agent 工程判断：不同任务可以用不同模型。生成答案需要强推理和工具调用能力；评分可能需要更稳定、更便宜或更严格的模型。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/llm/base.py`：看 Provider 抽象接口。
2. `jarvis/llm/router.py`：看模型规格解析和 provider registry。
3. `jarvis/llm/siliconflow.py`：看兼容 OpenAI API 的自定义 base_url。
4. `jarvis/llm/openai.py`：看 OpenAI provider。
5. `jarvis/llm/claude.py`：看 Claude provider。
6. `jarvis/config.py`：看默认模型配置。
7. `jarvis/agent/nodes/plan_and_call.py` 和 `jarvis/agent/nodes/reflect.py`：看不同节点如何选模型。

## 关键设计问题

为什么不直接在 `plan_and_call.py` 里写 OpenAI 调用？

因为那会把“Agent 规划逻辑”和“模型厂商接入逻辑”绑在一起。以后要换模型、做 AB 测试、加 fallback 或按请求覆盖模型时，改动会扩散到业务节点。

为什么模型规格用 `"provider/model_id"`？

这个格式简单、可读、适合从环境变量和 API 请求传入。它把“谁提供模型”和“具体哪个模型”放在同一个字符串里，同时仍然容易解析。

为什么 provider 不存在返回 400，provider 不可用返回 502？

provider 不存在通常是调用方传错参数，属于请求错误。provider 不可用通常是上游服务、密钥、网络或厂商问题，属于网关或依赖错误。错误语义清楚，API 调用方更容易处理。

## 学习检查

1. `get_model` 做了哪两件核心事？
2. `ANSWER_LLM` 和 `REFLECT_LLM` 为什么要分开？
3. 新增一个模型厂商时，应该新增 Provider 还是改 Agent 节点？
4. `"openai/gpt-4o"` 中 provider 和 model_id 分别是什么？
5. provider 不存在和 provider 不可用为什么应该区分？

## 小练习

设计一个新 provider：`local/llama-3`。不用写代码，只回答：

- 需要新增哪个文件？
- 需要实现哪个接口？
- `REGISTRY` 里应该新增什么？
- API 请求体是否需要变化？
- Agent Graph 是否需要变化？
