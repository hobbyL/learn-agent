# 项目 02：工具系统架构（Tool Calling）

把"散装函数 + 手写 Schema + 硬编码 dispatch"升级成
"只写函数 → 自动注册 + 自动生成 Schema + 自动校验参数"的工具系统。

---

## 📋 项目信息

**难度**：⭐⭐⭐☆☆
**预计时间**：3-4 天
**前置项目**：[01-simple-agent](../01-simple-agent/)（已完成）

**学习目标**：
- 理解工业级 Agent 框架为什么都要做"工具抽象"
- 掌握"代码即 Schema"：从函数签名自动生成 JSON Schema
- 掌握参数校验，并把校验错误喂回 LLM 让它自我纠正
- 体会 `@tool` 装饰器 + 注册表这一所有框架的共同地基

---

## 🤔 为什么需要 02？（01 暴露的痛点）

01 里加一个工具，要改**三个地方**，且信息重复：

```python
# ① 写函数（tools.py）
def calculator(expression: str): ...

# ② 手写一份 JSON Schema 告诉 LLM（tools.py 的 TOOLS_DEFINITION）
{"name": "calculator", "parameters": {"properties": {"expression": {"type": "string"}}, ...}}

# ③ 在 dispatch 表里登记（agent.py 的 tool_map）
tool_map = {"calculator": calculator, ...}
```

问题：`expression: str` 写了两遍（函数签名一遍、Schema 一遍），改了函数忘改 Schema，LLM 就拿到过时信息。
**02 要消灭这种重复**：只写函数，Schema 和注册自动完成。

---

## 🎯 核心范围

| 范围 | 做 / 不做 | 说明 |
|------|----------|------|
| 工具注册机制 | ✅ 做 | `@tool` 装饰器 + 注册表，加工具不用改 agent |
| 自动 Schema 生成 | ✅ 做 | **路线 A**：先手搓反射版（理解原理）→ 再用 Pydantic（学框架做法） |
| 参数校验 | ✅ 做 | 和 Pydantic 合并；校验错误喂回 LLM 让它自我纠正 |
| 并行工具调用 | ❌ 不做 | 偏性能优化，与主线关系弱，留作后续 |

---

## 🛠️ 8 个新工具（全部本地计算，无需外部 API）

特意**不复用 01 的工具**——从零设计新工具，才能完整经历
"想清楚参数 → 写函数 → Schema 自动生成 → 看校验生效"的全流程。
这 8 个工具的参数类型组合，刻意覆盖了手搓 Schema 时会踩的**所有典型坑**：

| 工具 | 参数 | 专门用来练的 Schema 场景 |
|------|------|------------------------|
| `qr_text_encoder` 文本转字符画二维码 | `text: str`、`size: int = 3` | 入门基准：str + int |
| `password_generator` 生成随机密码 | `length: int`、`use_symbols: bool = True` | **bool** + 带默认值的可选参数 |
| `random_picker` 从列表随机选 | `options: list[str]`、`count: int = 1` | **list 类型**怎么翻译成 Schema |
| `color_converter` 颜色格式转换 | `value: str`、`to_format: str`(hex/rgb/hsl) | **单值枚举** + 非法值校验 |
| `base_converter` 进制转换 | `number: str`、`from_base: int`、`to_base: int` | **多个必填参数**（required 列表） |
| `text_caseconverter` 大小写转换 | `text: str`、`mode: str`(upper/lower/title/snake/camel) | **多值枚举**（5 选项，密集枚举边界） |
| `dice_roller` 掷骰子 | `sides: int = 6`、`times: int = 1` | **全部带默认值**（required 为空） |
| `hash_generator` 计算哈希 | `text: str`、`algorithm: str`(md5/sha1/sha256)、`uppercase: bool = False` | **枚举 + bool + 默认值**混合复杂参数 |

> 参数场景全谱：`必填 str/int/bool/list`、`可选带默认值`、`单值/多值枚举`、`多必填参数`、`全可选(required 空)`、`混合复杂参数`

---

## 📝 实现步骤（建议顺序）

> 学习原则：**先手写理解原理，再用框架**。不要一上来就 Pydantic。

### 第 1 步：工具注册机制 ✅
- ✅ 设计 `@tool` 装饰器：被装饰的函数自动登记到一个全局注册表
- ✅ 注册表能列出所有工具、按名字取函数
- ✅ agent 从注册表拿工具，不再硬编码 `tool_map`

### 第 2 步：手搓 Schema 生成（路线 A 上半场） ✅
- ✅ 用 `inspect.signature()` 读函数签名
- ✅ 把 `str/int/float/bool` 映射成 JSON Schema 的 `type`
- ✅ 处理 `list[str]` → `{"type": "array", "items": {"type": "string"}}`
- ✅ 处理默认值 → 区分 required / optional
- ✅ **踩坑记录**：枚举怎么办？复杂类型怎么办？哪里开始变得繁琐？（已写进 notes.md）

### 第 3 步：换上 Pydantic（路线 A 下半场） ✅
- ✅ 为每个工具定义一个 Pydantic 参数模型（8 个 BaseModel）
- ✅ `model.model_json_schema()` 自动出 Schema（对比手搓版有多干净）
- ✅ `model.model_validate(args)` 自动校验 LLM 传回的参数
- ✅ **对比记录**：Pydantic 帮你省掉了第 2 步的哪些麻烦？（已写进 notes.md）

