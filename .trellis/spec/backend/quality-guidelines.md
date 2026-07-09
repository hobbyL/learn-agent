# Quality Guidelines

> Code quality standards for this AI Agent learning project.

---

## Overview

这是学习项目，质量标准侧重于：
- **可读性**：详尽中文注释，解释"为什么"而非"做什么"
- **可验证性**：虚构知识库 + 标准答案，确保答案路径可达
- **可运行性**：语法检查 + import 链验证通过即可上手

---

## Required Patterns

### 1. 虚构知识库：字段名一致性

知识库字段名必须在定义时统一，**不要在 test_questions.py 或 Agent prompt 里臆造字段名**。

```python
# ✅ 正确：先确认字段名再写测试
from knowledge_base import KNOWLEDGE_BASE
print(KNOWLEDGE_BASE['珊瑚城'].keys())
# → ['类型', '所属', '人口', '深度', '特色', ...]

# ✅ 正确：用实际字段名
lookup_entity('珊瑚城', '所属')   # → '珊瑚联邦'

# ❌ 错误：想当然用"所属国度"
lookup_entity('珊瑚城', '所属国度')  # → None（字段不存在）
```

**验证方式**：每个 test_questions.py 里的 ground truth 答案，都要通过 `lookup_entity()` 实际调用验证路径可达。

### 2. Ground Truth 答案路径验证（必做）

新增测试问题后，必须跑验证脚本确认每条答案路径实际可达：

```python
from knowledge_base import lookup_entity

# 验证 Q: "深渊王国国王的导师住在哪里？"
king = lookup_entity('深渊王国', '国王')      # → '奥西里斯'
mentor = lookup_entity(king, '导师')          # → 'xxx法师'
residence = lookup_entity(mentor, '居住地')   # → '暗流洞穴'
assert residence == '暗流洞穴', f"路径断了: {residence}"
```

### 3. 彩色可视化输出

每个项目的 verbose 输出必须用 ANSI 颜色区分层次，和 03 保持风格一致：

```python
CYAN  = '\033[96m'   # Thought / 推理
YELLOW = '\033[93m'  # Action  / 工具调用
GREEN = '\033[92m'   # Observation / 工具结果
MAGENTA = '\033[95m' # Reflection / 反思
RED   = '\033[91m'   # Error / 拒绝
RESET = '\033[0m'
```

### 4. 语法检查（提交前）

```bash
cd projects/04-agent-reflection
python -c "
import py_compile
for f in ['knowledge_base.py','tools.py','react_loop.py','evaluator.py',
          'reflector.py','reflexion_agent.py','test_questions.py','main.py']:
    py_compile.compile(f, doraise=True)
    print(f'OK: {f}')
"
```

---

## Forbidden Patterns

### 跨项目 import

```python
# ❌ 绝对禁止
from projects.react_agent.react_agent import ReactAgent

# ✅ 各项目内部重写，或做有意简化的轻量版
```

### 在 Agent Prompt 里猜字段名

```python
# ❌ prompt 里写"查询'所属国度'字段" → LLM 会调 lookup('珊瑚城', '所属国度') → None
# ✅ prompt 里的工具描述只说"查询某个属性"，由 Agent 自己 search 后 lookup 实际字段名
```

---

## Testing Requirements

对于学习项目，测试 = 运行可达性验证：

1. **语法通过**：`py_compile` 对所有 .py 文件通过
2. **Import 通过**：在 venv 里 `python -c "from module import ..."` 无报错
3. **答案路径可达**：每个 TEST_QUESTIONS 的 ground_truth 通过 `lookup_entity()` 链式调用可达
4. **运行不崩溃**：`python main.py --demo` 正常输出（不要求答案100%正确，但不能崩溃）

---

## Code Review Checklist

- [ ] 新建知识库实体后，字段名是否和 test_questions.py / prompt 里的字段名一致？
- [ ] 新增测试问题后，是否跑了 lookup_entity() 验证答案路径？
- [ ] 彩色输出是否有对应的 `if self._verbose:` 开关？
- [ ] .env.example 是否列出了所有新增环境变量？
- [ ] README 的架构图是否和实际文件结构一致？
