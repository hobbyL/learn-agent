# 项目 01：最简单的 Agent

手写一个最基础的 Agent，理解 Agent 的核心循环。

---

## 📋 项目信息

**难度**：⭐⭐☆☆☆  
**预计时间**：2-3 天  
**前置知识**：
- Python 基础
- 基本的 API 调用

**学习目标**：
- 理解 Agent 的核心循环：感知 → 推理 → 行动
- 学会调用 LLM API
- 实现简单的工具调用

---

## 🎯 项目目标

构建一个能够：
1. 接收用户输入
2. 调用 LLM 进行推理
3. 执行简单工具（如计算器、时间查询）
4. 返回结果给用户

的最简单 Agent。

---

## 🛠️ 技术栈

- **Python 3.10+**
- **LLM API**：OpenAI API（原生 Function Calling）
- **依赖**：
  - `openai>=1.0.0`
  - `python-dotenv>=1.0.0`
  - `requests>=2.31.0`

---

## 📝 实现步骤

### 第 1 步：环境搭建
- [ ] 创建 Python 虚拟环境
- [ ] 安装依赖
- [ ] 配置 API Key（OPENAI_API_KEY、OPENWEATHERMAP_API_KEY）

### 第 2 步：实现基础 Agent 类
- [x] 定义 `Agent` 类
- [x] 实现 `run()` 方法（核心循环）
- [x] 实现 LLM 调用（OpenAI Function Calling）

### 第 3 步：实现工具系统
- [x] 定义工具接口（JSON Schema）
- [x] 实现 5 个工具（计算器、时间、单位换算、文本统计、天气）
- [x] 工具注册和调用（_dispatch_tool）

### 第 4 步：整合和测试
- [x] 集成 Agent 和工具（main.py）
- [ ] 运行并测试 5 个测试用例
- [ ] 记录学习笔记（notes.md）

---

## 📦 项目结构

```
01-simple-agent/
├── README.md          # 本文件（项目说明、进度追踪）
├── main.py            # 命令行交互入口（启动这个文件）
├── agent.py           # Agent 核心循环（感知→推理→行动）
├── tools.py           # 5 个工具函数 + OpenAI Function Calling Schema
├── notes.md           # 学习笔记（原始记录）
├── requirements.txt   # Python 依赖列表
├── .env.example       # 环境变量配置示例
└── .env               # 你的真实配置（不提交到 git）
```

## 🚀 快速启动

```bash
# 1. 进入项目目录
cd projects/01-simple-agent

# 2. 创建并激活虚拟环境（使用 uv）
uv venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. 安装依赖
uv pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下内容：
# OPENAI_API_KEY=sk-xxxxxxxx
# OPENAI_BASE_URL=https://...   （如使用代理，否则删除此行）
# OPENWEATHERMAP_API_KEY=xxxx   （可先不填，天气工具会提示报错）
# LOG_LEVEL=INFO                （DEBUG 可看到详细工具调用过程）

# 5. 启动
python main.py
```

### 日志调试

通过 `LOG_LEVEL` 控制输出详细程度：

```bash
# 默认：只显示关键步骤（工具名称、轮次）
LOG_LEVEL=INFO python main.py

# 调试模式：显示工具参数、执行结果等所有细节
LOG_LEVEL=DEBUG python main.py

# 静默模式：只显示最终回答
LOG_LEVEL=OFF python main.py
```

---

## ✅ 完成标准

| 标准 | 状态 | 备注 |
|------|------|------|
| Agent 能正确处理用户输入 | ✅ 通过 | 2026-06-26 验证 |
| 能调用至少 2 个工具 | ✅ 通过 | 5/5 个工具全部验证通过 |
| 能返回合理的结果 | ✅ 通过 | 结果准确，错误处理优雅 |
| 代码有基本的错误处理 | ✅ 通过 | 代码审查 + 运行验证 |
| 能演示 3-5 个测试用例 | ✅ 通过 | 完成 4 个测试用例 |

---

## 🧪 测试用例

1. **简单计算**
   - 输入：`计算 2 的 13 次方`
   - 期望：调用 `calculator`，返回 `8192`
   - 状态：✅ 通过 — 返回 8192，公式 `2 ** 13` 正确

2. **时间查询**
   - 输入：`现在几点了？`
   - 期望：调用 `get_current_time`，返回当前时间
   - 状态：✅ 通过 — 返回 `2026-06-26 09:05:17 星期五`

3. **单位换算**
   - 输入：`100 华氏度是多少摄氏度？`
   - 期望：调用 `unit_converter`，返回约 `37.78°C`
   - 状态：✅ 通过 — 返回 37.777778°C，公式 `°C = (°F − 32) × 5/9` 正确

4. **文本统计**
   - 输入：`帮我统计这句话有多少个字：人工智能改变世界`
   - 期望：调用 `text_stats`，返回字数统计
   - 状态：✅ 通过 — 返回 8 个中文字符，统计正确

5. **天气查询**
   - 输入：`今天杭州天气`
   - 期望：调用 `get_weather`，返回实时天气
   - 状态：✅ 通过 — 返回 26.5°C、湿度 75%、多云，真实 API 数据正确

6. **多步骤任务**
   - 输入：`计算 100 + 200，然后告诉我结果是奇数还是偶数`
   - 期望：调用 `calculator` 后 LLM 继续推理，返回"偶数"
   - 状态：✅ 通过 — 返回 300 为偶数，LLM 正确推理工具结果

---

## 📚 相关资源

- [Agent 基础概念笔记](../../notes/agent-basics.md)
- [工具调用笔记](../../notes/tool-calling.md)
- [OpenAI Function Calling 文档](https://platform.openai.com/docs/guides/function-calling)
- [OpenWeatherMap API 注册](https://openweathermap.org/api)

---

## 🔗 后续项目

完成本项目后，可以继续：
- **项目 02**：`tool-calling` - 实现更复杂的工具系统
- **项目 03**：`react-agent` - 实现 ReAct 模式

---

**创建时间**：2026-06-25  
**完成时间**：2026-06-26  
**状态**：✅ 全部完成（6/6 测试用例通过，5/5 工具验证通过）
