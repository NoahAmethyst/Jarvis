# 06 Memory 与 RAG

## 本章目标

学完本章，你应该能：

- 区分短期上下文、长期对话记忆和知识库记忆。
- 理解 PostgreSQL conversation memory 的作用。
- 理解 Qdrant vector memory 的作用。
- 说明 RAG 在 Agent 流程中为什么放在规划前。

## 核心概念

Agent 的记忆不是一个单一概念。至少有三类：

- 短期上下文：本次请求中的消息和工具结果，保存在 `messages`。
- 长期对话记忆：过去和用户的对话，保存在 PostgreSQL。
- 知识库记忆：可被语义检索的文档或工具结果，保存在 Qdrant。

Jarvis 的 `memory_load` 节点从 PostgreSQL 读取用户历史对话，写入 `history`。`rag_retrieve` 节点用当前 query 去 Qdrant 检索相关知识，写入 `rag_context`。

然后 `plan_and_call` 把这些信息拼进模型输入：

- system prompt
- RAG 上下文
- 历史对话
- 本轮消息

这体现了 RAG 的核心位置：先检索，再让模型决策。模型不是凭空回答，而是在已有知识和当前问题基础上生成答案或决定调用工具。

## Jarvis 代码地图

建议阅读顺序：

1. `jarvis/agent/nodes/memory_load.py`：看历史对话加载。
2. `jarvis/memory/conversation.py`：看 PostgreSQL 表结构和读写函数。
3. `jarvis/agent/nodes/rag_retrieve.py`：看知识检索节点。
4. `jarvis/memory/knowledge.py`：看 Qdrant collection、embedding、store 和 retrieve。
5. `jarvis/agent/nodes/memory_write.py`：看最终对话和工具结果如何写回。
6. `jarvis/config.py`：看 `POSTGRES_DSN`、`QDRANT_URL`、`EMBED_MODEL`、`VECTOR_SIZE`。

## 关键设计问题

为什么对话历史用 PostgreSQL，而知识库用 Qdrant？

对话历史适合按用户和时间查询，结构清晰，关系数据库足够。知识库检索需要按语义相似度找内容，向量数据库更适合。

为什么 `rag_retrieve` 放在 `plan_and_call` 前面？

因为模型做规划和回答时需要先看到相关知识。如果先让模型回答，再检索，就失去了 RAG 的主要价值。

为什么存储组件不可用时可以降级？

Jarvis 的 `memory_load` 和 `rag_retrieve` 捕获异常后返回空历史或空上下文。这意味着 PostgreSQL 或 Qdrant 暂时不可用时，对话仍然可以继续，只是少了历史或知识增强。对 Agent 后端来说，这是可用性和答案质量之间的取舍。

为什么工具结果可能写入知识库？

工具返回的长内容可能有复用价值，比如网页正文或搜索结果。Jarvis 在 `memory_write` 中判断 ToolMessage 内容长度超过阈值后写入 Qdrant，让未来问题可以检索到。

## 学习检查

1. `history` 和 `rag_context` 分别来自哪里？
2. PostgreSQL 和 Qdrant 各自解决什么问题？
3. 为什么 RAG 检索要发生在模型规划前？
4. 存储不可用时 Jarvis 如何降级？
5. 工具结果自动入库有什么好处和风险？

## 小练习

设计一个“用户画像记忆”能力，不写代码，只回答：

- 它应该存 PostgreSQL 还是 Qdrant？
- 它应该在 `memory_load` 读，还是在 `rag_retrieve` 读？
- 它应该如何避免把用户临时说法误存成长期偏好？
- 它应该如何让用户删除？
