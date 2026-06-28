# 04-agent-reflection 学习笔记

> 实现过程中的关键踩坑记录和设计思考。
> 完整 Reflexion 模式理论与实战总结见：[notes/reflexion-pattern.md](../../notes/reflexion-pattern.md)

---

## 踩坑记录

### 1. 双评估器参数签名不兼容

**现象**：`run_compare` 在 `EVALUATOR_MODE=llm_judge` 时崩溃，`TypeError: evaluate() got unexpected keyword argument`。

**根因**：两种评估器的第三个参数名不同：

```python
# GroundTruthEvaluator
def evaluate(self, question, agent_answer, ground_truth): ...

# LLMJudgeEvaluator
def evaluate(self, question, agent_answer, steps): ...
```

`run_compare` 原来统一用 `ground_truth=` 关键字传参，LLMJudgeEvaluator 不认识该参数名。

**修复**：用 `isinstance` 判断评估器类型，路由到正确的参数名：

```python
from evaluator import GroundTruthEvaluator, LLMJudgeEvaluator

if isinstance(evaluator, LLMJudgeEvaluator):
    result = evaluator.evaluate(
        question=q["question"],
        agent_answer=answer,
        steps=steps,
    )
else:
    result = evaluator.evaluate(
        question=q["question"],
        agent_answer=answer,
        ground_truth=q["ground_truth"],
    )
```

**教训**：双轨接口的公共调用点，必须用类型判断路由，不能假设参数名一致。

---

### 2. 文档/Prompt 中的实体名与知识库不一致

**现象**：README 和 `react_loop.py` system prompt 示例里写的是 `珊瑚礁城`，但知识库实体实际名为 `珊瑚礁堡`。Agent 在推理时参照 system prompt 示例构造查询，导致 `lookup("珊瑚礁城", ...)` 命中不到实体。

**根因**：在实现知识库时将城市命名为"珊瑚礁**堡**"，但后续写 README 和 system prompt 时笔误写成"珊瑚礁**城**"，未与知识库对照。

**修复**：全局搜索 `珊瑚礁城`，统一改为 `珊瑚礁堡`（知识库实际名）。

**教训**：Prompt / 文档里的实体名必须和知识库定义完全一致，任何一处笔误都会让 Agent 的示例查询失败，误导 LLM 的推理方向。

---

### 3. MAX_STEPS 结构性约束无法被反思突破

**现象**：q07（多跳链式查询，需要 ≥12 次工具调用）在 `MAX_STEPS=10` 的配置下，无论反思几轮都无法完成，每轮都因步数耗尽终止。反思摘要能正确诊断"上次查到了 X，但步数用完了"，但下一轮仍然在第 10 步截断。

**根因**：Reflexion 的反思机制能修正**策略错误**（查错实体、用错字段名、推理方向偏差），但无法改变**步数上限**这个硬约束——这是配置层面的结构性限制，不是 Agent 的推理问题。

**修复**：`.env` 中将 `MAX_STEPS` 提高到 `15`，q07 在 Trial 1 即可完成。

**教训**：
- Reflexion 适合处理**系统性策略错误**（每次都犯同一类错），不适合处理**资源约束**（步数/token 不足）。
- 设计测试题时，要先验证答案路径需要的最少工具调用次数，再设置 MAX_STEPS（建议留 20%-30% 余量）。

---

## 相关笔记

完整的 Reflexion 模式理论、四组件设计、实战对照见：
→ [notes/reflexion-pattern.md](../../notes/reflexion-pattern.md)

---

**最后更新**：2026-06-28
**来源项目**：04-agent-reflection
