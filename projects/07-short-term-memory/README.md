# 07-short-term-memory：短期记忆 Agent

> 通过 4 种记忆策略的并排对比，直观展示 context 管理对 Agent 记忆能力的影响。

---

## 架构概览

```
07-short-term-memory/
├── knowledge_base.py    # 星际学院虚构知识库（22 个实体，6 层关系链）
├── tools.py             # search / lookup / calculate / compare 工具层
├── memory_manager.py    # MemoryManager 抽象基类 + 4 种策略实现
├── agent.py             # MemoryAgent：注入 MemoryManager，ask() 接口
├── display.py           # ANSI 着色 + 并排展示
└── main.py              # 入口：--compare / --demo / --strategy / 交互模式
```

### 模块依赖图

```
main.py
  ├── agent.py (MemoryAgent)
  │     ├── memory_manager.py (MemoryManager + 4 策略)
  │     │     └── tiktoken (token 计数)
  │     └── tools.py (工具执行)
  │           └── knowledge_base.py (星际学院知识库)
  └── display.py (ANSI 展示)
```

### 核心抽象：MemoryManager

```
MemoryManager (ABC)
│   get_messages() → list[dict]   ← 各策略差异的核心
│   add_user() / add_assistant()
│   token_count() / messages_count()
│
├── BaselineMemory        无限增长，不截断
├── SlidingWindowMemory   保留最近 N 轮（按条数截断）
├── TokenLimitMemory      精确 Token 预算（按 token 数截断）
└── SummaryMemory         LLM 摘要压缩（信息保留最完整）
```

---

## 记忆策略对比

| 策略 | 实现方式 | token 增长 | 记忆保留 | 适用场景 |
|------|---------|-----------|---------|---------|
| **baseline** | messages 无限增长 | 线性增长 | 完整（但会溢出） | 短对话 / 调试基准 |
| **sliding** | 保留最近 N 轮 | 恒定（~N 轮 token） | 仅最近 N 轮 | 仅需近期上下文的场景 |
| **token** | Token 预算截断 | 不超过上限 | 最近的对话 | 精确控制 context 窗口 |
| **summary** | LLM 摘要压缩 | 缓慢增长 | 语义摘要（最完整） | 长对话 / 需要早期信息 |

### 策略行为对比（8 轮追问后）

```
[baseline] messages: 25 | tokens: ~4500   → 信息完整，接近溢出
[sliding ] messages: 13 | tokens: ~2100   → 轮6+ 丢失轮1信息，开始答错
[token   ] messages: 14 | tokens: ~2800   → 精确控制，丢失最早期信息
[summary ] messages:  7 | tokens: ~1500   → 摘要保留关键事实，始终能答对
```

---

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 2. 安装依赖

```bash
# 共用 01-simple-agent 的 venv
cd projects/07-short-term-memory
uv pip install --python ../01-simple-agent/.venv/bin/python3 tiktoken
```

### 3. 运行

```bash
# 使用共用 venv
VENV=../01-simple-agent/.venv/bin/python3

# 核心体验：8 轮对比，看 4 种策略的记忆差异
$VENV main.py --compare

# 快速演示：5 轮精简序列
$VENV main.py --demo

# 单策略交互（可选 baseline/sliding/token/summary）
$VENV main.py --strategy sliding
$VENV main.py --strategy summary

# 默认：summary 策略交互模式
$VENV main.py
```

### 4. 交互模式命令

```
你的问题> 林晨是哪个院系的？
你的问题> 林晨的导师是谁？
你的问题> reset          # 清空记忆，重新开始
你的问题> exit           # 退出
```

---

## 星际学院知识库

### 关系链（设计用于触发记忆压力）

```
林晨（学员）
  └─ 导师: 苏明哲
        └─ 院系: 量子院
              └─ 院长: 方若冰
                    └─ 合作机构: 量子动力研究所
                                └─ 负责人: 黎远征
```

### 完整实体列表

**院系（6 个）**：量子院、生命院、机械院、数据院、能源院、外交院

**学员（4 个）**：林晨（量子院）、白羽（生命院）、顾铭（机械院）、夏晴（能源院）

**导师（4 个）**：苏明哲、江海涛、沈钢、罗燕

**院长（4 个）**：方若冰、陆思远、周铁柱、柳星辰

**合作机构（3 个）**：星际探索局（局长赵宇航）、量子动力研究所（所长黎远征）、生命科学联盟（主席韩冰）

---

## compare 模式追问序列

| 轮次 | 问题 | 测试重点 |
|------|------|---------|
| 1 | 林晨是哪个院系的学员？ | 建立基础（林晨→量子院） |
| 2 | 林晨的导师是谁？ | 建立基础（→苏明哲） |
| 3 | 林晨的导师在哪个院系任职？ | 引用轮2 |
| 4 | 那个院系的院长是谁？ | 隐式引用轮3（→方若冰） |
| 5 | 林晨的专长是什么？ | 回头引用轮1 |
| 6 | 那位院长的院系合作机构是哪个？ | 引用轮4，**滑动窗口开始丢失轮1** |
| 7 | 那个合作机构的负责人是谁？ | 引用轮6（→黎远征） |
| 8 | 林晨 2026 年入学多少年了？ | 引用轮1入学年份 + calculate |

---

## 展示效果示例

```
──────────────────────────────────────────────────────────────
第 6 轮：那位院长的院系合作机构是哪个？
──────────────────────────────────────────────────────────────
[baseline] 量子院的合作机构是量子动力研究所。
[sliding ] 对不起，我不记得之前提到的院长是谁。（已丢失轮1-3信息）
[token   ] 量子院的合作机构是量子动力研究所。
[summary ] 方若冰院长所在的量子院，合作机构是量子动力研究所。

📊 context 指标：
  [baseline] messages:  15 | tokens: ~ 2400 | 本轮: ✓ 答对
  [sliding ] messages:  13 | tokens: ~ 2100 | 本轮: ✗ 答错
  [token   ] messages:  14 | tokens: ~ 2800 | 本轮: ✓ 答对
  [summary ] messages:   7 | tokens: ~ 1500 | 本轮: ✓ 答对
```

---

## 技术说明

### Token 计数

使用 `tiktoken` 库（`cl100k_base` 编码，兼容 gpt-4o-mini / gpt-4o）：

```python
tokens = len(encoding.encode(content)) + 4  # +4 = 每条消息 overhead
```

### SummaryMemory 压缩触发条件

```
当前 token 数 > TOKEN_LIMIT × SUMMARY_THRESHOLD_RATIO (默认 0.7)
→ 取最旧 50% 历史 → 调 LLM 生成摘要（max_tokens=200）
→ 摘要注入 system prompt 末尾，旧历史删除
```

### context_length_exceeded 处理

Baseline 策略超出上限时，`MemoryAgent.ask()` 捕获 `BadRequestError`，
检查 `error.code == "context_length_exceeded"`，返回提示字符串而非抛出异常，
compare 模式继续运行其他策略。
