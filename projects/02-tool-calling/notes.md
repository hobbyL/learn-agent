# 项目 02：工具系统架构 — 学习笔记

> 在实现过程中遇到的问题、踩的坑、想通的点，随手记在这里。
> 完成后再把通用知识提炼到主目录 `notes/`。

---

## 实现日志

### 2026-06-26 完成工具系统骨架（手搓版）
- `registry.py`：`@tool` 装饰器 + `ToolRegistry` 单例。被装饰的函数"定义即注册"，
  agent 从注册表拿工具，彻底干掉 01 里手写的 `tool_map` 和 `TOOLS_DEFINITION`。
- `schema_gen.py`：手搓 Schema 生成器（路线 A 上半场）。用 `inspect.signature` 读签名，
  把 `str/int/float/bool/list[X]/Literal[...]` 翻译成 JSON Schema；有默认值 = 可选，无默认值 = 必填。
- `tools.py`：8 个本地工具（密码/随机抽取/颜色/进制/大小写/骰子/哈希/字符画），
  纯类型注解，不依赖 Pydantic（Pydantic 留作下半场对照）。
- `agent.py` / `main.py`：从 01 改造，dispatch 改为查注册表，tools 改为 `registry.get_schemas()`。
- 静态验证（不调 LLM）：8 个工具全部自动注册、Schema 正确生成、函数执行正确。

---

## 遇到的问题

### ⭐ 幻觉式工具调用（02 最有价值的实战发现）

**现象**：问"计算 2 的 10 次方"，但 02 工具集里**根本没有计算器**。LLM 却：
1. 硬调了一个完全不相关的 `hash_generator(text="2")`；
2. 拿到一串哈希值后**无视工具结果**，自己心算给出"1024"（答案蒙对了，但过程全错）。

**拆成两个独立问题**：
- 问题 A（能力边界）：任务超出工具覆盖范围时，LLM 不会老实说"我没有合适的工具"，
  而是倾向硬凑一个来调用 → **幻觉式工具调用**。
- 问题 B（结果可信度）：LLM 把工具结果当摆设，凭记忆/心算作答 → 01 笔记里"惰性优化"的升级版，
  更危险，因为它连工具返回值都敢无视。

**根因**：这不是代码 bug，是 LLM 的天性——
①「取悦倾向」：宁愿硬给答案，也不愿承认做不了；
②「过度自信」：简单计算它"背得出来"，懒得依赖工具。
**无法 100% 根治，只能大幅降概率 + 加护栏。**

**修复（路线 1+2：只改 SYSTEM_PROMPT，零代码逻辑改动）**：
- 【能力边界】最高优先级规则：工具覆盖不了时，绝不硬凑工具；如实告知"工具无法完成"，
  再凭知识尽力给参考答案，但必须标注"仅凭记忆、未经工具验证"。
- 【工具结果必须被使用】：调了工具，最终回答就必须基于其返回值；发现结果驴唇不对马嘴，
  应承认调错而不是假装有用或自行编答案。

**验证结果（6 个用例全部正确）**：
- 算 2¹⁰ → 不调工具，如实说没有计算工具 + 标注未验证给 1024 ✅
- 颜色转 YUV → color_converter 在但不支持 YUV，**没硬调**，凭 BT.601 公式给参考值并标注 ✅（更难的边界，也过了）
- 生成密码 / 16位带符号密码 → 正常调 password_generator ✅（没误伤）
- 密码→二维码 → 链式调用 password_generator → qr_text_encoder ✅

---

## 学到的内容

1. **prompt 是 Agent 行为最强的杠杆**：一行代码逻辑没改，只动 SYSTEM_PROMPT，
   就压住了"幻觉式工具调用"。这是"改 prompt 看行为变化"实验的正向印证——prompt 威力肉眼可见。

2. **"能力边界"判断比想象中细腻**：LLM 不只能判断"有没有工具"，还能判断"工具够不够用"
   （YUV 案例：color_converter 在场，但 LLM 判断它输出不了 YUV，于是不调）。

3. **但这一切都是概率性的，不是 100% 可靠**：今天表现完美，换个问法/换个模型仍可能翻车。
   prompt 护栏的定位是"大幅降低概率"，真正的确定性兜底要留到 03（ReAct）/04（反思）。

