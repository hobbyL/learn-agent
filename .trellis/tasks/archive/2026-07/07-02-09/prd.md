# 09-structured-output：结构化输出 Agent

## Goal

学习 LLM 结构化输出的完整工程实践：用 Pydantic 定义 schema，通过 OpenAI `response_format: json_schema`（强制模式）、`json_object`（弱模式）、纯文本提取（无约束）三种方式调用 LLM，对比可靠性差异。核心任务为"从游戏工作室知识库中提取结构化实体信息"。

## Requirements

### 知识库：游戏工作室
- 新建虚构知识库，包含：工作室、项目组、游戏作品、开发者、技术栈、里程碑等实体
- 实体间有丰富关系（工作室→项目组→成员、作品→技术栈、成员→角色/技能）
- 规模：约 20-25 个实体，足以支撑 4 层提取难度

### 3 种输出模式
1. **json_schema 强制模式**：`response_format: { type: "json_schema", json_schema: {...} }`，模型保证输出符合 schema
2. **json_object 弱模式**：`response_format: { type: "json_object" }`，模型返回合法 JSON 但不保证符合特定 schema
3. **纯文本提取**：不设 response_format，在 prompt 中要求返回 JSON，从自由文本中 parse

### 4 层提取难度
1. **单实体提取**（扁平）— 提取一个人物档案 `{name, role, team, skills[]}`
2. **多实体提取**（列表）— 提取实体列表 `[{name, lead, members_count, status}]`
3. **嵌套关系提取**（深层）— 嵌套结构 `{game: {name, team: {lead, members[]}, tech_stack[], milestones[]}}`
4. **对比分析提取**（高级）— 结构化对比报告 `{dimensions[], comparison[{dim, a_value, b_value, conclusion}]}`

### Schema 定义层
- 使用 Pydantic BaseModel 定义所有 schema（`schemas.py` 独立模块）
- Pydantic model → JSON Schema 自动转换（供 `json_schema` 模式使用）
- 设计为可复用，后续 10-planning 可直接 import

### 校验与重试机制
- Pydantic 校验：解析 LLM 输出为对应 Model，失败则获取 ValidationError
- JSON 语法错误处理：输出非合法 JSON 时同样触发重试
- 重试策略：将具体错误信息（字段缺失/类型错误/格式错误）追加到 messages，让 LLM 修正
- 最大重试次数：3 次
- refusal 处理：`json_schema` 模式下检查 `message.refusal` 字段

### 3 种运行模式
1. **`--compare`**（默认）：自动运行 4 层级 × 3 输出模式 = 12 组对比，展示每组的提取结果 + 校验通过/失败 + 重试次数
2. **`--demo`**：精简版，只跑 2 层级（单实体 + 嵌套关系）× 3 模式 = 6 组
3. **`--interactive`**：用户自由输入提取需求，选择输出模式，实时看结构化结果和校验状态

### 展示层
- ANSI 着色（沿用之前项目风格）
- 对比矩阵展示：行=难度层级，列=输出模式
- 每格展示：提取结果摘要 + ✅/❌ 校验状态 + 重试次数
- 最终汇总：各模式的成功率、平均重试次数

## Acceptance Criteria

- [ ] 知识库包含 20+ 实体，覆盖人物/项目组/作品/技术栈/里程碑
- [ ] schemas.py 用 Pydantic 定义 4 层难度对应的 4 个 schema
- [ ] json_schema 强制模式正确传递 schema 给 API，输出 100% 校验通过
- [ ] json_object 弱模式 + Pydantic 校验，失败时触发重试（最多 3 次）
- [ ] 纯文本模式能从自由文本中 parse JSON，失败时触发重试
- [ ] refusal 字段正确处理（不崩溃，展示提示）
- [ ] --compare 模式输出 4×3 对比矩阵 + 汇总统计
- [ ] --demo 模式输出 2×3 精简对比
- [ ] --interactive 模式支持自由提取 + 模式选择
- [ ] 所有依赖在 requirements.txt 中列出（openai, pydantic, python-dotenv）

## Definition of Done

- 代码实现完整，3 种模式均可运行
- notes.md 记录踩坑点
- README.md 含用法说明 + 状态标记
- .env.example 提供配置模板

## Out of Scope

- 不做并发请求（顺序调用即可）
- 不做配置热切换
- 不做 Function Calling（本项目聚焦输出结构化，不是工具调用）
- 不做任务分解/目标树（留给 10-planning）
- 不做流式输出（结构化输出需要完整 JSON，不适合流式）

## Technical Approach

### 文件结构
```
projects/09-structured-output/
├── main.py              # CLI 入口（--compare/--demo/--interactive）
├── schemas.py           # Pydantic schema 定义（4 层难度）
├── knowledge_base.py    # 游戏工作室虚构知识库
├── extractor.py         # 核心提取逻辑（3 种模式 + 重试）
├── display.py           # ANSI 着色展示
├── notes.md             # 踩坑记录
├── README.md            # 项目说明
├── requirements.txt     # 依赖
└── .env.example         # 环境变量模板
```

### 核心设计
- `extractor.py` 暴露统一接口 `extract(query, schema_class, mode)` → `(result, metadata)`
- metadata 包含：retries、is_valid、errors、raw_output
- 3 种 mode 内部实现不同的 API 调用方式，但对外接口一致
- 重试循环在 extractor 内部完成，外部只看最终结果

## Decision (ADR-lite)

**Context**: 需要选择结构化输出的演示场景和技术覆盖范围
**Decision**: 实体提取场景 + 游戏工作室知识库 + 3 模式 × 4 难度全矩阵对比
**Consequences**: 学习覆盖面完整（强制/弱/无约束），对比直观，但实现量较大（12 组组合）。schema 模块可复用给后续项目。
