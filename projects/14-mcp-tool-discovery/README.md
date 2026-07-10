# 14-mcp-tool-discovery · MCP 动态工具发现

## 项目目标

理解 MCP（Model Context Protocol）的核心价值：**运行时动态工具发现 vs 静态工具注册**。通过三阶段对比演示，展示 MCP 如何让 Agent 在不改代码的情况下获得新能力。

## 场景：星际探索指挥中心

多服务架构知识库，由三个独立 MCP Server 提供数据：

| Server | 角色 | 工具 | 传输 |
|--------|------|------|------|
| A 星图数据库 | 星系/星球/航线查询 | `search_stars` · `lookup_star_info` | stdio |
| B 舰队管理 | 飞船/船员/任务查询 | `search_ships` · `lookup_ship_info` | stdio |
| C 紧急通讯 | 通讯记录/紧急消息 | `search_communications` · `get_comm_detail` · `send_emergency_message` | stdio（动态加载） |

## 三阶段 Demo

```
阶段 1: 静态基线      → Agent 用硬编码 TOOLS_SCHEMA（4 个工具）
阶段 2: MCP 动态发现  → Agent 连接 Server A+B，list_tools() 发现 4 个工具
阶段 3: 运行时热加载  → Server C 上线，Agent 自动获得 3 个新工具（共 7 个）
```

| 维度 | 静态注册 | MCP 动态 | MCP 热加载 |
|------|---------|---------|-----------|
| 工具来源 | 代码硬编码 | `list_tools()` | `list_tools()` 刷新 |
| 工具数 | 4 | 4 | 7（+3） |
| 新增工具 | 改代码 + 重启 | 连接新 Server | 无需重启 |

## 运行

```bash
# 安装依赖
pip install mcp openai python-dotenv

# 配置 .env（和前面项目一样）
# OPENAI_API_KEY=...
# OPENAI_BASE_URL=...
# OPENAI_MODEL=...

# 三阶段完整演示
python main.py --demo

# 交互模式（连接全部 Server）
python main.py --interactive
```

## 文件结构

```
├── knowledge_base.py      # 星际探索指挥中心数据（星图 + 舰队 + 通讯）
├── server_starmap.py      # MCP Server A: 星图数据库（@mcp.tool + stdio）
├── server_fleet.py        # MCP Server B: 舰队管理（@mcp.tool + stdio）
├── server_comms.py        # MCP Server C: 紧急通讯（动态加载）
├── mcp_client.py          # MCP Client: 多 Server 连接 + 工具聚合 + Schema 转换
├── agent_static.py        # 静态工具 Agent（硬编码 TOOLS_SCHEMA，基线对照）
├── agent_mcp.py           # MCP 动态工具 Agent（list_tools → Function Calling）
├── display.py             # ANSI 着色展示 + 对比表格
├── main.py                # CLI 入口：--demo / --interactive
├── README.md              # 本文件
└── notes.md               # 开发笔记
```

## 核心知识点

1. **MCP Server 定义**：`FastMCP("name")` + `@mcp.tool()` 装饰器，函数签名自动生成 JSON Schema
2. **MCP Client 连接**：`stdio_client(StdioServerParameters(...))` + `ClientSession` 初始化协议
3. **工具发现**：`session.list_tools()` 返回工具列表（name + description + inputSchema）
4. **Schema 转换**：MCP `inputSchema` → OpenAI Function Calling `parameters`（结构几乎一致）
5. **工具路由**：Client 维护 `tool_name → server_name` 映射，`call_tool()` 自动路由
6. **生命周期管理**：`AsyncExitStack` 管理多个 async context manager，避免 anyio task scope 问题
7. **热加载**：新 Server 连接后 `get_openai_tools()` 自动包含新工具，Agent 代码零修改
