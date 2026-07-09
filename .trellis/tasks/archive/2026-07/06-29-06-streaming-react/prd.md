# 06-streaming-react：流式 ReAct Agent

## Goal

实现流式 ReAct Agent，边流边解析推理链（Thought → Action → Observation → Final Answer），
通过逐字状态机着色展示，让 streaming 下的 ReAct 推理过程实时可视化。

## Requirements

- 流式 ReAct 循环：`stream=True` + 逐 chunk 状态机解析文本格式
- 状态机着色：Thought=灰, Action=黄, Observation=绿, Final Answer=亮白
- 小 buffer 回溯策略（≤15 字符）处理标签跨 chunk
- 跳步检测（从 03 移植），流式下实时标红提示
- 格式错误重试（最多 2 次）
- `--compare` 模式：同一问题跑非流式 ReAct vs 流式 ReAct
- `--demo` 模式：预设问题演示
- 交互模式：默认
- 知识库：复用 05 太空站联盟

## Acceptance Criteria

- [ ] 单步问题正确回答，Thought/Action 实时着色流出
- [ ] 多步链式推理（≥3 步），每步实时流式展示
- [ ] 跳步检测触发时实时标红提示
- [ ] `--compare` 展示流式 vs 非流式 ReAct 的步数、耗时一致性
- [ ] 标签跨 chunk 场景正确处理（buffer 机制）
- [ ] notes.md 记录踩坑 + 学习要点

## Definition of Done

- 真机验证通过（单步+多步+compare）
- notes.md 有实际运行观察
- README 完整（架构图+快速开始+文件说明）

## Technical Approach

### 核心文件

| 文件 | 职责 |
|------|------|
| `stream_parser.py` | 核心状态机（IDLE→THOUGHT→ACTION→ACTION_INPUT→FINAL_ANSWER），小 buffer 标签检测 |
| `streaming_react_agent.py` | 流式 ReAct 循环 = stream API + parser 逐 chunk 喂入 + 工具执行 |
| `non_streaming_react_agent.py` | 从 03 移植简化版作为 compare 对照 |
| `display.py` | ANSI 着色 + 实时输出 |
| `knowledge_base.py` | 复用 05 太空站联盟 |
| `tools.py` | 复用 05 工具层 |
| `main.py` | 入口：--demo / --compare / 交互 |

### 状态机设计

```
         ┌─────────────────────────────────────────────┐
         │                                             │
         ▼                                             │
    ┌─────────┐   "Thought:"   ┌───────────┐          │
    │  IDLE   │───────────────▶│  THOUGHT  │          │
    └─────────┘                └─────┬─────┘          │
                                     │                 │
                              "Action:"                │
                                     │                 │
                                     ▼                 │
                               ┌───────────┐          │
                               │  ACTION   │          │
                               └─────┬─────┘          │
                                     │                 │
                           "Action Input:"             │
                                     │                 │
                                     ▼                 │
                            ┌──────────────┐          │
                            │ ACTION_INPUT │──────────┘
                            └──────────────┘  (parse JSON → execute → feed Observation → back to IDLE)
         
         or from THOUGHT:
                              "Final Answer:"
                                     │
                                     ▼
                            ┌──────────────┐
                            │ FINAL_ANSWER │ → 结束
                            └──────────────┘
```

### Buffer 机制

- 维护 ≤15 字符 buffer
- 新 chunk 到达 → 拼接 buffer + chunk → 扫描标签
- 未找到标签 → 安全刷出 buffer（保留尾部可能是标签前缀的部分）
- 找到标签 → 切换状态、输出标签前内容、清空 buffer

## Decision (ADR-lite)

**Context**: 流式 ReAct 的核心挑战是"标签跨 chunk"——文本格式解析需要完整看到标签才能切换状态
**Decision**: 方案 A — 逐字流出 + 小 buffer 回溯（≤15 字符），体感最接近真实 streaming
**Consequences**: 实现稍复杂，但学习价值最高；延迟极低（最多缓存几字符时间）

## Out of Scope

- 状态机提取为可复用模块（留给后续项目需要时）
- Function Calling 模式（已在 05 覆盖）
- Side-by-side 并排展示
- 并行工具调用（ReAct 天然串行）

## Technical Notes

- 03 的正则解析：`RE_THOUGHT`, `RE_ACTION`, `RE_ACTION_INPUT`, `RE_FINAL_ANSWER`
- 03 的跳步检测：`_UNFINISHED_PLAN_PATTERNS` 关键词列表
- 05 的 StreamCollector 不直接复用（05 是 Function Calling delta，06 是文本流）
- 共享 venv：`projects/01-simple-agent/.venv/`
- 模型 env：`OPENAI_MODEL` or `MODEL_NAME`
