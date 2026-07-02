# 结构化输出（Structured Outputs）

LLM 默认输出自然语言，无法直接用于程序逻辑。结构化输出解决"如何让 LLM
稳定返回可编程的数据格式"这个工程问题。

---

## 核心思想

**LLM 输出不可预测的根本原因**

模型生成的是概率分布下的 token 序列，没有内置约束机制。
即使 prompt 里写了"请返回 JSON"，模型也可能：

- 在 JSON 前加解释文字（`当然，以下是...{}`）
- 字段名拼写不一致（`skill` vs `skills` vs `skill_list`）
- 嵌套层级错误或缺失必填字段
- 枚举值自由发挥（本应是 `active`，返回了 `Active` 或 `在进行中`）

结构化输出的意义：将"模型生成"从自然语言空间约束到特定数据空间，
让输出可被程序直接解析和使用。

---

## 三种方式对比

| 方式 | API 参数 | 可靠性 | 适用场景 |
|------|---------|--------|---------|
| **json_schema 强制模式** | `response_format={type:"json_schema", json_schema:{...}}` | ★★★ 100% 符合 schema | 生产环境、关键数据提取 |
| **json_object 弱模式** | `response_format={type:"json_object"}` | ★★ 合法 JSON，不保证 schema | 快速原型、字段灵活的场景 |
| **纯文本 + prompt** | 不设 response_format | ★ 依赖模型遵从指令程度 | 兼容老模型、实验性场景 |

### json_schema 强制模式

模型通过受约束解码（Constrained Decoding）保证输出严格匹配 schema。
实质是在 token 生成时，直接过滤掉不符合 schema 的 token。

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "DeveloperProfile",
            "strict": True,
            "schema": schema_dict,   # 从 Pydantic model 生成
        }
    }
)

# 检查 refusal（模型拒绝时会填充此字段，而非 content）
msg = response.choices[0].message
if msg.refusal:
    print(f"模型拒绝：{msg.refusal}")
else:
    data = json.loads(msg.content)
```

**限制**：
- `additionalProperties` 必须显式设为 `false`
- 所有属性必须出现在 `required` 列表中（不支持可选字段）
- 不支持 `default`、`nullable`（用 `anyOf: [type, null]` 替代）
- 递归 schema 支持有限（`$defs` 层级不能太深）

### json_object 弱模式

只保证返回合法 JSON，不验证字段结构。
需要在 prompt 中描述期望的结构，并在应用层用 Pydantic 验证。

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    response_format={"type": "json_object"}
)
raw = json.loads(response.choices[0].message.content)
validated = MySchema.model_validate(raw)  # 可能抛 ValidationError
```

### 纯文本 + prompt engineering

不设 `response_format`，在 prompt 中要求返回 JSON：

```
请提取以下信息并以 JSON 格式返回，不要有其他内容：
{"name": "...", "role": "...", "skills": [...]}
```

从回复中提取 JSON：

```python
text = response.choices[0].message.content
# 尝试直接 parse；失败则用正则提取 ```json ... ``` 块
try:
    data = json.loads(text)
except json.JSONDecodeError:
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
```

---

## OpenAI Structured Outputs 的核心约束

使用 `json_schema` 强制模式时，schema 必须满足以下要求：

### 1. additionalProperties: false

所有 object 类型（含嵌套的 `$defs` 中的对象）都必须声明：

```json
{
  "type": "object",
  "properties": {...},
  "required": ["name", "role"],
  "additionalProperties": false   ← 必须显式写
}
```

### 2. 所有属性必须在 required 列表

不支持可选字段。需要"可选"时，用 `anyOf: [type, null]` + 在 prompt 中说明：

```json
{
  "bio": {
    "anyOf": [{"type": "string"}, {"type": "null"}]
  }
}
```

### 3. $defs 中的嵌套 schema 同样需要递归处理

Pydantic 生成的 schema 对嵌套 model 使用 `$defs` + `$ref` 引用。
提交给 OpenAI 时，`$defs` 中每个子 schema 也必须满足上述约束。

### 4. 不支持的关键字

| 不支持 | 替代方案 |
|--------|---------|
| `default` | 在 prompt 中说明默认值 |
| `nullable: true` | `anyOf: [type, null]` |
| `minLength` / `maxLength` 等验证关键字 | 在 prompt 中约束，或 Pydantic 后处理 |
| `oneOf` / `anyOf`（部分场景） | 简化 schema，避免复杂 union |

---

## Pydantic 与 JSON Schema 的配合

### model_json_schema() 自动生成 schema

```python
from pydantic import BaseModel, Field
from typing import List

class DeveloperProfile(BaseModel):
    name: str = Field(description="开发者姓名")
    role: str = Field(description="职位，如 Lead / Engineer / Designer")
    team: str = Field(description="所属团队名称")
    skills: List[str] = Field(description="技能列表")

# 自动生成 JSON Schema
schema = DeveloperProfile.model_json_schema()
```

### Pydantic v2 的 $defs 机制

嵌套 Model 会被提取到 `$defs`，主 schema 用 `$ref` 引用：

```python
class TeamInfo(BaseModel):
    lead: str
    members: List[str]

class GameDetail(BaseModel):
    name: str
    team: TeamInfo    ← 嵌套 Model
    tech_stack: List[str]

# 生成的 schema 结构：
# {
#   "properties": {
#     "team": {"$ref": "#/$defs/TeamInfo"},
#     ...
#   },
#   "$defs": {
#     "TeamInfo": {
#       "properties": {"lead": ..., "members": ...},
#       ...
#     }
#   }
# }
```

