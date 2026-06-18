# Agent Dispatch — Design Spec

**日期：** 2026-06-18
**状态：** 已确认

---

## 1. 概述

为 Jarvis 增加自定义 Agent 语义匹配调度机制。用户将 agent 定义文件放入项目目录，Jarvis 启动后自动读取，每次请求用 LLM 打分判断输入与各 agent 的契合度，契合度最高且超过阈值的 agent 的 instructions 会注入 system prompt，影响本次对话行为。契合度不足时完全降级为现有默认行为，对调用方透明。

---

## 2. Agent 文件格式

存储目录：`.agents/skills/<agent-name>/`（复用现有目录约定）

统一解析器支持三种格式，解析优先级：`agent.json` → `agent.yaml` → `SKILL.md + agents/openai.yaml`

### 格式 A — Claude Code 格式（现有）

```
.agents/skills/<name>/
├── SKILL.md
└── agents/openai.yaml
```

`SKILL.md` frontmatter 提供 `description`，`agents/openai.yaml` 提供 `display_name` 和 `short_description`。`instructions` 取 `SKILL.md` 正文。

### 格式 B — OpenAI Assistants JSON

```
.agents/skills/<name>/agent.json
```

```json
{
  "name": "...",
  "description": "...",
  "instructions": "...",
  "tools": []
}
```

### 格式 C — 自定义 YAML

```
.agents/skills/<name>/agent.yaml
```

```yaml
name: "..."
description: "..."
instructions: "..."
```

### 内部统一表示

所有格式解析为：

```python
@dataclass
class AgentDefinition:
    name: str
    description: str   # 用于 LLM 打分
    instructions: str  # 注入 system prompt
    source_file: str   # 来源路径，调试用
```

---

## 3. 架构

### 图结构变化

```
memory_load → agent_dispatch → rag_retrieve → plan_and_call → tool_node → reflect → memory_write
```

`agent_dispatch` 插入 `memory_load` 与 `rag_retrieve` 之间。

### AgentState 新增字段

```python
active_agent: AgentDefinition | None   # 选中的 agent，None = 走默认
agent_dispatch_score: float            # 最高匹配分，调试用
```

---

## 4. agent_dispatch 节点逻辑

```
1. 扫描 AGENTS_DIR 目录，按优先级解析所有 AgentDefinition
2. 若无可用 agent → 返回 {active_agent: None, agent_dispatch_score: 0.0}
3. 用 REFLECT_LLM 对每个 agent 打分（0.0-1.0）
   prompt 包含：用户 query + agent description
   要求 LLM 只返回一个 0.0-1.0 的小数
4. 取最高分 agent
5. 最高分 < AGENT_DISPATCH_THRESHOLD → active_agent = None
6. 最高分 ≥ AGENT_DISPATCH_THRESHOLD → active_agent = 该 AgentDefinition
```

打分复用 `REFLECT_LLM`，不新增模型配置项。

---

## 5. plan_and_call 节点改动

```python
system_content = "You are Jarvis, a helpful AI assistant. Answer questions accurately and completely."
if state.get("rag_context"):
    system_content += f"\n\nRelevant knowledge from memory:\n{state['rag_context']}"
if state.get("active_agent"):
    system_content += f"\n\n{state['active_agent'].instructions}"
```

instructions 追加在 system prompt 末尾，不替换默认内容。

---

## 6. 新增配置项

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `AGENTS_DIR` | `.agents/skills` | agent 文件扫描目录 |
| `AGENT_DISPATCH_THRESHOLD` | `0.6` | 触发 agent 的最低匹配分 |

---

## 7. 错误处理与降级

| 场景 | 行为 |
|------|------|
| `AGENTS_DIR` 不存在或为空 | 跳过 dispatch，`active_agent = None`，无告警 |
| agent 文件解析失败 | 跳过该 agent，`logger.warning`，继续处理其余 agent |
| LLM 打分调用失败 | 跳过 dispatch，`active_agent = None`，`logger.warning` |

所有失败路径对 HTTP/gRPC 调用方完全透明，不新增错误码。

---

## 8. 新增文件

```
jarvis/
├── agents/
│   ├── __init__.py
│   ├── loader.py       # 目录扫描 + 三种格式解析 → AgentDefinition
│   └── dispatcher.py   # LLM 打分 + 阈值决策
└── agent/
    └── nodes/
        └── agent_dispatch.py   # LangGraph 节点，调用 loader + dispatcher
```

修改文件：
- `jarvis/agent/state.py` — 新增 `active_agent`、`agent_dispatch_score`
- `jarvis/agent/graph.py` — 插入 `agent_dispatch` 节点
- `jarvis/agent/nodes/plan_and_call.py` — 读取 `active_agent` 注入 instructions
- `jarvis/config.py` — 新增 `AGENTS_DIR`、`AGENT_DISPATCH_THRESHOLD`

---

## 9. 测试策略

新增 `tests/unit/test_agent_dispatch.py`，覆盖：

- 目录为空 → `active_agent = None`
- 解析三种格式 → 正确生成 `AgentDefinition`
- 最高分 < 阈值 → `active_agent = None`
- 最高分 ≥ 阈值 → `active_agent` 为正确 agent
- LLM 打分失败 → 降级，主流程不中断
- `plan_and_call` 有 `active_agent` → instructions 追加进 system prompt

所有测试 mock LLM，无真实调用。
