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

## 从实践中学到的教训

### 1. 工具 description 直接影响 LLM 的调用决策

LLM 靠工具的 `description` 字段判断：
- 这个工具是做什么的
- 什么时候该调用它
- 什么情况下不需要调用

**反面案例**：`get_current_time` 最初的描述只说"获取当前时间"，没有强调"相对日期计算时必须调用"。结果 LLM 在历史中已有日期时选择不调工具，自行推算星期，出现错误。

**结论**：description 要包含"何时必须调用"的明确指令，不能只描述功能。

**补充**：即使 LLM 在历史中已经知道今天日期，也必须在 description 中明确声明"历史有信息也要调工具"——否则 LLM 会做惰性优化，跳过调用。这个问题在 `get_current_time` 和 `date_calculator` 上都复现了。

### 2. LLM 不擅长精确计数，应交给工具

LLM 在以下场景容易出错：
- 星期推算（+1 天是星期几）
- 日期加减（N天后是哪天）
- 精确数字计算（应该用 calculator 工具）

**结论**：凡是需要精确计数或计算的场景，必须调工具，不能让 LLM 自行推理。

### 3. load_dotenv 必须在所有 import 之前调用

Python 模块级代码（如 `_LOG_LEVEL = os.environ.get("LOG_LEVEL")`）在 `import` 时立即执行。
如果 `load_dotenv()` 在 `import` 之后调用，`.env` 中的配置对模块级变量无效。

**正确做法**：
```python
from dotenv import load_dotenv
load_dotenv()           # 第一步

from agent import Agent  # 之后再 import
```

**最后更新**：2026-06-26  
**来源项目**：01-simple-agent
