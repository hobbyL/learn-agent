# 提炼 03-react-agent 实战经验到 notes/react-pattern.md

## Goal

`notes/react-pattern.md` 目前停留在 2026-06-25 的初始规划稿，
全是理论描述，没有任何 03 项目的实战内容。
本任务把 03 实践中得到的核心经验追加进该文件，形成"理论 + 实战"完整笔记。

## Requirements

1. 在 `notes/react-pattern.md` 末尾（`**最后更新**` 标记之前）追加"从实践中学到的教训"章节
2. 收录以下 6 条经验（内容来源：`projects/03-react-agent/notes.md`）：
   - ReAct 的核心价值是"幻觉可审计"而非"让 LLM 不犯错"
   - 跳步 bug：LLM 把"计划写进 Thought"当成"已执行"——代码护栏对策
   - 模型能力是 ReAct 的天花板（ReAct 是放大镜）
   - ReAct vs Direct 真实性能对比（串行 7 步 vs 并行 4 步）
   - 虚构数据是验证工具依赖性的标准设计模式
   - Function Calling 是工程化的 ReAct（取舍分析）
3. 更新文件末尾的 `**最后更新**` 为 2026-06-27，`**来源项目**` 追加 03-react-agent

## Acceptance Criteria

- [ ] `notes/react-pattern.md` 新增"从实践中学到的教训"章节，共 6 条
- [ ] 每条经验有清晰标题 + 核心结论 + 必要示例（参考 tool-calling.md 的格式风格）
- [ ] 末尾元数据更新（日期 + 来源项目）
- [ ] 无其他文件改动
- [ ] git commit 提交

## Definition of Done

- 内容无遗漏（对照 03 notes.md 检查）
- 格式与 tool-calling.md 风格一致（标题层级、粗体关键词、代码块）

## Technical Approach

直接在 `notes/react-pattern.md` 的 `**最后更新**` 标记前插入新章节。
内容从 `projects/03-react-agent/notes.md` 的"学到的内容"章节提炼，
浓缩重点结论、去掉过程性叙述，保持与 `notes/tool-calling.md` 风格一致。

## Out of Scope

- 不修改 react-pattern.md 的现有理论内容
- 不修改其他 notes 文件
- 不改动 03 项目代码

## Technical Notes

- 内容来源：`projects/03-react-agent/notes.md` → "学到的内容"章节（6 条）
- 格式参考：`notes/tool-calling.md`（"从实践中学到的教训"章节的写法）
- 目标文件：`notes/react-pattern.md`
