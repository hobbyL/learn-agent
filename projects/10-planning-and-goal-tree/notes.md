# 10-planning-and-goal-tree 踩坑记录

本项目实现"Plan → Execute → Re-plan"双层认知架构，最难的不是 LLM 调用，而是
**DAG 状态管理**与**局部重规划的影响范围分析**。以下按"问题 → 原因 → 解决方案"
记录关键踩坑点。

---

## 1. DAG 拓扑排序 + 环检测（Kahn 算法）

**问题**：LLM 生成的目标树 `depends_on` 可能写出循环依赖（t1 依赖 t2、t2 又依赖 t1），
若不检测就直接执行，`get_ready_tasks()` 会永远返回空，主循环卡死。

**原因**：LLM 对"依赖方向"的理解偶尔出错，尤其是重规划插入新节点时，容易把
"前置"和"后继"写反，形成环。

**解决方案**：用 Kahn 算法做拓扑排序，天然带环检测：
```python
# 统计入度 → 入度 0 入队 → 出队并削减后继入度 → 后继归零入队
# 若最终排序节点数 < 总节点数，剩余节点即处于环中
if len(order) != len(self._nodes):
    remaining = [tid for tid in self._nodes if tid not in set(order)]
    raise ValueError(f"目标树存在循环依赖，涉及节点：{remaining}")
```
关键决策：**在 `GoalTree.__init__`、`add_subtasks`、`replace_subtree` 之后都调一次
`topological_order()`**，让环在"引入的那一刻"就暴露，而不是等到执行时才卡死。

**额外踩坑**：`depends_on` 里可能指向已被移除的节点（悬空依赖）。拓扑排序时必须
`if dep in self._nodes` 过滤，否则悬空依赖会让入度永远无法归零，被误判成环。

---

## 2. 局部重规划的子树替换与依赖重定向

**问题**：某任务 t3 失败，用 r1/r2 替换后，原本"依赖 t3"的下游任务 t4 怎么办？
如果不处理，t4 会永远等一个已被作废（SKIPPED）的 t3，卡死流程。

**原因**：局部重规划的本质是"换掉一段子树"，但下游节点的依赖边还指向旧节点。
DAG 的边必须同步重定向，否则图的连通性被破坏。

**解决方案**：`replace_subtree` 分三步：
1. 受影响旧节点标记 `SKIPPED`（保留在图里供展示"被替换"轨迹，但不计入 `all_done`、不阻塞后继）
2. 插入替换节点（id 用 r1/r2 避免冲突）
3. **下游依赖重定向**：把指向"被跳过节点"的依赖，改为依赖"全部新替换任务"
```python
if any(dep in affected_set for dep in node.depends_on):
    node.depends_on = [d for d in node.depends_on if d not in affected_set]
    node.depends_on.extend(new_ids)  # 简化策略：依赖所有新任务，保证在其之后
```

**权衡**：这里用了"下游依赖所有新替换任务"的简化策略，而非精确匹配"哪个新任务
产出了下游需要的东西"。精确匹配需要 LLM 额外标注产物映射，对教学项目过重，
简化策略保证了"下游一定在替换任务之后执行"这一正确性底线。

**关于 SKIPPED 不计入完成判定**：`all_done()` 必须跳过 SKIPPED 节点，否则被替换的
旧任务永远不是 DONE，`all_done` 永远为 False。同理 `_dependencies_satisfied` 把
SKIPPED 前置视为"不阻塞"，否则下游会无限等待。

---

## 3. LLM 驱动执行用 report_result 收尾工具判定成败

**问题**：外层规划器需要一个**可靠的 success/failure 信号**来决定"标记 DONE 还是触发
重规划"。如果靠解析执行器 LLM 的自然语言（"我觉得完成了""看起来资源不太够"），
判定会充满歧义。

**原因**：自然语言的"成功"表达千变万化，关键词匹配（出现"失败"就判失败）极易误判——
比如"没有失败，顺利建成"里也含"失败"二字。

**解决方案**：给执行器 LLM 一个额外的 `report_result(success, reason)` 收尾工具，
prompt 里强制约定"完成或确认无法完成后，必须调用它收尾"：
```python
if tool_name == "report_result":
    result["success"] = bool(tool_args.get("success", False))
    result["failure_reason"] = None if success else reason
    return result  # success 是结构化 bool，外层无需猜
```
好处三点：① success 是结构化 bool，零歧义；② reason 字段直接就是喂给重规划 LLM 的
失败原因，格式统一；③ 强制 LLM 在收尾前明确判断，呼应"绝不假装成功"的约束。

**兜底**：若 LLM 没调 report_result 而直接自然语言收尾，才退回关键词判定
（出现明确失败词判失败，否则视为成功）——这是下策，只作保险。

---

## 4. 混合规划模式：初始全计划 vs 执行中动态展开的边界

**问题**：既然有初始全计划，为什么还要"动态展开"？两者职责如何划分？会不会重复拆解？

**原因**：初始规划时 LLM 对"某步到底多复杂"的判断可能过粗（把"建造居住舱"当成一步，
实际它包含打印外壳 + 焊接组装 + 密封检测）。但如果一开始就要求 LLM 把每步都拆到最细，
又会让初始计划过于庞大、token 爆炸。

**解决方案**：分层——
- **初始规划**（`generate_plan`）：拆到"采集资源 / 建造模块"的粗粒度，快速给出可视化目标树
- **动态展开**（`expand_subtask`）：**默认关闭**（`enable_expansion=False`），仅在执行后 LLM
  明显发现"这步其实含多个独立步骤"时才展开。判断准则刻意保守（"多数情况 needs_expansion=false"）