提交给 `json_schema` 模式前，需要对 `$defs` 中每个对象递归添加
`additionalProperties: false` 和确保 `required` 完整。

### ValidationError 的信息提取

```python
from pydantic import ValidationError

try:
    result = DeveloperProfile.model_validate(raw_dict)
except ValidationError as e:
    # e.errors() 返回详细错误列表
    for err in e.errors():
        print(f"字段 {'.'.join(str(x) for x in err['loc'])}: {err['msg']}")
    # 输出示例：
    # 字段 skills: Input should be a valid list
    # 字段 role: Field required
```

### 将 ValidationError 转换为 LLM 错误提示

```python
def format_validation_error(e: ValidationError) -> str:
    errors = []
    for err in e.errors():
        field = ".".join(str(x) for x in err["loc"])
        errors.append(f"- 字段 `{field}`: {err['msg']}")
    return "JSON 结构校验失败，请修正以下问题：\n" + "\n".join(errors)
```

将此字符串追加到 messages 中，让 LLM 根据具体错误修正输出。

---

## 重试机制设计模式

### 错误分类

| 错误类型 | 触发条件 | 处理方式 |
|---------|---------|---------|
| JSON 语法错误 | `json.JSONDecodeError` | 提示"返回内容不是合法 JSON" |
| Schema 校验错误 | `pydantic.ValidationError` | 提示具体字段错误 |
| refusal | `message.refusal` 非空 | 不重试，直接报告拒绝原因 |
| 空输出 | `content` 为空或 None | 提示"返回了空内容" |

### 重试循环结构

```python
def extract_with_retry(
    messages: list,
    schema_class: type[BaseModel],
    mode: str,
    max_retries: int = 3,
) -> tuple[BaseModel | None, dict]:
    errors = []

    for attempt in range(max_retries + 1):
        try:
            raw = call_llm(messages, schema_class, mode)
            data = json.loads(raw)
            result = schema_class.model_validate(data)
            return result, {"retries": attempt, "is_valid": True, "errors": errors}

        except json.JSONDecodeError as e:
            err_msg = f"JSON 语法错误：{e}"
        except ValidationError as e:
            err_msg = format_validation_error(e)

        errors.append(err_msg)

        # 将错误追加到 messages，让 LLM 修正
        if attempt < max_retries:
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"你的输出有问题，请修正后重新返回：\n{err_msg}"},
            ]

    return None, {"retries": max_retries, "is_valid": False, "errors": errors}
```

### 重试次数与成本权衡

- `json_schema` 强制模式：理论上不需要重试（schema 100% 符合）
- `json_object` 弱模式：字段错误时需重试，建议 2-3 次
- 纯文本模式：JSON 语法错误概率高，建议 3 次
- 每次重试 = 额外一次 API 调用，生产环境需监控重试率

### 不同模式的重试必要性

```
json_schema  [────────────────────] 100% 成功（受约束解码）
json_object  [──────────────░░░░░] ~80% 成功，字段不稳定
纯文本提取   [────────────░░░░░░░░] ~60% 成功，格式不稳定
              0%                 100%
```

---

## 实践建议

### 何时用 json_schema vs json_object

**用 json_schema 的场景**：
- 输出结构固定，有明确的必填字段
- 下游直接依赖结构（数据库写入、API 传参）
- 模型版本支持 Structured Outputs（gpt-4o, gpt-4o-mini）

**用 json_object 的场景**：
- 字段数量或名称随内容动态变化
- 模型不支持 `json_schema`（老版本 GPT-3.5）
- 快速原型验证，schema 还在迭代中

### Schema 设计原则

**1. Field description 要具体**

```python
# ❌ 含糊
status: str = Field(description="状态")

# ✅ 明确
status: str = Field(description="项目状态，只能是以下之一：active / completed / cancelled")
```

**2. 用枚举约束取值范围**

```python
from typing import Literal

class ProjectInfo(BaseModel):
    status: Literal["active", "completed", "cancelled"]
```

**3. 避免过深的嵌套**

json_schema 模式对递归 schema 支持有限，超过 3-4 层嵌套建议拆分为多次提取。

### 避免 LLM Schema Hallucination

LLM 有时会"发明"不在 schema 中的字段，或忽略必填字段。

**技巧**：
- 在 system prompt 中重述关键字段名（与 schema 保持一致）
- 避免字段名歧义（`name` 太泛，`game_name` 更精确）
- 对 `json_object` 模式，在 prompt 中提供 JSON 模板示例：

```
请按以下格式返回（不要修改字段名）：
{"game_name": "...", "tech_stack": [...], "team_lead": "..."}
```

---

## 与 Function Calling 的区别

| 维度 | Structured Outputs | Function Calling |
|------|-------------------|-----------------|
| 目的 | 约束最终输出格式 | 触发外部工具调用 |
| 控制时机 | 生成最终答案时 | 生成中间步骤时 |
| 输出类型 | 固定 schema 的 JSON | 工具调用参数（也是 JSON） |
| 常见场景 | 信息提取、报告生成 | 查询数据库、执行操作 |
| 是否执行代码 | 否 | 是（应用层执行工具） |

两者可以组合使用：Function Calling 执行工具获取数据，
Structured Outputs 将最终结果格式化为特定 schema。

---

**最后更新**：2026-07-02  
**来源项目**：09-structured-output
