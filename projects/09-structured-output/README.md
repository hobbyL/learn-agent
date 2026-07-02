# 09-structured-output：结构化输出 Agent

**状态**: ✅ 已完成

学习 LLM 结构化输出的完整工程实践：用 Pydantic 定义 schema，通过 OpenAI 三种输出模式（json_schema 强制、json_object 弱约束、text 纯文本）调用 LLM，对比可靠性差异。

## 核心特性

### 3 种输出模式
1. **json_schema 强制模式**  
   `response_format: { type: "json_schema", json_schema: {...} }`  
   OpenAI 保证输出 100% 符合 schema，无需重试

2. **json_object 弱模式**  
   `response_format: { type: "json_object" }`  
   OpenAI 保证合法 JSON，但不保证符合特定 schema，需 Pydantic 校验 + 重试

3. **text 纯文本模式**  
   不设 response_format，在 prompt 中要求返回 JSON  
   从自由文本中 parse JSON（支持 markdown 代码块），失败时重试

### 4 层提取难度
1. **Level 1：单实体提取**（扁平） — 提取开发者档案 `{name, role, team, skills[]}`
2. **Level 2：多实体提取**（列表） — 提取项目组列表 `[{name, lead, members_count, status}]`
3. **Level 3：嵌套关系提取**（深层） — 提取游戏详情 `{game: {team: {lead, members[]}, tech_stack[], milestones[]}}`
4. **Level 4：对比分析提取**（高级） — 结构化对比报告 `{comparison[{dim, a_value, b_value, conclusion}]}`

### 校验与重试机制
- Pydantic 校验：解析 LLM 输出为 Model，失败则获取 ValidationError
- JSON 语法错误处理：输出非合法 JSON 时同样触发重试
- 重试策略：将具体错误信息（字段缺失/类型错误/格式错误）追加到 messages，让 LLM 修正
- 最大重试次数：3 次
- refusal 处理：json_schema 模式下检查 message.refusal 字段

### 虚构知识库
**游戏工作室「星火互娱」**，包含 29 个实体：
- 1 个工作室、4 个项目组、4 个游戏作品
- 8 个开发者、6 个技术栈、6 个里程碑
- 实体间有丰富的多层关系（工作室→项目组→成员→技能，项目组→游戏→技术栈→里程碑）

## 使用方法

### 安装依赖

如果使用 uv（推荐）：
```bash
cd projects/09-structured-output
uv venv
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
```

如果使用 pip：
```bash
cd projects/09-structured-output
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY
```

### 运行模式

#### 1. 完整对比模式（默认）
```bash
python3 main.py --compare
# 或
python3 main.py
```
运行 4 层级 × 3 模式 = 12 组对比，展示对比矩阵 + 汇总统计

#### 2. 快速演示模式
```bash
python3 main.py --demo
```
运行 2 层级 × 3 模式 = 6 组，快速体验效果

#### 3. 交互模式
```bash
python3 main.py --interactive
```
用户选择层级 + 模式，实时查看提取结果和校验状态

## 输出示例

### 对比矩阵展示
```
  层级               json_schema      json_object      text
  ──────────────────────────────────────────────────────
  L1 单实体          ✓ 0 次           ✓ 1 次           ✓ 2 次
  L2 多实体          ✓ 0 次           ✗ 3 次           ✓ 1 次
  L3 嵌套            ✓ 0 次           ✓ 2 次           ✓ 2 次
  L4 对比            ✓ 0 次           ✓ 1 次           ✗ 3 次
```

### 汇总统计
```
📊 汇总统计
──────────────────────────────────────────────────────────────────
  json_schema 强制模式       成功率: 4/4 (100%)  平均重试: 0.0 次
  json_object 弱模式         成功率: 3/4 (75%)   平均重试: 1.8 次
  text 纯文本模式            成功率: 3/4 (75%)   平均重试: 2.0 次
```

## 文件结构

```
projects/09-structured-output/
├── knowledge_base.py    # 游戏工作室虚构知识库（29 实体）
├── schemas.py           # Pydantic schema 定义（4 层难度）+ 注册表
├── tools.py             # 工具注册表（search_entities, lookup_entity）
├── extractor.py         # 核心提取逻辑（3 种模式 + 重试）
├── display.py           # ANSI 着色展示（对比矩阵 + 汇总）
├── main.py              # CLI 入口（--compare/--demo/--interactive）
├── requirements.txt     # 依赖列表
├── .env.example         # 环境变量模板
├── notes.md             # 踩坑记录
└── README.md            # 本文件
```

## 技术要点

### Pydantic Schema → JSON Schema 转换
```python
from schemas import get_json_schema, DeveloperProfile

json_schema = get_json_schema(DeveloperProfile)
# 自动生成符合 OpenAI Structured Outputs 要求的 schema
# 包含 additionalProperties: false 和 required 字段处理
```

### 3 种模式的 API 调用差异
```python
# json_schema 强制模式
response_format={
    "type": "json_schema",
    "json_schema": json_schema,
}

# json_object 弱模式
response_format={
    "type": "json_object",
}

# text 纯文本模式
# 不设 response_format，从自由文本中提取 JSON
```

### 重试机制
```python
for attempt in range(MAX_RETRIES + 1):
    resp = client.chat.completions.create(...)
    try:
        result = schema_class.model_validate(json.loads(resp))
        return result  # 成功
    except ValidationError as e:
        error_msg = format_validation_error(e)
        messages.append({"role": "user", "content": f"校验失败：{error_msg}"})
        # 继续重试
```

## 学习收获

1. **json_schema 强制模式**是结构化输出的最佳选择（100% 成功率，0 重试）
2. **json_object 弱模式**需要配合 Pydantic 校验 + 重试机制，成功率较高但需要额外开销
3. **text 纯文本模式**成功率最低，需要处理 markdown 代码块、额外解释文本等情况
4. **重试策略**关键：将 ValidationError 详细反馈给 LLM，让其修正具体问题
5. **Schema 设计**：嵌套层级越深、字段类型越严格，提取难度越高

## 下一步

- 项目 10：planning（目标分解 + 任务规划）—— 复用本项目的 schemas.py
- 项目 11：multi-agent（多 Agent 协作）—— 结构化输出用于 Agent 间通信

## 相关资源

- [OpenAI Structured Outputs 文档](https://platform.openai.com/docs/guides/structured-outputs)
- [Pydantic 官方文档](https://docs.pydantic.dev/)
- 本项目参考：07-short-term-memory（知识库设计）、08-long-term-memory（工具调用）