**权衡**：动态展开每个成功子任务后要额外调一次 LLM，token 消耗翻倍。因此默认关闭，
`--demo` 想演示时通过 `ENABLE_EXPANSION=true` 打开。这是"完整覆盖混合规划概念"与
"控制 demo token 成本"之间的平衡。

**展开的语义细节**：展开后 parent 变成"汇聚点"——新子任务先执行，parent 依赖它们
（`add_subtasks` 会把 parent 的状态回退为 PENDING）。这样保证"展开出来的细步骤"
在"原粗步骤收尾"之前完成。

---

## 5. json_schema 强制模式复用 09 的经验

**问题**：规划输出的 `depends_on` / `id` 引用必须 100% 精确，自由文本极易产生格式漂移
（漏字段、id 写错、依赖写成名称而非 id）。

**解决方案**：三个规划动作（generate_plan / replan_subtree / expand_subtask）全部走
`json_schema` 强制模式，直接复用 09 的 `get_json_schema()` + `_enforce_strict_schema()`：
```python
response_format={"type": "json_schema", "json_schema": get_json_schema(Plan)}
```
OpenAI 保证输出符合 schema，无需重试。prompt 只需讲清"依赖语义"（depends_on 存的是
前置子任务的 id，不是名称），让 LLM 专注"怎么拆"而非"格式对不对"。

**strict 模式的字段约束**：09 已踩过的坑——所有字段必填、不能有 Optional/默认值语义。
因此 `SubTask.target_module` 无关联时填占位串 `'无'` 而非 `None`，
`SubTaskExpansion.new_subtasks` 不需要展开时填空列表而非省略。

**为什么用扁平节点列表而非嵌套树**：strict 模式下深层嵌套会让 `$defs` 迅速膨胀，
且嵌套树只能表达父子层级，无法表达"t5 同时依赖 t2 和 t3"的跨分支边。扁平的
`SubTask` 列表 + 每个节点的 `depends_on` 能完整还原 DAG，也和 Kahn 拓扑排序天然契合。

---

## 6. ANSI 着色下 ASCII 树的对齐问题

**问题**：给目标树的每一行加了 ANSI 颜色码后，用 `f"{text:^20}"` 之类的对齐格式化会错乱——
颜色码（如 `\033[32m`）被计入字符串长度，导致实际可见宽度和格式化宽度不一致。

**原因**：Python 的字符串宽度计算把 ANSI 转义序列当成普通字符，但终端渲染时它们不占宽度。
这是 09 notes.md 里已记录的老坑。

**解决方案**：**对齐用的缩进/前缀全部用纯文本构成，颜色码只在最后拼接到已排好版的文本两侧**。
树形前缀 `├─ └─ │` 的缩进由 `_tree_prefix(depth, is_last)` 生成纯文本，
颜色只包裹在"图标 + 任务名"这段不参与列对齐的内容上：
```python
prefix = _tree_prefix(depth, is_last)   # 纯文本缩进
print(f"│  {prefix}{color}{icon} {row['id']} {row['name']}{Colors.RESET}...")
```
这样即使颜色码长度不一，缩进也不会错位。

**DAG 压平成树的信息损失**：`depth` 来自"最长依赖链长度"，同一 depth 的节点可能来自
不同分支，缩进只给"层级直觉"而非严格父子边。真正的跨分支依赖靠每行后面的
`← t1, t2` 标注补全，弥补压平树丢失的信息。

---

## 7. display 接线：verbose 职责归一

**问题**：executor 和 planner 内部原本各有 `verbose` 占位打印，planner_agent 也有
`_print_tree_placeholder`。接入 display 后如果都开着 verbose，同一信息会打印两遍。

**解决方案**：把"过程展示"的职责收敛到 display 层，由 planner_agent 统一调度：
- 调 `execute_subtask(..., verbose=False)`，执行细节改由 `display.print_subtask_execution`
  基于返回的 steps 统一渲染，避免 executor 内部占位打印与 display 重复
- 删除 `_print_tree_placeholder`，全部替换为 `display.print_goal_tree`
- planner 的规划进度打印（"规划中…""受影响 N 个"）保留，它是"规划器视角"的简短反馈，
  与 display 的"目标树视角"不重复

**收益**：展示逻辑集中在 display.py，改配色/改布局只动一处；逻辑层（planner_agent）
只管"何时展示什么"，不管"怎么展示"。

---

## 性能与成本观察

- **token 消耗结构**：初始规划 1 次 + 每个子任务 1 轮 ReAct（若干次工具调用）+ 每次失败 1 次重规划。
  子任务数 × ReAct 步数是主要成本，`--demo` 的预设目标控制在 3~4 个核心模块以内
- **动态展开默认关闭**：开启后每个成功子任务额外 1 次 LLM 调用，token 近似翻倍，仅演示时开
- **RANDOM_SEED 复现**：tools 层的"采集难度随机失败"用独立 `Random` 实例，
  设 `RANDOM_SEED` 可让 demo 的失败/重规划序列在多次运行间可复现，便于调试和录屏

---

## 最佳实践小结

1. **DAG 操作后立即校验拓扑序**：构建/展开/替换后都跑一次，让环尽早暴露
2. **SKIPPED 语义要贯穿到底**：完成判定、依赖满足判定都要正确处理 SKIPPED，否则卡死
3. **结构化收尾信号优于自然语言解析**：report_result 让成败判定零歧义
4. **规划全走 json_schema 强制模式**：id/依赖引用容不得格式漂移
5. **展示与逻辑分离**：verbose 职责归一到 display 层，逻辑层只决定"何时展示"
