# 14-mcp-tool-discovery：MCP 动态工具发现

## Goal

通过实现完整的 MCP Server + Client + Agent 系统，理解 MCP 协议的核心价值：**运行时动态工具发现 vs 静态工具注册**。对比前面项目中的硬编码工具列表（03/12），体验 MCP 带来的"即插即用"工具生态。

## Background

前面 13 个项目中，工具始终是静态注册的：
- 项目 03：`TOOLS` 字典 + `TOOLS_SCHEMA` 手写 JSON Schema
- 项目 12：`@tool` 装饰器 + `bind_tools()` 编译时绑定

MCP（Model Context Protocol）改变这个模式：
- Server 独立进程暴露工具，Client 通过协议发现
- 工具可以运行时增减，无需改 Agent 代码
- 标准化的 tool schema 交换格式

## 场景：星际探索指挥中心

新建多服务架构知识库：

- **MCP Server A（星图数据库）**：查星系、星球、距离、环境数据
- **MCP Server B（舰队管理）**：查飞船、燃料、船员、任务状态
- **MCP Server C（紧急通讯）**：运行中动态加载，发送紧急消息、查通讯记录

Agent 启动时只知道 A + B，运行中 C 上线，Agent 自动发现新工具并使用。

## 技术方案

### 传输方式
- Server A + B：**stdio** 传输（子进程通信，MCP 最核心最实用的方式）
- Server C：运行时**动态加载**（演示 `list_tools()` 结果变化）
- 不做 SSE — 协议层无区别，增加 HTTP 复杂度但学习价值低

### Agent 集成
- 只做**手写 Agent + MCP Client**
- Agent ReAct 循环里直接调 `session.call_tool()`
- 工具列表从 `session.list_tools()` 动态获取后转成 OpenAI Function Calling schema
- 不做 LangGraph 版（项目 12 已充分覆盖，本项目聚焦 MCP 协议本身）

### 演示三阶段

| 阶段 | 描述 | 展示要点 |
|------|------|---------|
| 1. 静态基线 | Agent 用硬编码 TOOLS_SCHEMA | 工具来源 = 代码里写死 |
| 2. MCP 动态发现 | Agent 连接 Server A + B，list_tools() | 工具来源 = 运行时协议发现 |
| 3. 运行时热加载 | Server C 上线，Agent 重新发现 | 无需改代码，自动获得新能力 |

每阶段回答对应问题，最后输出对比汇总表。

## 文件结构

```
projects/14-mcp-tool-discovery/
├── knowledge_base.py      # 星际探索指挥中心数据（星图 + 舰队 + 通讯）
├── server_starmap.py      # MCP Server A: 星图数据库（stdio）
├── server_fleet.py        # MCP Server B: 舰队管理（stdio）
├── server_comms.py        # MCP Server C: 紧急通讯（动态加载）
├── mcp_client.py          # MCP Client: 多 Server 连接 + 工具聚合 + schema 转换
├── agent_static.py        # 静态工具 Agent（基线，硬编码 TOOLS_SCHEMA）
├── agent_mcp.py           # MCP 动态工具 Agent（list_tools → Function Calling）
├── display.py             # ANSI 着色展示 + 对比表格
├── main.py                # CLI: --demo / --interactive
├── README.md
└── notes.md
```

## Requirements

1. 3 个独立 MCP Server，各自暴露 2-3 个 `@mcp.tool()` 工具
2. MCP Client 聚合多个 Server 的工具列表，转换为 OpenAI Function Calling schema
3. 静态 Agent（agent_static.py）使用硬编码工具，作为对比基线
4. MCP Agent（agent_mcp.py）通过 MCP Client 动态获取工具
5. 三阶段 demo：静态基线 → MCP 动态发现 → 运行时热加载
6. 每阶段展示：当前可用工具列表 + 工具来源 + 问答结果
7. 最终输出对比汇总表

## Acceptance Criteria

- [ ] 3 个 MCP Server 可独立运行，各暴露 2-3 个工具
- [ ] MCP Client 能 stdio 连接 Server A/B，list_tools() 返回正确工具列表
- [ ] MCP tool schema → OpenAI Function Calling schema 转换正确
- [ ] agent_static 用硬编码工具回答问题
- [ ] agent_mcp 用 MCP 动态发现的工具回答同样问题，结果一致
- [ ] Server C 动态加载后，agent_mcp 能发现新工具并使用
- [ ] 三阶段 demo 端到端跑通，ANSI 着色展示 + 对比表格输出
- [ ] `python main.py --demo` 一键运行完整演示
- [ ] README.md + notes.md + notes/mcp-tool-discovery.md（根目录知识笔记）
