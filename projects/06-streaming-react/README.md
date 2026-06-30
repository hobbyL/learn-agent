# 06-streaming-react —— 流式 ReAct Agent

## 项目目标

学习在 **streaming 模式下实时解析 ReAct 文本格式**：
- LLM 逐字输出 `Thought:` / `Action:` / `Final Answer:` 时，如何边流边识别 section 边界
- 通过状态机（buffer 回溯策略）处理"标签跨 chunk"问题
- 实时着色展示推理链，让 streaming 下的 ReAct 推理过程可视化

**核心学习目标**：
- 理解流式 ReAct 与非流式 ReAct 的核心差异
- 掌握小 buffer 回溯策略处理标签跨 chunk
- 体验流式推理链展示 vs 等待完整响应的体感差异

---

## 与 03 / 05 的对比

| | 03-react-agent | 05-streaming-agent | **06-streaming-react** |
|--|---------------|-------------------|----------------------|
| 输出格式 | 纯文本 ReAct | Function Calling | 纯文本 ReAct |
| API 模式 | stream=False | stream=True | **stream=True** |
| 解析方式 | 正则一次性解析 | delta 拼接 JSON | **状态机增量解析** |
| 推理可见 | 完整链（事后） | 黑盒 | **实时逐字展示** |
| 工具调用 | 文本解析 Action | Function Calling | **文本解析 Action** |

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                     main.py（入口）                            │
│  --demo / --compare / 交互式                                  │
└───────────────┬──────────────────────┬────────────────────────┘
                │                      │
                ▼                      ▼
┌──────────────────────────┐  ┌─────────────────────────────────┐
│  streaming_react_agent   │  │  non_streaming_react_agent      │
│                          │  │  （--compare 对照组）             │
│  stream=True             │  │  stream=False                   │
│  StreamParser 增量解析    │  │  正则一次性解析                   │
│  实时着色展示             │  │  等完整响应后输出                 │
└──────────────┬───────────┘  └─────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│              stream_parser.py（核心状态机）                     │
│                                                              │
│  Section: IDLE → THOUGHT → ACTION → ACTION_INPUT             │
│           → FINAL_ANSWER                                     │
│                                                              │
│  feed(text_fragment) → list[ParseEvent]                      │
│                                                              │
│  Buffer 机制：                                               │
│    维护 ≤20 字符 buffer，处理标签跨 chunk                     │
│    "Tho" + "ught:" → 确认完整 "Thought:" 后切换状态           │
└──────────────┬───────────────────────────────────────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
┌──────────┐ ┌──────────────────────────────────────────────────┐
│display.py│ │  tools.py + knowledge_base.py（太空站联盟）         │
│          │ │                                                  │
│Thought=灰│ │  search / lookup / calculate / compare           │
│Action=黄 │ │  12 个实体：4站 + 5人 + 3设备/飞船               │
│Observ=绿 │ │  + get_tool_descriptions()（ReAct 文本格式）      │
│Final=亮白│ │                                                  │
└──────────┘ └──────────────────────────────────────────────────┘
```

---

## 状态机流转

```
                    "Thought:"
         ┌──────────────────────────────────────┐
         │                                      │
         ▼                                      │
    ┌─────────┐                                 │
    │  IDLE   │                                 │
    └─────────┘                                 │
         │ "Thought:"                           │
         ▼                                      │
    ┌──────────┐   "Action:"    ┌──────────┐   │
    │ THOUGHT  │───────────────▶│  ACTION  │   │
    └──────────┘                └────┬─────┘   │
         │                           │          │
         │ "Final Answer:"            │ "Action Input:"
         │                           ▼          │
         │                   ┌──────────────┐  │
         │                   │ ACTION_INPUT │──┘
         │                   │ → ActionReady│
         │                   │ → Observation│
         │                   └──────────────┘
         ▼
    ┌──────────────┐
    │ FINAL_ANSWER │ → FinalAnswerReady → 循环结束
    └──────────────┘
```

---

## 快速开始

### 1. 环境准备

```bash
cd projects/06-streaming-react
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 2. 运行

```bash
# 交互模式（默认）— 流式 ReAct，实时推理链展示
python main.py

# 预设问题演示
python main.py --demo

# 非流式 vs 流式 ReAct 对比
python main.py --compare
python main.py --compare "深红站站长的导师驻扎在哪？"
```

---

## 展示效果

流式 ReAct 推理链（实时着色）：

```
── 第 1 步 ──

🧠 Thought: 我需要查询深红站的站长信息。      ← 灰色，实时流出
⚡ Action: lookup
📥 Action Input: {"entity": "深红站", "field": "站长"}
👁 Observation [lookup]: 深红站 → 站长: 赵铁翼  ← 绿色

── 第 2 步 ──

🧠 Thought: 已知站长是赵铁翼，查询其导师。
⚡ Action: lookup
📥 Action Input: {"entity": "赵铁翼", "field": "导师"}
👁 Observation [lookup]: 赵铁翼 → 导师: 周明远

── 第 3 步 ──

🧠 Thought: 导师是周明远，查询其当前驻站。
⚡ Action: lookup
📥 Action Input: {"entity": "周明远", "field": "驻站"}
👁 Observation [lookup]: 周明远 → 驻站: 极光站

── 第 4 步 ──

🧠 Thought: 已有所有信息。
✅ Final Answer: 深红站站长赵铁翼的导师周明远现驻扎在极光站。  ← 亮白色
```

---

## 文件说明

| 文件 | 职责 |
|------|------|
| `main.py` | 入口：--demo / --compare / 交互模式 |
| `stream_parser.py` | 核心状态机：增量解析 ReAct 文本，buffer 处理跨 chunk 标签 |
| `streaming_react_agent.py` | 流式 ReAct Agent：stream=True + StreamParser |
| `non_streaming_react_agent.py` | 非流式对照组：stream=False + 正则解析 |
| `display.py` | ANSI 着色展示：Thought/Action/Observation/Final Answer |
| `tools.py` | 4 个工具 + get_tool_descriptions()（ReAct 文本格式） |
| `knowledge_base.py` | 太空站联盟虚构知识库（复用自 05） |
| `notes.md` | 学习笔记 + 踩坑记录 |

---

## 知识库：太空站联盟（复用自 05）

| 类别 | 实体 | 关键属性 |
|------|------|---------|
| 太空站 | 极光站、天琴站、深红站、冰环站 | 位置、人口、站长、建站年份 |
| 人物 | 陈星河、林夜霜、赵铁翼、苏晴岚、周明远 | 职位、驻站、导师、年龄 |
| 飞船/设备 | 天琴号、赤焰号、极光之眼 | 所属站、操作员、用途 |

---

**创建时间**：2026-06-30
**完成时间**：2026-06-30
**状态**：✅ 已完成
