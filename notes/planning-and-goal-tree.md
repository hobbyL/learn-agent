# 任务规划与目标树（Planning & Goal Tree）

ReAct 让 Agent"边想边做"，Reflexion 让 Agent"做错再改"，但两者都是
**单任务、线性推进**。当目标复杂到需要"先想清楚整体步骤、按依赖顺序推进、
局部出错只补局部"时，就进入了任务规划（Planning）的范畴。

本主题聚焦 **Plan → Execute → Re-plan** 双层认知架构：外层规划器把目标拆成
子任务 DAG，内层执行器逐个完成叶子任务，失败时只重规划受影响子树。

---

## 核心思想

### 为什么需要"先规划再执行"

单步推理（ReAct）在长程任务上有两个硬伤：

- **上下文漂移**：步骤一多，LLM 容易忘记全局目标，陷入局部最优或原地打转。
- **无法表达依赖**：ReAct 是线性的"想一步做一步"，无法显式表达"任务 C 必须
  等 A 和 B 都完成才能开始"这类跨分支依赖。

规划把"想清楚整体结构"和"逐步执行"解耦：

```
Plan（规划器）     一次性/增量产出目标树 DAG，明确依赖关系
   ↓
Execute（执行器）  按拓扑序取可执行叶子，用内层 ReAct 完成
   ↓
Re-plan（重规划）  某叶子失败 → 只重规划受影响子树，保留已完成成果
```

### 三种规划时机

| 模式 | 何时规划 | 优点 | 缺点 |
|------|---------|------|------|
| **初始全计划** | 一次性生成完整目标树 | 全局可视、便于展示 | 现实与计划偏差时僵硬 |
| **纯动态规划** | 每步临时决定下一步 | 灵活适应 | 无全局视图，难可视化 |
| **混合模式** | 初始全计划 + 执行中按需展开 | 兼顾全局与灵活 | 实现复杂度略高 |

本项目采用**混合模式**：先让 LLM 用 json_schema 强制模式产出完整 DAG，
执行中若发现某叶子过粗，再动态展开成更细的子树。

---

## 目标树数据结构：扁平节点 + depends_on

### 为什么不用嵌套树

直觉上目标树是"父任务包含子任务"的嵌套结构，但嵌套树只能表达**父子层级**，
无法表达**跨分支依赖**（如 t5 同时依赖 t2 和 t3，而 t2、t3 属于不同父节点）。

且 OpenAI Structured Outputs 的 strict 模式对递归/深层嵌套 schema 支持有限，
`$defs` 会迅速膨胀。

**解法**：用扁平的 SubTask 列表，每个节点带 `depends_on: list[str]`，
靠 id 引用还原完整 DAG。这既能表达任意跨分支依赖，又和拓扑排序天然契合。

```python
class SubTask(BaseModel):
    id: str                    # 't1'、't2'…全局唯一
    name: str
    description: str
    depends_on: list[str]      # 前置子任务 id（空列表=无依赖）
    target_module: str         # 关联模块/资源，无则填'无'
    estimated_steps: int
```

注意 strict 模式不支持可选字段，所以 `target_module` 用占位串 `'无'`
而非 `None`，`depends_on` 用空列表而非省略。

---

## DAG 拓扑排序 + 环检测（Kahn 算法）

拓扑排序回答"按什么顺序执行才能满足所有依赖"，同时天然检测环
（有环则无法排序，说明依赖设计矛盾）。

```python
def topological_order(nodes):
    # 1. 统计入度（每个节点有多少未处理的前置依赖）
    in_degree = {tid: 0 for tid in nodes}
    successors = {tid: [] for tid in nodes}
    for tid, node in nodes.items():
        for dep in node.depends_on:
            if dep in nodes:              # 忽略悬空依赖，避免崩溃
                in_degree[tid] += 1
                successors[dep].append(tid)

    # 2. 入度为 0 的入队（保持插入顺序，展示更直观）
    queue = deque(tid for tid in nodes if in_degree[tid] == 0)
    order = []
    while queue:
        tid = queue.popleft()
        order.append(tid)
        for succ in successors[tid]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # 3. 排出的节点数 < 总数 → 存在环
    if len(order) != len(nodes):
        remaining = [tid for tid in nodes if tid not in set(order)]
        raise ValueError(f"循环依赖：{remaining}")
    return order
```

