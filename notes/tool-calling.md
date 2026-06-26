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

### 4. 工具的 error 信息会影响 Agent 的循环行为

工具的错误返回不只是给人看的日志，**它会被喂回 LLM，直接影响 Agent 下一步的决策**。

**实验**：让 Agent "查不存在的城市'阿斯加德'天气，再转华氏度"。
- `get_weather` 返回 `{"error": "未找到城市：Asgard。请检查城市名称拼写，建议使用英文名称"}`
- LLM 读懂这是"城市不存在"（本质性失败），判断重试无意义，于是**主动终止任务链**，没有去做不可能的第二步（转换一个不存在的温度），而是优雅地向用户解释。

**关键**：LLM 能做出正确决策，是因为错误信息明确区分了失败类型。

- ✅ 好的错误：`"未找到城市：Asgard，拼写有误"` → LLM 知道不可重试，停止
- ❌ 坏的错误：`{"error": "request failed"}` 或直接抛 500 → LLM 可能误判为临时网络问题，反复重试，最终撞上 `max_iterations`

**结论**：设计工具时，错误信息要让 LLM 能区分"可重试"（网络抖动、限流）和"不可重试"（参数错误、资源不存在），这是控制 Agent 循环行为的重要手段。

### 5. 工具链是 LLM 自主串起来的，不是代码写死的

**实验**：输入"今天杭州天气，再把温度从摄氏转华氏"，Agent 自动跑出三轮：
1. `get_weather` → 29.18°C
2. `unit_converter`（把上一步的 29.18 当作输入）→ 84.5°F
3. LLM 综合两步结果给最终回答

代码里**没有任何**"查完天气要转温度"的逻辑——是 LLM 读懂任务后自主分解成两步，并把上一个工具的输出当作下一个工具的输入。`messages` 数量 2→4→6 的增长就是记忆在累积，第 2 轮 LLM 能拿到 29.18 正是因为第 1 轮结果留在了 `messages` 里。

**结论**：这是 Agent 和普通脚本的根本区别——脚本的流程是人写死的，Agent 的流程是 LLM 当场决定的。

### 6. SYSTEM_PROMPT 是 Agent 行为最强的杠杆

**实验**：02 项目里，问"计算 2 的 10 次方"（没有计算器工具），LLM 硬调 `hash_generator`，拿到哈希值后无视结果自己心算出 1024。

**修复**：一行代码逻辑没改，只在 SYSTEM_PROMPT 加了两条规则：
- 【能力边界】：工具覆盖不了时，绝不硬凑工具
- 【工具结果必须被使用】：调了工具就必须用其结果

6 个用例全部验证通过。

**结论**：Agent 行为出偏时，优先调 prompt 而非改代码。SYSTEM_PROMPT 的权重远超你的直觉——它是 LLM 行为最强的控制面。但要记住这是概率性护栏，不是 100% 可靠。

**来源项目**：02-tool-calling

### 7. JSON Schema 是通用协议，Pydantic 是 Python 的标准实现

所有 LLM 的工具调用机制（OpenAI、Anthropic、LangChain、CrewAI、LlamaIndex）底层都是 JSON Schema 协议。框架差异只在"怎么生成这份 Schema"：

- 手搓：inspect.signature → 类型映射 → 拼 JSON（理解原理）
- Pydantic：BaseModel + model_json_schema() 一行搞定（生产选择）

手搓能覆盖 80% 简单场景（str/int/bool/list/Literal），在复杂类型（Union、嵌套对象）和运行时校验上很快到顶。Pydantic 一步到位。

**结论**：先手搓理解协议本身，再用 Pydantic 避免重复造轮子。两步缺一不可——只手搓会在生产中痛苦，只用 Pydantic 会不理解它背后做了什么。

**来源项目**：02-tool-calling

### 8. 运行时参数校验是 Agent 可靠性的关键防线

Schema 里写的 `"enum": ["hex","rgb","hsl"]` 只是"告诉"LLM 约束，LLM 传了枚举外的值照样能到达工具函数。手搓版全靠每个工具内部 `if` 拦截——分散、不统一、容易遗漏。

Pydantic 的 `model_validate()` 提供了统一的自动校验关卡：
- 枚举非法值 → `literal_error`
- 缺少必填字段 → `missing`
- 类型不对 → 自动宽容转换（`"16"` → `16`），转不了才报错

校验失败的错误信息可以直接喂回 LLM（`role="tool"`），让它自我纠正后重试——这就是"参数校验闭环"。

**结论**：Schema 是"建议"，validate 是"强制"。生产级 Agent 两者都需要。

**来源项目**：02-tool-calling

---

**最后更新**：2026-06-27  
**来源项目**：01-simple-agent, 02-tool-calling
