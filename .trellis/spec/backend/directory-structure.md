# Directory Structure

> How backend code is organized in this project.

---

## Overview

这是一个 AI Agent **学习项目**，不是传统 web 后端项目。
每个子项目（`projects/01-xxx/`）是独立的学习单元，各自包含所有代码，
不跨项目 import。

---

## Directory Layout

```
learn-agent/
├── projects/
│   ├── 01-simple-agent/      # 独立，含 .venv（后续项目复用此 venv）
│   ├── 02-tool-calling/      # 独立，复用 01 的 .venv
│   ├── 03-react-agent/       # 独立，复用 01 的 .venv
│   └── 04-agent-reflection/  # 独立，复用 01 的 .venv
├── notes/                    # 跨项目提炼的通用知识笔记
├── progress/                 # 学习进度日志
└── resources/                # 参考资料
```

### 每个 projects/NN-xxx/ 内部结构（扁平风格）

```
projects/04-agent-reflection/
├── main.py                 # 入口
├── <core-module>.py        # 核心业务（Agent、评估器等）
├── tools.py                # 工具层
├── knowledge_base.py       # 知识库（虚构数据）
├── test_questions.py       # 测试问题 + 标准答案
├── requirements.txt        # 依赖（通常只列 openai + python-dotenv）
├── .env.example            # 配置模板
├── .env                    # 真实配置（不提交）
├── README.md               # 项目文档
└── notes.md                # 学习笔记
```

---

## Module Organization

### 项目独立原则（Critical）

**每个项目完全自包含**，不跨 `projects/NN-xxx/` 目录 import。

```python
# ❌ 错误：跨项目 import
from projects.react_agent import ReactAgent

# ✅ 正确：各项目内部重写，或只共享 notes/ 里的知识
from react_loop import ReactLoop   # 04 内部自己写的轻量版
```

理由：每个项目的学习重点不同，内层组件可能有意简化（如 04 的 react_loop 故意去掉跳步检测以便触发反思）。

### venv 复用策略

```bash
# 所有项目复用 01 的 venv（依赖一样：openai + python-dotenv）
source ../01-simple-agent/.venv/bin/activate
python main.py
```

---

## Naming Conventions

| 类型 | 命名风格 | 示例 |
|------|---------|------|
| 模块文件 | snake_case | `reflexion_agent.py`, `react_loop.py` |
| 类名 | PascalCase | `ReflexionAgent`, `GroundTruthEvaluator` |
| 函数/变量 | snake_case | `execute_tool`, `get_evaluator` |
| 环境变量 | UPPER_SNAKE | `MAX_TRIALS`, `EVALUATOR_MODE` |
| 知识库 key | 中文实体名 | `"深渊王国"`, `"潮汐三叉戟"` |

---

## Examples

参考项目：
- [`projects/03-react-agent/`](../../../projects/03-react-agent/) — 代码风格标准（注释密度、彩色输出）
- [`projects/04-agent-reflection/`](../../../projects/04-agent-reflection/) — Reflexion 架构标准
