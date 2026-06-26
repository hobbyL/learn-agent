# 项目学习笔记

本文件记录在实现 `01-simple-agent` 过程中的原始学习笔记。

---

## 项目状态

**开始时间**：2026-06-25  
**完成时间**：2026-06-26  
**当前进度**：✅ 已完成

---

## 实现过程

### Day 1 - 2026-06-25
- 完成 tools.py、agent.py、main.py 的实现

### Day 2 - 2026-06-26
- 运行验证全部 6 个测试用例
- 发现并修复 load_dotenv 时序问题
- 发现并修复 get_current_time 工具描述不完善导致的日期推算 bug

---

## 遇到的问题与解决方案

### 问题 1：LOG_LEVEL 在 .env 中设置不生效

**现象**：在 `.env` 里设置 `LOG_LEVEL=DEBUG`，运行后仍然是 INFO 级别。

**根因**：`main.py` 的执行顺序：
1. `from agent import Agent`（模块级）→ 触发 `agent.py` 顶层代码，`_LOG_LEVEL` 被立即赋值
2. `load_dotenv()`（在 `main()` 函数内）→ 太晚了，`.env` 还没加载

**解决方案**：将 `load_dotenv()` 移到 `main.py` 最顶部（所有 import 之前）。

**教训**：Python 模块级代码在 `import` 时立即执行，环境变量的加载必须先于任何读取环境变量的代码。

---

### 问题 2：相对日期（明天/昨天）星期推算错误

**现象**：
- 问"昨天的日期" → LLM 正确调用 `get_current_time`，推算出昨天日期和星期 ✅
- 问"明天的日期" → LLM **没有调工具**，复用历史中的今天日期推算，日期算对了但**星期算错了** ❌
  - 今天星期五，明天应该是星期六，但 LLM 输出了"星期五"

**根因**：
1. LLM 在 messages 历史中已有"今天是 2026-06-26 星期五"的信息
2. 认为不需要重新调工具，直接推算"明天是 2026-06-27"
3. 但 LLM 对星期的 +1 推算出错（精确计数是 LLM 的弱点）

**解决方案**：在 `get_current_time` 的 TOOLS_DEFINITION description 中明确要求：
> 每当需要计算相对日期或星期时，必须重新调用此工具，不能依赖历史中的日期

**教训**：
- **工具的 description 直接影响 LLM 的工具调用决策**，写得越精确，行为越可靠
- **LLM 不擅长精确计数**（星期 +1、天数计算等），应该让工具来算，不要让 LLM 自行推理
- "复用历史信息"是 LLM 的优化行为，但对需要实时/精确数据的场景是 bug

---

### 问题 3：相对日期在多轮对话后失效（date_calculator 不被调用）

**现象**：
- reset 后立即问"前天" → 正确调用 `date_calculator` ✅
- 先问今天/昨天/明天后再问"前天" → LLM 跳过 `date_calculator`，直接从历史推算或答非所问 ❌

**根因**：
- LLM 在对话历史中看到"今天是 2026-06-26"后，认为不需要重新调工具
- 直接从历史中复用日期，跳过 `date_calculator`
- 即使能推算出正确日期，星期也容易出错（LLM 精确计数弱点）

**解决方案**：在 `date_calculator` 的 description 中明确加入：
> 即使对话历史中已出现过今天的日期，计算任何相对日期时也必须重新调用此工具，不能从历史推算。

**教训**：
- 同一个 LLM 偏好（复用历史以减少工具调用）在两个工具上都触发了相同的 bug
- description 必须明确告知"历史有信息也要调工具"，否则 LLM 会做惰性优化
- 这是 `date_calculator` description 的第二次修订（第一次修订修复了 `get_current_time`）

---

## 待提炼到主目录 notes/

- ✅ load_dotenv 时序问题 → 提炼到 `notes/tool-calling.md`
- ✅ 工具 description 影响 LLM 行为 → 提炼到 `notes/tool-calling.md`
- ✅ LLM 不擅长精确计数的结论 → 提炼到 `notes/tool-calling.md`（教训 2）

---

**最后更新**：2026-06-26

