# 构建第一个简单 Agent：手写核心循环

## Goal

用纯 Python 手写一个最基础的 AI Agent（不依赖任何 Agent 框架），调用 Claude API，理解 Agent 的感知-推理-行动核心循环，并支持若干简单工具调用（计算器、时间查询等）。这是学习 Agent 的第一个实践项目，重点是理解底层原理而非实用性。

## What I already know

* 项目目录：`projects/01-simple-agent/`
* 使用 OpenAI API（openai SDK）
* 不使用任何 Agent 框架（LangChain、LlamaIndex 等）
* 需要实现：工具定义、工具注册、工具调用、Agent 核心循环
* 已有框架文件：`.env.example`、`requirements.txt`（含 anthropic、python-dotenv）

## Assumptions

* 以命令行交互方式运行（非 Web UI）
* 工具调用使用 OpenAI 原生 tool use（function calling）
* 多轮对话模式，维护 messages 历史，输入 "exit" 退出
* 学习目的优先，代码可读性 > 代码简洁性

## Open Questions

（已全部解决）

## Requirements

* 用纯 Python 实现 Agent，不依赖任何 Agent 框架
* 使用 OpenAI API（openai SDK），原生 Function Calling 机制
* 多轮对话模式，维护 messages 历史，输入 "exit" 退出
* 实现 5 个工具：
  1. `calculator` — 数学表达式计算
  2. `get_current_time` — 查询当前日期和时间
  3. `unit_converter` — 单位换算（温度、长度）
  4. `text_stats` — 统计文本字数、字符数
  5. `get_weather` — 真实天气查询（OpenWeatherMap API）
* 代码有清晰注释，适合学习

## Acceptance Criteria

* [ ] Agent 能正确处理用户输入并返回合理结果
* [ ] 5 个工具均可被正确调用
* [ ] 多轮对话中 Agent 能记住上下文
* [ ] 天气工具调用真实 OpenWeatherMap API
* [ ] 基本错误处理（工具失败、API 错误）
* [ ] 能演示以下测试用例：
  * [ ] "23 * 47 等于多少？"
  * [ ] "现在几点了？"
  * [ ] "100摄氏度等于多少华氏度？"
  * [ ] "帮我统计这句话有多少个字：人工智能改变世界"
  * [ ] "北京今天天气怎么样？"

## Definition of Done

* 代码可在本地运行
* 附有清晰的注释，适合学习
* `notes.md` 记录了实现过程中的关键发现

## Out of Scope

* Web UI
* 持久化记忆
* 多轮对话历史管理
* 生产级错误处理
* 单元测试

## Technical Notes

* OpenAI Function Calling 文档：https://platform.openai.com/docs/guides/function-calling
* OpenWeatherMap 免费 API：https://openweathermap.org/api（需注册获取 key）
* 项目结构：main.py / agent.py / tools.py
* `.env.example` 需新增 `OPENWEATHERMAP_API_KEY`

## Decision (ADR-lite)

**Context**: 工具调用方式、交互模式、工具集的选择
**Decision**:
- OpenAI 原生 Function Calling（而非手动解析 ReAct 文本）
- 多轮对话，messages 列表维护历史
- 5 个工具：计算器、时间、单位换算、文本统计、真实天气
**Consequences**: 代码接近生产实践，学习价值高；天气工具需要额外注册 API key

## Out of Scope

* Web UI
* 持久化记忆（跨会话）
* 单元测试
* 生产级错误处理与重试
* 超过 5 个工具
