# 05-streaming-agent：流式输出 Agent

## Goal

学习 OpenAI Streaming API + tool_calls delta 拼接，通过 raw/final 双视角直观理解 streaming 协议细节。纯 Function Calling 模式，为后续 06-streaming-react 打基础。

## Requirements

* 基础 streaming：`stream=True` 逐 token 实时输出文本
* tool_calls delta 拼接：正确重组分块 `function.name` + `function.arguments`
* 完整 Agent 循环：streaming 模式下多轮工具调用正常工作
* 双视角展示（C2）：先打印 raw delta 时间线（chunk 编号 + 原始内容），再打印合成最终输出
* `--compare` 模式：同一问题分别跑 streaming / non-streaming，展示延迟差异和输出对比
* `--demo` 模式：预设问题演示完整效果
* 轻量知识库"太空站联盟"（~12 实体：太空站/站长/工程师/设备/飞船）
* 4 个工具（search/lookup/calculate/compare）沿用 03/04 模式

## Acceptance Criteria

* [ ] 纯文本流式逐字输出可见
* [ ] tool_calls delta 正确拼接（含并行工具调用场景）
* [ ] streaming Agent 循环完成 3 步以上链式推理
* [ ] raw delta 时间线展示：每个 chunk 编号 + 类型 + 内容
* [ ] `--compare` 展示 streaming vs non-streaming 对比
* [ ] `--demo` 预设问题跑通
* [ ] 网络中断 / 空 chunk 优雅降级
* [ ] notes.md 记录 streaming 协议踩坑

## Definition of Done

* 代码有清晰注释解释 streaming 协议
* notes.md 记录踩坑和学习要点
* README.md 完整（项目目标/架构/快速开始/完成标准/文件说明）
* 真机跑通演示

## Technical Approach

* 纯 Function Calling 模式（不做 ReAct 文本解析，那是 06 的事）
* `StreamCollector` 类负责收集 delta、拼接 tool_calls、记录原始时间线
* `StreamingAgent` 类封装 streaming 版 Agent 循环
* `main.py` 入口支持 `--demo` / `--compare` / 交互式
* 知识库"太空站联盟"约 12 实体，足够触发 2-3 步工具链

## Decision (ADR-lite)

**Context**: 05 需要决定 streaming 可视化方式、Agent 循环模式、知识库策略

**Decisions**:
1. 可视化采用 C2（先 raw delta timeline，再 final output）——实现简洁，学习效果直观
2. Agent 循环采用纯 Function Calling stream（ReAct stream 独立为 06 项目）
3. 知识库新建"太空站联盟"轻量主题（~12 实体），突出 streaming 为主角
4. 阶段 2 扩展为 7 个项目（05 FC stream + 06 ReAct stream），后续顺延

**Consequences**:
- 05 范围精简，聚焦 streaming 协议本身
- 06 有独立空间做"边流边解析"的复杂逻辑
- 阶段 2 总项目 7 个，阶段 3 从 12 开始，总计 17 个项目

## Out of Scope

* 流式 ReAct 文本解析（→ 06-streaming-react）
* WebSocket / SSE 服务端推送
* asyncio 异步版本
* 可复用模块抽取（留给 06 重构时考虑）
* Web UI / 前端界面

## Technical Notes

* openai 2.44.0 已安装于 `projects/01-simple-agent/.venv/`
* streaming response 结构：`chunk.choices[0].delta.content` / `.tool_calls`
* tool_calls delta 的 `index` 字段用于区分并行工具调用
* `chunk.choices[0].finish_reason` 为 `"tool_calls"` 时表示需要执行工具
* 项目文件结构约定参考 01-04
* 知识库复用 03/04 的 search/lookup/calculate/compare 工具模式

## File Structure

```
05-streaming-agent/
├── main.py               # 入口：--demo / --compare / 交互
├── streaming_agent.py    # StreamingAgent 循环
├── stream_collector.py   # delta 收集 + 拼接 + 时间线记录
├── tools.py              # 4 个工具 + schema
├── knowledge_base.py     # 太空站联盟（~12 实体）
├── display.py            # 输出展示（raw timeline / final / compare）
├── notes.md              # 踩坑记录
├── README.md             # 项目文档
├── requirements.txt      # openai, python-dotenv
└── .env.example          # 环境变量
```