### 第 4 步：参数校验闭环 ✅
- ✅ LLM 传错参数时，把 Pydantic 的校验错误转成可读信息
- ✅ 把错误喂回 LLM（role="tool"），观察它能否自我纠正后重试
- ✅ 呼应 01 的教训："error 信息影响 Agent 循环行为"

### 第 5 步：迁移 8 个工具 + 测试 ✅
- ✅ 用新系统实现 8 个工具（先跑通 1~2 个，再快速铺开）
- ✅ 跑通正常用例（6 个真机用例全部通过）
- ✅ **故意传错参数**用例：枚举非法值、缺少必填字段、类型不对——全部被 Pydantic 拦截并喂回 LLM
- ✅ 记录学习笔记，提炼"手搓 vs Pydantic"对比到 notes.md

---

## 📦 项目结构

```
02-tool-calling/
├── README.md              # 本文件
├── main.py                # 命令行入口（从 01 改：工具清单/示例已更新）
├── agent.py               # Agent 循环（dispatch 查注册表 + Pydantic 校验）
├── registry.py            # @tool 装饰器 + 工具注册表（定义即注册）
├── schema_gen.py          # 手搓 Schema 生成器（路线 A 上半场，理解原理用）
├── schema_gen_pydantic.py # 🆕 Pydantic 版（路线 A 下半场，对照 + 运行时校验）
├── tools.py               # 8 个新工具（纯类型注解，两套 Schema 生成器都能驱动）
├── notes.md               # 学习笔记
├── requirements.txt       # 依赖（含 pydantic>=2.0.0）
├── .env.example           # 环境变量示例（无需 OpenWeatherMap）
└── .env                   # 真实配置（不提交）
```

> 通过 `.env` 中的 `SCHEMA_ENGINE` 配置切换两条完整路线：
>
> | 配置 | Schema 生成 | 参数校验 | 适合 |
> |------|------------|---------|------|
> | `handcraft`（默认） | `schema_gen.py`（inspect + 类型映射） | 无（靠工具内部 if） | 理解原理 |
> | `pydantic` | `schema_gen_pydantic.py`（model_json_schema） | validate_tool_args() 自动拦截 | 学框架做法 |
>
> 一行配置切换两个世界，同一套 8 个工具，对比学习更直观。

---

## 🚀 快速启动

```bash
# 1. 进入项目目录
cd projects/02-tool-calling

# 2. 准备虚拟环境（二选一）
#    方式 A：复用 01 已建好的环境（本项目依赖与 01 基本一致）
source ../01-simple-agent/.venv/bin/activate
#    方式 B：本项目单独建环境（使用 uv）
# uv venv
# source .venv/bin/activate          # macOS / Linux
# # .venv\Scripts\activate           # Windows
# uv pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下内容：
# OPENAI_API_KEY=sk-xxxxxxxx
# OPENAI_BASE_URL=https://...   （如使用代理，否则保留默认）
# MODEL_NAME=gpt-4o-mini        （可选，默认 gpt-4o-mini）
# LOG_LEVEL=INFO                （DEBUG 可看到工具调用全过程）
# SCHEMA_ENGINE=handcraft       （手搓版，默认；改为 pydantic 切换引擎）

# 4. 启动（默认 handcraft 模式）
python main.py

# 或切换到 Pydantic 模式体验运行时校验
SCHEMA_ENGINE=pydantic python main.py
```

> 注意：02 的 8 个工具全部是**本地计算**（密码、骰子、进制、哈希等），
> 不依赖任何外部 API，所以**不需要** OpenWeatherMap 之类的 Key，只需 OpenAI Key。

### 日志调试

通过 `LOG_LEVEL` 控制输出详细程度：

```bash
# 默认：只显示关键步骤（第几轮推理、调用了哪个工具）
LOG_LEVEL=INFO python main.py

# 调试模式：额外显示工具参数、执行结果等所有细节
LOG_LEVEL=DEBUG python main.py

# 静默模式：只显示最终回答
LOG_LEVEL=OFF python main.py
```

### 不启动 Agent，只验证工具系统（无需 OpenAI Key）

注册表和 Schema 生成是纯本地逻辑，可以脱离 LLM 单独验证：

```bash
# 查看 8 个工具是否都自动注册、Schema 是否正确生成
python -c "import tools; from registry import registry; \
print('已注册工具：', registry.list_names())"
```

---

## ✅ 完成标准

| 标准 | 状态 |
|------|------|
| `@tool` 装饰器能自动注册工具，agent 不再硬编码 dispatch | ✅ |
| 手搓 Schema 生成器能处理 str/int/bool/list/默认值 | ✅ |
| Pydantic 版能自动生成 Schema + 校验参数 | ✅ |
| 参数校验错误能喂回 LLM 并触发自我纠正 | ✅ 已集成到 agent._dispatch_tool |
| 8 个工具全部接入新系统并验证通过 | ✅ |
| "故意传错参数"用例展示校验反馈闭环 | ✅ validate_tool_args 拦截枚举/缺字段/类型 |

---

## 🔗 相关

- 上一项目：[01-simple-agent](../01-simple-agent/)
- 工具调用笔记：[../../notes/tool-calling.md](../../notes/tool-calling.md)
- Pydantic 文档：https://docs.pydantic.dev/

---

**创建时间**：2026-06-26
**状态**：✅ 完成
