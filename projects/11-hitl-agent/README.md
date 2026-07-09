# 11 · Human-in-the-Loop Agent

> 场景：明川市 6.8 级地震复合灾害应急指挥中心

## 核心概念

Human-in-the-Loop（HITL）= Agent 在执行**高风险工具调用前主动暂停**，等待人类审批后再决定是否继续。

本项目在标准 ReAct 循环中嵌入 HITL 检查点，使人类指挥官对关键操作保持控制权：

```
Thought → Action →?→ [HITL 检查点]
                       ├── approve   → 执行工具 → Observation → 下一步
                       ├── reject    → 注入替代指令 → LM 重新规划
                       └── provide_info → 注入信息 → LM 重新推理
```

## 架构

```
main.py          CLI 入口（--demo / --interactive）
agent.py         ReAct + HITL 主循环（HITLAgent）
hitl.py          检查点拦截 + 反馈处理（ScriptedHandler / InteractiveHandler）
tools.py         9 个救援工具（rule-based requires_approval 标记）
knowledge_base.py  虚构明川市世界状态 + 灾害恶化机制（tick）
schemas.py       Pydantic 数据模型（HITLRequest / HITLResponse）
display.py       ANSI 终端渲染（黄色 HITL 区 vs 绿色自主区）
scenarios.py     Demo 剧本（5 步：approve + provide_info + reject + approve × 2）
```

## HITL 触发规则

| 工具 | 是否需审批 | 审批类型 |
|------|-----------|---------|
| `dispatch_team` | ✅ | `life_risk`（队员人身安全） |
| `evacuate` | ✅ | `irreversible`（不可逆撤离） |
| `allocate_resource` | ✅ | `resource_conflict`（稀缺资源分配） |
| `release_flood` | ✅ | `irreversible`（泄洪不可逆） |
| `check_situation` | ❌ | — |
| `check_resources` | ❌ | — |
| `query_knowledge` | ❌ | — |
| `repair_infra` | ❌ | — |
| `set_alert_level` | ❌ | — |

## 三层人类反馈

- **approve**：批准执行，Agent 继续
- **reject + 替代指令**：注入否决原因 + 新指令到 messages，LM 重新规划；连续 3 次 → 终止
- **provide_info**：注入补充信息，LM 重新评估后决定是否继续

## 灾害恶化机制

每个 Agent 步骤后调用 `tick()`，使灾情随时间自动恶化：
- 堰塞湖水位：+0.3m / tick（警戒线 45m）
- 东城火灾：+500 ㎡ / tick（超 15000 ㎡ → 加油站爆炸警告）
- 余震：每 3 tick 发生一次，老城区危险建筑 +1
- 市中心医院燃油：-0.5 小时 / tick（≤2 小时 → 紧急警报）

人类拖延有可观测的代价，每次 reject/provide_info 都消耗一个 tick。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 复制并填写 API Key
cp .env.example .env

# Demo 模式（预设 5 步剧本，无人值守）
python main.py --demo

# 交互模式（真实 stdin 输入）
python main.py --interactive
```

## Demo 剧本

| 步骤 | 触发工具 | 反馈类型 | 说明 |
|------|---------|---------|------|
| 1 | `dispatch_team` | approve | 批准搜救犬队前往震中广场 |
| 2 | `evacuate` | provide_info | 指挥官补充撤离路线信息 |
| 3 | `dispatch_team` | reject | 否决——要求先灭火再搜救 |
| 4 | `dispatch_team` | approve | 批准消防队出动 |
| 5 | `allocate_resource` | approve | 批准物资分配 |

## 环境变量

| 变量 | 必填 | 说明 |
|------|-----|------|
| `OPENAI_API_KEY` | ✅ | API 密钥 |
| `OPENAI_BASE_URL` | ❌ | 自定义端点（兼容 OpenAI 格式） |
| `MODEL_NAME` | ❌ | 默认 `gpt-4o-mini` |
| `MAX_STEPS` | ❌ | ReAct 最大步数，默认 15 |
