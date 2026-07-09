# AI Agent 互动学习档案

本目录保存从共享 ChatGPT 对话整理出的 AI Agent 学习进度、知识结构和后续教学约定。它不是原始聊天记录的逐字转录，而是把对话中形成的认知、表达、练习和项目叙事整理成可持续复用的学习资料。

来源链接：

- <https://chatgpt.com/share/6a1d1fb6-558c-83ec-832d-749558e787e3>

## 当前结论

你的背景是 6 年后端开发，主力语言包括 Golang，同时熟悉 Java 和 Python，有微服务与 Kubernetes 实战经验。你的目标是在较短周期内转向 AI 方向岗位，重点关注 AI Agent 开发，以及模型服务化、部署平台、Kubernetes 相关工程能力。

当前学习定位：

- 你不是从编程零基础开始，而是从传统后端工程师转向 LLM 应用工程。
- 最大缺口不是后端工程能力，而是 LLM 应用抽象能力。
- 当前应该先打穿 LLM 应用工程基础，再进入 Agent 架构，再把已有 K8s 工程经验变成 AI 工程化优势。

## 文件说明

1. [learning-profile.md](learning-profile.md)
   - 记录你的学习背景、目标岗位、当前优势和短板。

2. [knowledge-map.md](knowledge-map.md)
   - 把对话中形成的核心知识点整理成系统化知识图谱，包括 LLM、RAG、Tool Calling、Memory、Agent 架构和工程化。

3. [staged-learning-plan.md](staged-learning-plan.md)
   - 按初阶、中阶、高阶整理成不限时间的阶段式学习计划。

4. [interview-agent-project.md](interview-agent-project.md)
   - 保存“多工具 Agent + AI 推理平台部署”的面试级项目叙事框架。

5. [teacher-protocol.md](teacher-protocol.md)
   - 定义后续我继续作为教学老师时的讲解方式、提问方式和纠偏标准。

## 后续学习使用方式

后续继续学习时，可以按下面方式引用本目录：

- “基于 `docs/study/interaction/knowledge-map.md`，继续讲 RAG。”
- “按 `teacher-protocol.md` 的方式考我 Memory 和 RAG 的区别。”
- “帮我把 `interview-agent-project.md` 继续扩展成 2 分钟面试口述稿。”
- “根据 `staged-learning-plan.md`，判断我现在处于哪个阶段，并安排今天的学习任务。”

## 与现有学习资料的关系

`docs/study` 下已有的 00-09 章节是围绕 Jarvis 项目代码展开的系统学习资料。本目录补充的是“互动学习上下文”：

- 00-09 章节回答“Jarvis 这个项目怎么理解”。
- interaction 目录回答“你现在学到了哪里、下一步该怎么教、如何面试表达”。
