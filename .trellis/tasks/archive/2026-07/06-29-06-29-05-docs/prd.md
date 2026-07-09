# 05-streaming-agent：补充文档与测试观察记录

## Goal

将今天交互测试中实际观察到的三个现象补充进 `projects/05-streaming-agent/notes.md`，
让学习笔记完整记录"真实运行"而非仅理论推断的行为。

## What I already know

* `notes.md` 已有"踩坑记录"（4条）和"学习要点"（5条）两个分节
* 今天新观察到 3 个现象：
  1. **模型用记忆跳步**：问"天琴站站长多大了"时，Agent 直接调 `lookup("林夜霜","年龄")`，跳过了"先查站长名"这步——因为 system prompt 里已列出人名，模型推断出来了，不是真正的两步
  2. **并行工具调用实际触发**：问"天琴站和天琴号有什么区别？"时，第一轮 API 同时发出 index=0 和 index=1 两个 lookup，只用 3 个 chunk 完成（单次 API，两个并行调用）
  3. **Streaming 中途长间隔卡顿**：第二题回答中 chunk 88→89 之间约 7 秒空白（从 `"。"` 到 `'天琴号的'`）——模型在表格末尾和总结段落之间"思考"，streaming 体验下用户已看到表格，不是盯空屏

## Requirements

* 在"踩坑记录"或"学习要点"合适位置补充上述 3 条观察
* 保持现有文档风格（标题层级、代码块格式）
* 注明观察来自实际运行（不是理论推断）

## Acceptance Criteria

* [ ] notes.md 新增"模型记忆绕过工具调用"条目，含验证建议（新 session reset 后重测）
* [ ] notes.md 新增"并行工具调用实际触发"条目，含 timeline 数据引用
* [ ] notes.md 新增"Streaming 中途思考停顿"条目，含对用户体验意义的解释
* [ ] 文档风格与现有内容一致

## Out of Scope

* 修改代码
* 修改 README.md 或 progress/
* 添加自动化测试

## Technical Notes

* 目标文件：`projects/05-streaming-agent/notes.md`
* 现有结构：核心概念 → 踩坑记录（4条）→ 学习要点（5条）
* 新内容放到"踩坑记录"第5条（系统提示词记忆问题）和"学习要点"第6条（并行调用+停顿现象）
