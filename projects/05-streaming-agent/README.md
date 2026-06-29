# 05-streaming-agent —— 流式输出 Agent

## 项目目标

学习 OpenAI Streaming API 的完整工作原理：从基础的逐 token 文本流，
到 streaming 模式下 tool_calls 的分块 delta 拼接，再到双视角展示（raw timeline + final output）
让 streaming 协议细节一目了然。

**核心学习目标**：
- 理解 `stream=True` 如何改变 API 调用模式
- 掌握 tool_calls delta 拼接的完整流程（按 index 分组 + arguments 字符串累积）
- 通过 raw delta timeline 直观观察 streaming 协议底层行为
- 对比 streaming vs non-streaming 的体感差异（首字节延迟 vs 总耗时）

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                     main.py（入口）                            │
│  --demo / --compare / 交互式                                  │
└──────────────┬──────────────────────────┬────────────────────┘
               │                          │
               ▼                          ▼
┌───────────────────────────┐  ┌──────────────────────────────┐
│   streaming_agent.py      │  │   non_streaming_agent.py     │
│                           │  │   （--compare 对照组）          │
│  stream=True              │  │   stream=False               │
│  逐 chunk 迭代             │  │   等待完整响应                 │
│  StreamCollector 拼接      │  │   直接解析                    │
└──────────────┬────────────┘  └──────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│              stream_collector.py（核心）                        │
│                                                              │
│  StreamCollector:                                            │
│    feed(chunk) → 逐 chunk 收集                                │
│    build() → StreamResult                                    │
│                                                              │
│  ToolCallAccumulator:                                        │
│    apply_delta() → 拼接单个 tool_call                         │
│                                                              │
│  TimelineEntry:                                              │
│    记录每个 chunk 的时间戳、类型、原始内容                       │
└──────────────┬───────────────────────────────────────────────┘
               │
       ┌───────┼───────┐
       ▼       ▼       ▼
┌──────────┐ ┌─────────────────────────────────────────────────┐
│display.py│ │  tools.py + knowledge_base.py（太空站联盟）        │
│          │ │                                                  │
│Raw时间线  │ │  search / lookup / calculate / compare           │
│Final输出  │ │  12 个实体：4站 + 5人 + 3设备/飞船               │
│Compare   │ │                                                  │
└──────────┘ └─────────────────────────────────────────────────┘
```

---

## Streaming 工作流程

```
用户: "深红站站长的导师驻扎在哪？"
        │
        ▼
┌─ StreamingAgent.run() ───────────────────────────────────────┐
│                                                              │
│  第 1 轮 streaming API 调用:                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ stream = client.chat.completions.create(stream=True)   │  │
│  │                                                        │  │
│  │ for chunk in stream:                                   │  │
│  │   collector.feed(chunk)                                │  │
│  │   → chunk: tool_calls delta (name="lookup")            │  │
│  │   → chunk: tool_calls delta (args+='{"en')             │  │
│  │   → chunk: tool_calls delta (args+='tity":')           │  │
│  │   → ...                                                │  │
│  │   → chunk: finish_reason="tool_calls"                  │  │
│  │                                                        │  │
│  │ result = collector.build()                             │  │
│  │ → tool_calls: [{name:"lookup", args:{entity:"深红站",   │  │
│  │                                      field:"站长"}}]   │  │
│  └────────────────────────────────────────────────────────┘  │
│                      │                                       │
│                      ▼                                       │
│  execute_tool("lookup", {entity:"深红站", field:"站长"})       │
│  → "深红站 → 站长: 赵铁翼"                                    │
│                      │                                       │
│  第 2 轮 streaming API 调用:                                  │
│  → tool_calls: [{name:"lookup", args:{entity:"赵铁翼",       │
│                                       field:"导师"}}]        │
│  execute_tool → "赵铁翼 → 导师: 周明远"                        │
│                      │                                       │
│  第 3 轮 streaming API 调用:                                  │
│  → tool_calls: [{name:"lookup", args:{entity:"周明远",       │
│                                       field:"驻站"}}]        │
│  execute_tool → "周明远 → 驻站: 极光站"                        │
│                      │                                       │
│  第 4 轮 streaming API 调用:                                  │
│  → content 逐字流出: "深红站站长赵铁翼的导师是周明远，          │
│                       他目前驻扎在极光站。"                    │
│  → finish_reason="stop"                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
展示：raw delta timeline → final output
```

---

## 快速开始

### 1. 环境准备

```bash
cd projects/05-streaming-agent
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 2. 运行

```bash
# 交互模式（默认）
python main.py

# 预设问题演示
python main.py --demo

# Streaming vs Non-Streaming 对比
python main.py --compare
python main.py --compare "极光站和冰环站人口相差多少？"
```

### 3. 交互命令

| 命令 | 说明 |
|------|------|
| 直接输入问题 | streaming 模式回答 + raw timeline |
| `reset` | 重置对话历史 |
| `exit` | 退出 |

---

## 双视角展示（C2 模式）

每次问答后，展示两个视角：

**视角 1：Raw Delta Timeline**
```
[  1]    12ms 📝 content          '深'
[  2]    15ms 📝 content          '红'
[  3]    18ms 📝 content          '站'
...
[  7]    45ms 🔧 tool_call_delta  [0] name=lookup
[  8]    48ms 🔧 tool_call_delta  [0] args+='{"entity":'
[  9]    51ms 🔧 tool_call_delta  [0] args+='"深红站",'
...
[ 15]    89ms 🏁 finish           finish_reason=tool_calls
```

**视角 2：合成最终输出**
```
✅ 合成最终输出
深红站站长赵铁翼的导师是周明远，他目前驻扎在极光站。
```

---

## 知识库：太空站联盟

12 个实体的轻量虚构世界：

| 类别 | 实体 | 关键属性 |
|------|------|---------|
| 太空站 | 极光站、天琴站、深红站、冰环站 | 位置、人口、站长、建站年份 |
| 人物 | 陈星河、林夜霜、赵铁翼、苏晴岚、周明远 | 职位、驻站、导师、年龄 |
| 飞船/设备 | 天琴号、赤焰号、极光之眼 | 所属站、操作员、用途 |

**陷阱设计**：「天琴站」vs「天琴号」（太空站 vs 飞船，名字相似易混淆）

---

## 文件说明

| 文件 | 职责 |
|------|------|
| `main.py` | 入口：--demo / --compare / 交互模式 |
| `streaming_agent.py` | StreamingAgent：streaming 版 Agent 循环 |
| `non_streaming_agent.py` | NonStreamingAgent：非流式对照组（--compare 用） |
| `stream_collector.py` | StreamCollector：delta 收集 + tool_calls 拼接 + timeline 记录 |
| `display.py` | 展示模块：raw timeline / final output / compare 对比 |
| `tools.py` | 4 个工具（search/lookup/calculate/compare）+ Schema |
| `knowledge_base.py` | 太空站联盟虚构世界知识库（12 实体） |
| `notes.md` | 学习笔记 + 踩坑记录 |

---

## 与 01 的关系

| | 01-simple-agent | 05-streaming-agent |
|--|----------------|-------------------|
| API 模式 | `stream=False` | `stream=True` |
| 响应获取 | 等待完整响应 | 逐 chunk 迭代 |
| tool_calls | 一次性完整返回 | delta 分块拼接 |
| 用户体验 | 等→一次性输出 | 实时逐字显示 |
| 调试视角 | 只看最终结果 | raw timeline 可审查每个 delta |

---

**创建时间**：2026-06-29
**完成时间**：2026-06-29
**状态**：✅ 已完成
