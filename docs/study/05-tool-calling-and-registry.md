# 05 Tool Calling 与工具注册表

## 本章目标

学完本章，你应该能：

- 解释 Tool Calling 是什么。
- 理解工具注册表模式。
- 说明 LLM 如何决定是否调用工具。
- 理解 ToolNode 在 Jarvis 图中的位置。

## 核心概念

Tool Calling 是让模型不只生成文本，还能请求系统执行某个工具。模型不会自己真正访问网络或数据库；它只输出结构化的工具调用意图。系统接到这个意图后，执行对应函数，再把结果作为 ToolMessage 放回消息流。

Jarvis 当前有两个工具：

- `web_search`：通过 Tavily 搜索最新信息。
- `web_scrape`：抓取网页并提取正文。

工具注册表解决一个扩展问题：新增工具时，不希望每次都改 Agent 图。Jarvis 使用 `@register_tool` 装饰器把函数转成 LangChain `StructuredTool`，统一存入 registry。Graph 中的 ToolNode 只需要拿 `get_tools()`。

在 `plan_and_call` 中，模型通过 `bind_tools(get_tools())` 获得可用工具列表。模型看到工具描述后，可以选择直接回答，也可以输出 tool_calls。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/tools/registry.py`：看 `register_tool` 和 `get_tools`。
2. `jarvis/tools/search.py`：看 `web_search` 如何注册。
3. `jarvis/tools/scraper.py`：看 `web_scrape` 如何注册。
4. `jarvis/agent/nodes/plan_and_call.py`：看模型如何 bind tools。
5. `jarvis/agent/graph.py`：看 ToolNode 如何接入图。

注意 `jarvis/agent/graph.py` 顶部 import 了工具模块。这些 import 的副作用是执行装饰器注册工具。

## 关键设计问题

为什么工具不直接由 API 调用？

因为工具是 Agent 的行动能力，不是外部用户直接调用的业务接口。用户给目标，模型判断是否需要工具。API 如果直接决定调哪个工具，就变成普通后端工作流，不是 Agent 决策。

为什么工具需要 description？

模型选择工具时主要依赖工具名、参数结构和描述。描述写得不清楚，模型就可能不用工具，或在错误场景用工具。工具描述是给模型看的接口文档。

为什么新增工具仍然需要 import 模块？

装饰器注册发生在模块加载时。如果文件存在但从未 import，注册代码不会运行。Jarvis 当前在 `graph.py` 顶部 import `jarvis.tools.search` 和 `jarvis.tools.scraper`，确保工具进入 registry。

## 学习检查

1. Tool Calling 中，模型真正执行工具了吗？
2. `register_tool` 的作用是什么？
3. `get_tools()` 返回什么？
4. 为什么 `plan_and_call` 要调用 `bind_tools`？
5. 新增工具文件后，为什么还要确保它被 import？

## 小练习

设计一个 `weather_lookup` 工具，不写代码，只写接口说明：

- 工具名是什么？
- 输入参数是什么？
- description 应该怎么写，才能让模型知道何时调用？
- 工具失败时应该返回异常，还是返回可读错误信息？
- 这个工具结果是否应该进入知识库？为什么？
