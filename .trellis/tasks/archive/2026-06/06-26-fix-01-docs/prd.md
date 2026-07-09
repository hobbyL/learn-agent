# 修复 01-simple-agent README 和进度记录中的过时内容

## Goal

修复文档中 4 处与实际代码/进度不符的内容，使文档准确反映当前状态。

## Requirements

### 1. `projects/01-simple-agent/README.md` — 实现步骤勾选

`第 1 步：环境搭建` 下三项改为已完成：
```
- [x] 创建 Python 虚拟环境
- [x] 安装依赖
- [x] 配置 API Key（OPENAI_API_KEY、OPENWEATHERMAP_API_KEY）
```

`第 4 步：整合和测试` 下两项改为已完成，并更新测试用例数量：
```
- [x] 运行并测试 6 个测试用例
- [x] 记录学习笔记（notes.md）
```

### 2. `projects/01-simple-agent/README.md` — 项目结构描述

```
├── tools.py  # 5 个工具函数 + OpenAI Function Calling Schema
```
改为：
```
├── tools.py  # 6 个工具函数 + OpenAI Function Calling Schema
```

### 3. `projects/01-simple-agent/README.md` — 第 3 步工具列表

```
- [x] 实现 5 个工具（计算器、时间、单位换算、文本统计、天气）
```
改为：
```
- [x] 实现 6 个工具（计算器、时间、日期计算、单位换算、文本统计、天气）
```

### 4. `progress/2026-06.md` — 06-26 补充今天实际完成的内容

在"今日完成"列表中追加：
```
- ✅ 新增 `date_calculator` 工具（处理昨天/前天/明天/后天等相对日期）
- ✅ 修复 date_calculator 在多轮对话历史中被 LLM 跳过的 bug
- ✅ 将 .trellis/ .claude/ .codex/ .agents/ AGENTS.md 加入 .gitignore（本地工具目录不提交）
```

在"学到的内容"中追加：
```
- **LLM 惰性优化是双刃剑**：LLM 在历史中已有信息时会跳过工具调用，同一 bug 在 get_current_time 和 date_calculator 上都复现 → description 必须明确"历史有信息也要调工具"
```

在"遇到的问题"中追加：
```
- date_calculator 在多轮对话后被跳过 → 根因：LLM 在历史有日期时做惰性优化 → 修复：description 追加强制约束
```

同时更新统计部分：
- 代码行数从"约 750 行"改为"约 850 行"（新增了 date_calculator）

## Acceptance Criteria

- [ ] README.md 实现步骤中无未勾选的 `[ ]`（项目已完成）
- [ ] README.md 工具数量统一为 6 个
- [ ] progress/2026-06.md 的 06-26 包含 date_calculator 新增和 bug 修复记录

## Out of Scope

- 不修改代码文件（tools.py / agent.py / main.py）
- 不修改 notes/tool-calling.md（已是最新）
- 不修改 projects/01-simple-agent/notes.md（已是最新）
