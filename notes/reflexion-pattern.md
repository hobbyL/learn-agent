# Reflexion 模式详解

Reflexion（Language Agents with Verbal Reinforcement Learning）是在 ReAct 基础上引入"试错→反思→重试"机制的 Agent 设计模式。

---

## 核心思想

**让 Agent 像人一样从错误中学习**：不是简单重试，而是先分析"哪里错了、为什么错、下次怎么改"，再带着这份经验重试。

```
Trial 1 → 评估 → ❌ 失败 → 反思摘要
Trial 2 → 评估 → ❌ 失败 → 反思摘要  ← 带着 Trial 1 的教训
Trial 3 → 评估 → ✅ 成功
```

---

## Reflexion 四组件

### 1. Actor（内层执行器）

执行实际任务的 ReAct 循环。Reflexion 对 Actor 没有严格要求，
可以是任何能完成任务并返回结果的执行器。

关键点：**内层 Actor 可以故意简化**（如去掉跳步检测护栏），
让 Agent 更容易犯错，反思机制才有施展空间。

### 2. Evaluator（评估器）

判断 Actor 的输出是否正确，返回评估结果和反馈。

#### 双轨制设计

| 模式 | 实现 | 适用场景 |
|------|------|---------|
| Ground Truth | 程序比对预定义答案 | 有标准答案、自动化测试 |
| LLM Judge | LLM 评估答案质量 | 开放问题、演示场景 |

```python
class GroundTruthEvaluator:
    def evaluate(self, question, answer, ground_truth) -> EvalResult:
        # 关键字匹配：ground_truth 中的关键词是否都出现在 answer 中
        ...

class LLMJudgeEvaluator:
    def evaluate(self, question, answer, reasoning_steps) -> EvalResult:
        # 额外一次 LLM 调用，评估完整性/数据来源/逻辑一致性
        ...
```

### 3. Self-Reflector（反思器）

接收失败的执行结果和评估反馈，由 LLM 生成结构化反思摘要。

**反思 Prompt 的关键要素**：
- 任务目标是什么
- Actor 给出了什么答案
- 评估器认为哪里错了
- 要求 LLM 分析根因并给出具体改进策略

```python
reflection_prompt = f"""
上次尝试：
问题：{question}
答案：{answer}
错误反馈：{eval_feedback}

请分析：
1. 哪一步出错了？
2. 错误的根本原因是什么？
3. 下次尝试时应该如何避免这个错误？

用简洁的中文回答，作为给自己的备忘录。
"""
```

### 4. Memory（记忆缓冲区）

存储历次反思摘要，传递给下一轮 Actor。

**关键设计**：**注入 system prompt 尾部**（论文标准做法）

```python
reflections = []  # 内存缓冲区，不持久化

def build_system_prompt(base_prompt: str, reflections: list[str]) -> str:
    if not reflections:
        return base_prompt
    
    reflection_text = "\n\n".join([
        f"第{i+1}次尝试的教训：{r}"
        for i, r in enumerate(reflections)
    ])
    
    return base_prompt + f"\n\n## 历史尝试教训（请认真参考）\n\n{reflection_text}"
```

---

## 外层 Reflexion 循环

```python
class ReflexionAgent:
    def run(self, question: str, ground_truth: str = None) -> dict:
        reflections = []
        all_trials = []
        
        for trial_num in range(1, self.max_trials + 1):
            # 1. 执行内层 ReAct（带历史反思）
            result = self.actor.run(question, reflections=reflections)
            
            # 2. 评估结果
            eval_result = self.evaluator.evaluate(question, result["answer"], ground_truth)
            
            # 3. 记录本轮结果
            all_trials.append({
                "trial": trial_num,
                "result": result,
                "evaluation": eval_result,
            })
            
            # 4. 成功则提前退出
            if eval_result["is_correct"]:
                break
            
            # 5. 生成反思，加入记忆
            if trial_num < self.max_trials:
                reflection = self.reflector.reflect(question, result, eval_result)
                reflections.append(reflection)
        
        return {
            "final_answer": result["answer"],
            "trials": all_trials,
            "reflections": reflections,
            "success": eval_result["is_correct"],
        }
```

---

## 从实践中学到的教训

