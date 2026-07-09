# 07-short-term-memory：短期记忆 Agent

## Goal

实现一个支持**短期记忆管理**的多轮对话 Agent，通过 4 种记忆策略（Baseline / 滑动窗口 / Token 截断 / LLM 摘要压缩）的并排对比，
直观展示 context 管理对 Agent 记忆能力的影响。

核心学习目标：
- 理解 `messages` 列表增长带来的 context 窗口压力
- 掌握 3 种工程化的 context 管理策略及其权衡
- 体验 LLM 摘要压缩在信息保留上的优势
- 预留 `MemoryManager` 抽象接口，为 08-long-term-memory 铺垫

---

## Requirements

### 知识库
- 新建虚构世界「星际学院」，15~20 个实体，刻意设计 5~6 层嵌套关系链
  - 示例链：学员 A → 导师 B → 院系 C → 院长 D → 合作机构 E → 负责人 F
  - 目的：可设计跨轮依赖问题序列，触发记忆压力

### 记忆策略（4 种）

| 策略 | 实现逻辑 |
|------|---------|
| `baseline` | messages 无限增长，超出时捕获 `context_length_exceeded` 并提示 |
| `sliding` | 保留 system prompt + 最近 N 轮（默认 N=6），硬截断旧消息 |
| `token` | tiktoken 计数，超出阈值时从最旧消息开始删，直到 token 数达标 |
| `summary` | 超出阈值时，调 LLM 将旧对话压缩为摘要（max_tokens=200），注入 system prompt 尾部 |

### 架构模块

```
memory_manager.py     # MemoryManager 抽象基类 + 4 种策略实现
agent.py              # MemoryAgent：注入 MemoryManager，单次 ask() 接口
knowledge_base.py     # 星际学院虚构知识库
tools.py              # search / lookup / calculate / compare（同前序项目）
display.py            # 并排展示：4策略回答 + token数 + messages数
main.py               # 入口：--compare / --demo / --strategy <name> / 交互模式
```

### 运行模式

1. **`--compare` 模式（核心）**：预设 8~10 轮追问序列，4 种策略并行运行（顺序 API 调用，并排展示），每轮打印：
   - 各策略的回答内容
   - 当前 messages 数 / token 数
   - 是否正确引用了早轮信息（程序判断关键词）

2. **`--demo` 模式**：同 compare，但使用精简的 5 轮序列，快速演示

3. **`--strategy <name>` 交互模式**：单策略交互，支持 `reset` 命令

### 追问序列设计原则
- 第 1~3 轮：建立基础信息（问学员、问导师）
- 第 4~6 轮：引用早轮信息（问"之前提到的那个导师的院系"）
- 第 7~10 轮：深层追问（问院长、合作机构），此时滑动窗口已丢失第1轮信息

### 实时 context 指标
每轮结束后展示（全策略）：
```
[sliding]  messages: 8 | tokens: ~1240 | 本轮: ✓ 答对
[token]    messages: 12 | tokens: ~1800 | 本轮: ✓ 答对
[summary]  messages: 6  | tokens: ~950  | 本轮: ✓ 答对
[baseline] messages: 20 | tokens: ~3200 | 本轮: ✓ 答对
```

### 错误处理
- Baseline 超出 context 窗口时：捕获 OpenAI `context_length_exceeded` 错误，打印 `⚠️ Baseline: context 溢出，本轮跳过` 并继续其他策略

---

## Acceptance Criteria

- [ ] 4 种记忆策略均能独立运行（单策略交互模式验证）
- [ ] `--compare` 模式：同一追问序列，4 策略并排展示，≥8 轮
- [ ] 第 6+ 轮时，sliding 策略因丢失早轮信息出现答错，summary 策略仍答对
- [ ] 每轮打印 messages 数 + token 数（tiktoken 计数）
- [ ] Baseline 超长时优雅降级（不崩溃）
- [ ] `MemoryManager` 是抽象基类，策略通过子类实现
- [ ] `.env` + `.env.example` 配置 `OPENAI_API_KEY` / `MODEL_NAME` / `MEMORY_STRATEGY`

---

## Definition of Done

- 代码注释密度与 05/06 一致（关键逻辑有中文注释）
- README.md：架构图 + 快速开始 + 策略对比表
- notes.md：踩坑记录 + 学习要点
- 通过真机验证（至少运行一次 `--compare` 完整序列）

---

## Technical Approach

### MemoryManager 抽象基类

```python
from abc import ABC, abstractmethod

class MemoryManager(ABC):
    def __init__(self, system_prompt: str):
        self._system_prompt = system_prompt
        self._history: list[dict] = []  # 不含 system prompt

    @abstractmethod
    def get_messages(self) -> list[dict]:
        """返回本次 API 调用使用的完整 messages 列表"""
        ...

    def add_user(self, content: str): ...
    def add_assistant(self, content: str): ...
    def reset(self): ...
    def token_count(self) -> int: ...  # tiktoken 计数
```

### Token 计数
- 使用 `tiktoken` 库（`cl100k_base` encoding，兼容 gpt-4o-mini / gpt-4o）
- 每条 message 的 token 数 = `len(encoding.encode(content)) + 4`（overhead）

### LLM 摘要触发阈值
- 默认：token 数超过 `MAX_TOKENS * 0.7` 时触发摘要
- 摘要 max_tokens=200，注入到 system prompt 末尾：
  ```
  [对话摘要] 之前的对话要点：<摘要内容>
  ```

### 知识库：星际学院
- 6 个院系（量子院、生命院、机械院、数据院、能源院、外交院）
- 12 个人物（学员 4 + 导师 4 + 院长 4）
- 3 个合作机构
- 关系链深度：学员→导师→院系→院长→合作机构→机构负责人（6 层）

---

## Decision (ADR-lite)

**Context**：短期记忆有多种工程实现，需要在学习价值和实现复杂度间平衡

**Decision**：
- 实现 4 种策略（全部）
- `--compare` 用并排模式（方案 C），每轮 4 策略顺序调 API
- 新建「星际学院」知识库（专为多层追问设计）
- `MemoryManager` 抽象基类（为 08 预留接口）

**Consequences**：
- `--compare` 单次运行耗时 = 4x 单策略（可接受，学习场景不追求速度）
- tiktoken 是额外依赖，需加入 requirements.txt
- 摘要策略增加一次 LLM 调用（触发压缩时），成本略高

---

## Out of Scope

- 持久化存储（08-long-term-memory 专题）
- 向量检索 / 语义相似度检索（08 专题）
- 多用户 session 隔离
- 异步并发 API 调用（顺序调用即可）
- 摘要质量评估（定性观察即可）

---

## Technical Notes

- 共用 venv：`projects/01-simple-agent/.venv/`
- 新增依赖：`tiktoken>=0.7.0`
- 环境变量：`OPENAI_API_KEY` / `MODEL_NAME` or `OPENAI_MODEL` / `MEMORY_STRATEGY`（默认 summary）
- 参考实现：`projects/05-streaming-agent/`（知识库结构）、`projects/03-react-agent/`（工具设计）
- `context_length_exceeded` 错误码：OpenAI error type `invalid_request_error`，code `context_length_exceeded`
