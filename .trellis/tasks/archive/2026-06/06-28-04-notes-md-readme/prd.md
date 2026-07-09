# 补全 04 项目 notes.md 并修正 README 日期

## Goal

04-agent-reflection 项目内的 `notes.md` 目前是占位符，缺少实际踩坑记录；
`README.md` 的"最后更新"日期停留在 2026-06-27，但 fix commit 发生在 2026-06-28。
本任务补全项目内笔记、修正日期，使文档与实际实现对齐。

## Requirements

1. `projects/04-agent-reflection/notes.md`：用实际踩坑内容替换占位符，涵盖：
   - 双评估器参数不兼容 bug（`ground_truth=` vs `steps=` 参数路由，需 isinstance 判断）
   - 实体名文档不一致（`珊瑚礁城` → `珊瑚礁堡`，文档/prompt 需与知识库保持一致）
   - MAX_STEPS 结构性约束 vs 反思策略的边界（q07 需要 ≥12 步，反思无法突破步数上限）
   - 末尾指向 `notes/reflexion-pattern.md` 作为完整参考

2. `projects/04-agent-reflection/README.md`：将"最后更新"从 `2026-06-27` 改为 `2026-06-28`

## Acceptance Criteria

- [ ] `notes.md` 不再包含"待补充"占位符
- [ ] `notes.md` 包含上述 3 个踩坑条目，每条有"现象→根因→修复"结构
- [ ] `notes.md` 末尾有指向 `notes/reflexion-pattern.md` 的说明
- [ ] `README.md` 最后更新日期为 `2026-06-28`

## Definition of Done

- 两个文件修改完毕，内容准确
- git commit 提交

## Out of Scope

- 不修改 notes.md 以外的项目文件
- 不补充运行输出截图或示例输出
- 不修改 notes/reflexion-pattern.md（已经完整）

## Technical Notes

- 目标文件：
  - `projects/04-agent-reflection/notes.md`（当前 246 字节，纯占位符）
  - `projects/04-agent-reflection/README.md`（最后一行 `最后更新：2026-06-27`）
- 踩坑细节来源：上一个 session 的 fix commit `86c85e0`