> 以下经验来自 04-agent-reflection 项目的实际实现，是对上方理论的实战校验。

### 1. 反思"有没有用"取决于反思质量，而非反思次数

反思摘要必须明确指出**具体的错误步骤**，泛泛而谈没有价值：

```
# ❌ 无效反思：太笼统
"上次我查询了错误的信息，下次要更仔细。"

# ✅ 有效反思：指向具体问题
"上次我在查询珊瑚城的所属国度时，直接用了'珊瑚城'查'所属国度'字段，
但实际字段名是'所属'。下次应先用 search('珊瑚城') 确认实体的完整字段列表，
再用正确字段名 lookup。"
```

### 2. 内层 Actor 故意简化才能触发反思

如果内层 ReAct 护栏太强（跳步检测、格式重试等），Agent 几乎不会犯错，
反思机制就没有施展空间。

**04 的设计决策**：内层 `react_loop.py` 去掉了 03 的跳步检测，
让 Agent 更自然地出错，从而积累真实的反思素材。

### 3. 评估器是 Reflexion 的瓶颈

- **Ground Truth 评估**：适合学习/测试，但需要预定义答案（且字段名必须和知识库一致）
- **LLM-as-Judge**：灵活但不确定，评估器本身可能出错，导致"答对被判错"或"答错被判对"

**推荐**：学习项目用 Ground Truth，真实场景用 LLM Judge，两者都实现供切换。

### 4. Ground Truth 字段名必须和知识库实际字段一致

这是 04 实现中踩的坑：test_questions.py 里写了"所属国度"，但知识库实际字段是"所属"，
导致验证路径断掉。

**预防措施**：每次新增测试问题后，必须跑验证脚本：

```python
# 验证脚本（集成到 test_questions.py 或单独 verify.py）
from knowledge_base import lookup_entity

def verify_answer_path(chain: list[tuple[str, str]], expected):
    """验证 lookup 链式调用路径是否可达"""
    result = None
    for entity, field in chain:
        result = lookup_entity(entity if result is None else result, field)
        assert result is not None, f"路径断了：{entity}.{field} → None"
    assert result == expected, f"答案不匹配：得到 {result!r}，期望 {expected!r}"
```

### 5. Reflexion vs 无脑重试的本质区别

| | 有反思（Reflexion） | 无脑重试 |
|--|-------------------|---------|
| 重试方向 | 有针对性（基于上次错误） | 随机（LLM 温度带来的随机性） |
| 改进机制 | LLM 分析根因 → 修正策略 | 概率性碰运气 |
| Token 消耗 | 多（额外反思 LLM 调用） | 少 |
| 适用场景 | 系统性错误（字段查错、推理链断） | 随机性错误（格式偶发飘移） |

**结论**：Reflexion 不适合处理概率性偶发错误（那用 temperature=0 + 重试即可），
适合处理**系统性错误**——Agent 每次都会犯同一类错，反思才能打断这个循环。

### 6. MAX_TRIALS=3 的经验依据

Reflexion 论文实验表明 2-3 轮反思后改进趋于饱和。超过 3 轮通常意味着：
- 问题超出模型能力（换更强的模型，不是继续反思）
- 评估器判断有问题（误判导致正确答案被否定）
- 反思摘要质量差（反思器生成了无效建议）

配置建议：通过 `.env` 的 `MAX_TRIALS` 控制，默认 3，调试时可降为 1（等于无反思）。

---

## 相关论文

**Reflexion: Language Agents with Verbal Reinforcement Learning**
- 作者：Noah Shinn, Federico Cassano, Edward Berman et al.
- 发表：2023
- 链接：https://arxiv.org/abs/2303.11366

---

## 进阶话题

### Reflexion vs Self-Consistency

- **Self-Consistency**：多次运行取多数答案（投票），处理随机性
- **Reflexion**：单线程迭代改进（有记忆），处理系统性错误

两者可以结合：外层 Reflexion 保证方向正确，内层多次采样保证答案稳定。

### 反思记忆的持久化

04 只做运行时内存（session 内），跨 session 的经验积累属于长期记忆系统（05-memory-system 的范畴）。

---

**最后更新**：2026-06-28
**来源项目**：04-agent-reflection
