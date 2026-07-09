# 补充 react-pattern.md 容错设计章节

## Goal

`notes/react-pattern.md` 第 6 条只一句带过容错，
但 `03/notes.md` 有完整的"容错设计是 ReAct 循环的必要组成"内容（格式失败最多 2 次重试策略）。
本任务将该策略补全进主笔记。

## Requirements

在 `notes/react-pattern.md` 的第 6 条（"Function Calling 是工程化的 ReAct"）
**之前**插入独立的第 6 条"容错设计是 ReAct 循环的必要组成"，
原第 6 条顺延为第 7 条。

新增内容覆盖：
- 格式解析失败不能崩溃，要给 LLM 重试机会
- 重试提示模板（告知正确格式）
- "最多 2 次重试"策略的权衡（给机会 vs 避免无限消耗 token）

## Acceptance Criteria

- [ ] 新第 6 条标题：`### 6. 容错设计是 ReAct 循环的必要组成`
- [ ] 原第 6 条（Function Calling）顺延为第 7 条，标题序号更新
- [ ] 末尾元数据无需变动（日期已是 2026-06-27）
- [ ] git commit 提交

## Technical Notes

- 内容来源：`projects/03-react-agent/notes.md` → "### 6. 容错设计"
- 目标文件：`notes/react-pattern.md`