4. **error 信息影响循环的延续**：工具内部校验失败时返回的错误（如"count 超界，请调小到 N 以内重试"）
   是给 LLM 做决策用的，明确区分"可重试 / 不可重试"——呼应 01 的同名教训。

5. **手搓 Schema 的边界**：手搓版只把枚举范围"告诉"LLM，并**不在运行时强制校验**。
   若 LLM 真传了枚举外的值，得靠工具内部 `if` 自己拦——这正是后续引入 Pydantic（自动校验）的价值。

---

## 手搓 Schema vs Pydantic 对比

> 两条路线都已走完，以下是实际体会总结。

### 代码量对比

| 维度 | 手搓版 (schema_gen.py) | Pydantic 版 (schema_gen_pydantic.py) |
|------|----------------------|--------------------------------------|
| Schema 生成逻辑 | ~80 行（inspect + 类型映射 + 拼装） | ~30 行（model_json_schema + 清理 title） |
| 参数描述 | 分散在 @tool(params={...}) 里 | 和类型写在一起 Field(description=...) |
| 运行时校验 | 无（全靠工具内部 if） | model_validate() 一行 |
| 错误信息格式化 | 每个工具手写 error 文案 | _format_validation_error() 通用 |

### 手搓版遇到的麻烦 → Pydantic 怎么解决的

1. **类型映射要逐个写**
   - 手搓：`_annotation_to_schema()` 要 if/elif 判断 str/int/bool/list/Literal 五种
   - Pydantic：类型系统是它的核心能力，str/int/bool/list/Literal/Optional/Union/嵌套对象 全自动

2. **required 判断逻辑要手写**
   - 手搓：`if param.default is inspect.Parameter.empty → required`
   - Pydantic：有默认值的 Field 自动 optional，没有的自动 required

3. **枚举只是"建议"，运行时拦不住**
   - 手搓：`Literal["hex","rgb","hsl"]` 生成了 `"enum": [...]` 告诉 LLM，但 LLM 传 "yuv" 照样能到达工具函数
   - Pydantic：`model_validate()` 直接抛 `literal_error`，工具函数根本收不到非法值

4. **类型不宽容**
   - 手搓：LLM 传 `"16"`（字符串）给 int 参数，Python 函数收到字符串就炸
   - Pydantic：自动做宽容类型转换（`"16"` → `16`），减少 LLM 格式瑕疵导致的失败

5. **错误信息要自己写**
   - 手搓：每个校验点要写 `{"error": "length 太短..."}` 人话文案
   - Pydantic：ValidationError 自带 field + msg + input，一个通用函数格式化所有工具的错误

### 手搓版的价值（不是白走的弯路）

- 你亲眼看到"从签名生成 Schema"的完整链路：`inspect → 类型判断 → properties + required 拼装`
- 你理解了 JSON Schema 的结构不是魔法，就是 `{"type":"object","properties":{...},"required":[...]}`
- 你体会到"手搓能覆盖 80% 简单场景，但在复杂类型和运行时校验上很快到顶"
- 这些理解让你用 Pydantic 时不是"黑盒调 API"，而是知道它背后替你做了什么

### SCHEMA_ENGINE 配置切换

最终实现了"一行配置切两条完整路线"：

```bash
# .env 加一行
SCHEMA_ENGINE=handcraft   # 或 pydantic
```

| 阶段 | handcraft 模式 | pydantic 模式 |
|------|---------------|---------------|
| Schema 生成 | `@tool` → `build_schema()`（inspect 读签名） | `@tool(model=XxxParams)` → `build_schema_pydantic()`（model_json_schema） |
| 参数校验 | 无（靠工具内部 if） | `validate_tool_args()` 自动拦截 |
| 类型转换 | 无（字符串"16"会炸） | Pydantic 宽容转换（"16"→16） |

验证对比：
- handcraft 传 `to_format="yuv"` → 悄悄当 hsl 处理（静默错误）
- pydantic 传 `to_format="yuv"` → 调用前拦截，返回明确错误给 LLM

### 一句话总结

> **JSON Schema 是通用协议，Pydantic 是 Python 生态里生成它 + 强制校验的标准方案。**
> 手搓帮你理解协议本身，Pydantic 帮你在生产中不重复造轮子。