**要点**：
- **悬空依赖不阻塞**：动态展开/重规划过程可能临时出现指向不存在节点的引用，
  忽略它们而非崩溃，让流程更鲁棒。
- **可执行任务筛选**：不是取拓扑序第一个，而是取"依赖全部 DONE（或 SKIPPED）
  且自身 PENDING"的节点集合，再按拓扑序优先处理靠前的。

---

## 局部重规划：子树替换与依赖重定向

全局重规划（失败就整个重来）简单但浪费——已完成的工作全丢了。
局部重规划只作废受影响的部分，是本主题最有价值也最难的一环。

### 三步走

```python
def replace_subtree(affected_ids, replacements):
    # 1. 受影响的旧节点标记 SKIPPED（保留在图里供展示"被替换"轨迹）
    for tid in affected_ids:
        nodes[tid].status = SKIPPED

    # 2. 插入替换节点（新 id 用 r1、r2… 避免冲突）
    new_ids = [insert(st) for st in replacements]

    # 3. 依赖重定向：下游原本依赖"被跳过节点"的，改为依赖新替换节点
    #    否则下游会永远等一个已 SKIPPED 的节点
    for node in nodes.values():
        if any(dep in affected_ids for dep in node.depends_on):
            node.depends_on = [d for d in node.depends_on if d not in affected_ids]
            node.depends_on.extend(new_ids)
```

### 两个关键设计

- **SKIPPED 而非删除**：被替换的旧节点不从图中删除，而是标记 SKIPPED。
  好处是可视化能展示"这个任务失败后被哪些新任务替换"的完整轨迹；
  同时 `all_done()` 判定要跳过 SKIPPED，否则被替换的旧任务会永远卡住完成判定。
- **影响范围识别**：让 LLM 给出 `affected_task_ids`，但代码要兜底把失败任务
  自身也加进去（防 LLM 漏列）。至少包含失败任务，有强下游依赖的一并列入。

### 把"部分完成状态"编码给 LLM

重规划的前提是 LLM 看清"现在到哪了"。把目标树当前状态编码成文本注入 prompt：

```
进度：完成 3/7，失败 1，待办 3，跳过 0
- [done]    t1 采集钛矿×6 (依赖：无)
- [done]    t2 采集碳纤维×4 (依赖：无)
- [failed]  t3 建造居住舱 (依赖：t1、t2)
- [pending] t4 建造实验室 (依赖：t3)
...
```

这样 LLM 才知道哪些资源已备齐、哪些前置已完成，避免重规划时重复已做的工作。

---

## LLM 驱动执行：用收尾工具判定成败

内层执行器给每个叶子任务跑一轮 ReAct（Function Calling）。关键问题：
**外层规划器怎么知道这个叶子成功还是失败？**

### 不要解析自然语言

如果靠关键词/正则去猜 LLM 回复里的"完成了""好像失败了"，极不可靠——
自然语言充满歧义。

### 用结构化收尾工具

额外给 LLM 一个 `report_result(success: bool, reason: str)` 工具，
约定它**必须调用它来收尾**：

```python
REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "report_result",
        "parameters": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "reason": {"type": "string"},   # 失败原因直接喂给重规划器
            },
            "required": ["success", "reason"],
        },
    },
}
```

- `success` 是结构化 bool，外层无需猜。
- `reason` 字段失败时直接就是给重规划 LLM 的失败原因，格式统一。
- 调 report_result 前 LLM 必须明确判断任务是否真完成，强制"不要假装成功"。

**兜底**：若 LLM 没调 report_result 而是自然语言收尾，解析回复里的失败词
（"失败""无法完成""不足"…）判成败——但这只是保险，正常路径都走收尾工具。

---

## 失败设计：让失败可解释、可绕过

