# 工具调用（Tool Calling）

工具调用是 Agent 与外部世界交互的核心机制。

---

## 什么是工具调用？

**工具（Tool）** 是 Agent 可以调用的外部功能，让 Agent 能够：
- 获取实时信息（搜索、天气、数据库查询）
- 执行操作（发送邮件、创建文件、调用 API）
- 执行计算（数学运算、数据处理）

---

## 工具调用的流程

```
1. 工具定义    → 告诉 LLM 有哪些工具可用
2. LLM 推理    → LLM 决定要调用哪个工具
3. 参数提取    → 从 LLM 输出中提取工具名称和参数
4. 工具执行    → 实际调用工具函数
5. 结果反馈    → 将工具执行结果返回给 LLM
6. 继续推理    → LLM 根据结果决定下一步
```

---

## 工具定义规范

工具定义通常使用 **JSON Schema** 格式：

```json
{
  "name": "get_weather",
  "description": "获取指定城市的当前天气信息",
  "parameters": {
    "type": "object",
    "properties": {
      "city": {
        "type": "string",
        "description": "城市名称，例如：北京、上海"
      },
      "unit": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "description": "温度单位",
        "default": "celsius"
      }
    },
    "required": ["city"]
  }
}
```

---

## 实现要点

### 1. 工具注册

```python
class ToolRegistry:
    def __init__(self):
        self.tools = {}
    
    def register(self, name, func, schema):
        self.tools[name] = {
            "function": func,
            "schema": schema
        }
    
    def get_tool(self, name):
        return self.tools.get(name)
```

### 2. 解析工具调用

从 LLM 输出中提取工具调用信息：

```
Action: get_weather(city="北京", unit="celsius")
```

需要解析出：
- 工具名称：`get_weather`
- 参数：`{"city": "北京", "unit": "celsius"}`

### 3. 执行工具

```python
def execute_tool(tool_name, params):
    tool = registry.get_tool(tool_name)
    if not tool:
        return {"error": f"Tool {tool_name} not found"}
    
    try:
        result = tool["function"](**params)
        return result
    except Exception as e:
        return {"error": str(e)}
```

### 4. 错误处理

- 工具不存在
- 参数缺失或类型错误
- 执行超时
- 网络错误

---

## 常见工具类型

### 1. 信息检索工具
- 搜索引擎
- Wikipedia 查询
- 数据库查询

### 2. 计算工具
- 数学计算器
- 单位转换
- 日期时间处理

### 3. 文件操作工具
- 读取文件
- 写入文件
- 列出目录

### 4. API 调用工具
- 天气 API
- 地图 API
- 第三方服务

---

## 进阶话题

### 1. 并行工具调用

当多个工具调用互不依赖时，可以并行执行：

```python
import asyncio

async def parallel_tool_calls(calls):
    tasks = [execute_tool(call) for call in calls]
    results = await asyncio.gather(*tasks)
    return results
```

### 2. 工具链

一个工具的输出作为另一个工具的输入：

```
get_user_location() → get_weather(location) → translate(weather_info)
```

### 3. 工具权限控制

限制 Agent 能调用哪些工具：

```python
class PermissionController:
    def can_execute(self, tool_name, user_role):
        # 实现权限检查逻辑
        pass
```

---

## 最佳实践

1. **清晰的工具描述**：让 LLM 能准确理解工具的用途
2. **完整的参数说明**：包括类型、默认值、示例
3. **错误信息友好**：返回易于理解的错误信息
4. **超时保护**：设置合理的超时时间
5. **日志记录**：记录所有工具调用，便于调试

---

**最后更新**：2026-06-25  
**来源项目**：无（初始笔记）