Re-planning 只有在"失败原因清晰、且能被新计划绕过"时才有演示价值。
因此工具层的失败要以**确定性条件失败**为主：

| 失败类型 | 触发条件 | LLM 应有的重规划对策 |
|---------|---------|---------------------|
| 资源不足 | 建造模块时库存 < 需求 | 先插入采集资源子任务，建造依赖它们 |
| 前置未完成 | 建造模块时前置模块未建 | 先插入建造前置模块的子任务 |
| 环境禁止 | 太阳风暴期做舱外作业 | 插入"等待/确认环境"子任务或改序 |
| 设备不可用 | 所需设备故障 | 插入修复子任务或改用替代设备 |

少量随机失败（采集难度过高）作点缀，用固定随机种子保证 demo 可复现。
每个失败都返回以"失败："开头的清晰中文错误串，让 LLM 一眼看懂症结。

---

## 双层结构对照

| 项目 | 外层循环 | 内层循环 | 学习重点 |
|------|---------|---------|---------|
| 04-reflexion | Reflexion（评估→反思→重试） | ReAct | 从失败中学习、经验累积 |
| 10-planning | Planning（规划→执行→重规划） | ReAct | 任务分解、依赖管理、局部修复 |

两者都是"外层认知循环 + 内层 ReAct 执行"，但外层的语义不同：
Reflexion 是"同一任务反复试直到对"，Planning 是"把大任务拆成 DAG 分而治之"。

---

## 踩坑记录

### 1. ANSI 着色破坏 ASCII 树对齐

**问题**：给树节点上色后，用于对齐的缩进/连接符列错乱。

**原因**：ANSI 转义码（`\033[32m` 等）会被计入字符串长度，
但终端渲染时不占宽度，导致 `f"{colored:^20}"` 这类对齐失效。

**解决**：对齐用的缩进和 box drawing 字符（`│ ├─ └─`）全部用纯文本先排好版，
颜色码只在最后拼接到已定宽的文本两侧，不参与任何宽度计算。

### 2. 压平的 DAG 如何画成树

**问题**：DAG 不是严格的树（一个节点可能有多个前置），无法直接画父子边。

**解决**：按拓扑序压平，用"最长依赖链长度"作为 depth 决定缩进，给出层级直觉；
真正的跨分支依赖用每行后面的 `← t1, t2` 箭头标注补全。这是"树形直觉 +
依赖标注"的折中，而非严格的树渲染。

### 3. 动态展开导致 parent 状态回退

**问题**：某叶子执行后要动态展开成更细子任务，展开后 parent 该是什么状态？

**解决**：把 parent 变成"汇聚点"——新子任务先执行，parent 的 depends_on
追加这些新子任务 id，parent 从 READY/RUNNING **回退为 PENDING**，
等新子任务全 DONE 后才重新可执行。

### 4. json_schema 强制模式复用 09 的经验

规划的三个动作（生成/重规划/展开）全走 json_schema 强制模式，
直接复用 09 的 `get_json_schema()` + `_enforce_strict_schema()`。
目标树的 id/depends_on 引用必须精确，强制模式把结构约束交给 API，
prompt 只需讲清"依赖语义"，让 LLM 专注"怎么拆"而非"格式对不对"。

### 5. 无限循环的多重兜底

规划-执行-重规划循环有多个可能卡死的点，需要分层兜底：
- `all_done()` 全完成正常退出
- `max_replans`（默认 3）限制重规划次数
- 无可执行任务但未全完成 → safeguard 退出（被失败/跳过卡住）
- `max_total_iterations`（200）总迭代上限，最后一道防线

---

## 一句话总结

任务规划的本质是**把"想清楚"和"做"解耦**：用 DAG 显式表达依赖，
用拓扑排序保证顺序，用局部重规划让"一处出错只修一处"。
LLM 负责"怎么拆"和"失败怎么补"，代码负责"依赖追踪"和"状态管理"——
职责分明，才能在长程复杂任务上稳定推进。

---

**最后更新**：2026-07-06  
**来源项目**：10-planning-and-goal-tree
