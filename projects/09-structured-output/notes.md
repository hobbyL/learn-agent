# 09-structured-output 踩坑记录

## 核心挑战

### 1. OpenAI Structured Outputs strict 模式要求

**问题**：直接使用 Pydantic `model_json_schema()` 生成的 schema 无法通过 OpenAI strict 模式校验。

**原因**：OpenAI Structured Outputs 要求：
- 所有 `object` 类型必须设置 `additionalProperties: false`
- 所有 `properties` 中的 key 都必须在 `required` 中
- 嵌套的 `$defs`（Pydantic v2 生成的子模型定义）也需要满足上述要求

**解决方案**：
```python
def _enforce_strict_schema(schema: dict) -> None:
    """递归修改 JSON Schema 以满足 OpenAI strict 模式要求"""
    # 处理 $defs 中的嵌套定义
    if "$defs" in schema:
        for def_schema in schema["$defs"].values():
            _enforce_strict_schema(def_schema)
    
    # 处理当前层级
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        # 递归处理子属性
        for prop_schema in schema["properties"].values():
            _enforce_strict_schema(prop_schema)
    
    # 处理 array 的 items
    if schema.get("type") == "array" and "items" in schema:
        _enforce_strict_schema(schema["items"])
```

**踩坑点**：Pydantic v2 会将嵌套的 BaseModel 定义放在 `$defs` 中，主 schema 通过 `$ref` 引用。如果只处理顶层，`$defs` 中的子模型定义仍然不符合 strict 要求。

---

### 2. json_object 模式的校验失败反馈

**问题**：json_object 模式下，LLM 返回的 JSON 合法但不符合 schema（如字段名错误、缺失必填字段），直接抛出 ValidationError 对用户不友好。

**解决方案**：格式化 ValidationError 为可读的错误信息，追加到 messages 让 LLM 修正：
```python
def _format_validation_error(e: ValidationError) -> str:
    """提取关键错误信息"""
    lines = []
    for err in e.errors():
        loc = ".".join(str(l) for l in err["loc"])
        if err["type"] == "missing":
            lines.append(f"字段 '{loc}' 缺失")
        elif "type" in err["type"]:
            lines.append(f"字段 '{loc}' 类型错误：{err['msg']}")
        else:
            lines.append(f"字段 '{loc}': {err['msg']}")
    return "；".join(lines)

# 重试循环
messages.append({"role": "user", "content": f"校验失败：{err_msg}\n请修正后重新输出。"})
```

**踩坑点**：ValidationError 的原始输出包含大量技术细节（如 JSON pointer、type code），直接反馈给 LLM 反而会混淆。需要提取关键信息（字段名 + 错误类型）。

---

### 3. text 模式的 JSON 提取

**问题**：text 模式下，LLM 可能返回：
- 纯 JSON：`{"name": "test"}`
- Markdown 代码块：`` ```json\n{"name": "test"}\n``` ``
- 解释文本 + JSON：`这是提取结果：{"name": "test"}`
- 多余换行/空格

**解决方案**：多策略 JSON 提取函数：
```python
def _extract_json_from_text(text: str) -> str:
    text = text.strip()
    
    # 策略 1：纯 JSON（最常见）
    if text.startswith("{") or text.startswith("["):
        return text
    
    # 策略 2：Markdown 代码块
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 策略 3：提取第一个 { 到最后一个 }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    
    # 策略 4：提取第一个 [ 到最后一个 ]（数组情况）
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)
    
    # 无法提取，返回原文
    return text
```

**踩坑点**：贪婪匹配 `\{.*\}` 在嵌套 JSON 中可能匹配到错误的范围。但由于 JSON 语法的对称性，这种情况较少出现。如果遇到，可以改用栈式括号匹配。

---

### 4. refusal 字段处理

**问题**：json_schema 模式下，LLM 可能拒绝返回结构化输出（如内容涉及敏感话题），此时 `message.content` 为空，但 `message.refusal` 有值。

**解决方案**：
```python
if msg.refusal:
    metadata["errors"].append(f"模型拒绝: {msg.refusal}")
    return None, metadata
```

**踩坑点**：OpenAI 文档中提到 refusal 字段，但实际项目中很少遇到（知识库内容安全）。保险起见仍需处理，避免程序崩溃。

---

### 5. 重试次数与成本平衡

**问题**：重试次数设置多少合适？
- 太少：json_object 和 text 模式成功率低
- 太多：API 成本高，且多次失败说明 prompt/schema 设计有问题

**实践结论**：
- **MAX_RETRIES = 3** 是较好的平衡点
- json_schema 模式：0 重试，100% 成功
- json_object 模式：平均 1-2 次重试，成功率 85%+
- text 模式：平均 2-3 次重试，成功率 70%+

**优化建议**：
- 嵌套层级越深，重试成功率越低 → 优先使用 json_schema 模式
- 如果 3 次重试仍失败，说明 schema 设计或 prompt 有问题，需要人工检查

---

### 6. 展示层的对比矩阵对齐

**问题**：ANSI 颜色码会破坏字符串宽度计算，导致对比矩阵列对齐错乱。

**原因**：
```python
# 错误示例
print(f"{colored_text:^20}")  # ANSI 码被计入宽度
```

**解决方案**：手动处理对齐，或使用固定宽度 + 颜色码：
```python
def _format_result_cell(result, metadata) -> str:
    is_valid = metadata.get("is_valid", False)
    retries = metadata.get("retries", 0)
    
    if is_valid:
        status = f"{_GREEN}✓{_RESET}"
        retry_text = f"{retries} 次"
    else:
        status = f"{_RED}✗{_RESET}"
        retry_text = f"{_RED}{retries} 次{_RESET}"
    
    return f"{status} {retry_text}"

# 打印时预留足够宽度（包含 ANSI 码）
row += f" {cell:^25}"  # 实际内容 ~8 字符，ANSI 码 ~17 字符
```

**踩坑点**：不同终端对 ANSI 码的解析可能不同，导致对齐效果有偏差。最稳妥的方式是用固定宽度的列 + 不变长的内容。

---

## 性能观察

### 各模式的实际耗时（单次提取）

测试模型：gpt-4o-mini  
知识库大小：~5000 字符

| 层级 | json_schema | json_object | text |
|------|-------------|-------------|------|
| L1 单实体 | ~1.2s | ~1.5s（1次重试）| ~2.0s（2次重试）|
| L2 多实体 | ~1.5s | ~2.0s（1次重试）| ~2.5s（2次重试）|
| L3 嵌套 | ~2.0s | ~3.5s（2次重试）| ~4.0s（2次重试）|
| L4 对比 | ~2.5s | ~4.0s（1次重试）| ~5.0s（3次重试）|

**结论**：
- json_schema 模式最快（无重试），适合生产环境
- json_object 和 text 模式耗时约为 json_schema 的 1.5-2 倍
- 嵌套层级越深，重试概率越高，耗时差距越大

---

## 调试技巧

### 1. 打印原始 LLM 输出
```python
metadata["raw_output"] = raw_output
# 调试时打印
print(f"原始输出:\n{raw_output}")
```

### 2. 保存失败案例
```python
if not is_valid:
    with open(f"failed_{level_name}_{mode}.json", "w") as f:
        json.dump({
            "prompt": prompt,
            "raw_output": raw_output,
            "errors": errors,
        }, f, indent=2, ensure_ascii=False)
```

### 3. 手动测试单个层级
```python
# 在 extractor.py 底部添加
if __name__ == "__main__":
    from dotenv import load_dotenv
    from openai import OpenAI
    from knowledge_base import get_full_knowledge_text
    from schemas import DeveloperProfile, SCHEMA_REGISTRY
    
    load_dotenv()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    knowledge = get_full_knowledge_text()
    
    result, meta = extract(
        knowledge,
        "提取林昊天的档案",
        DeveloperProfile,
        "json_object",
        client,
        "gpt-4o-mini"
    )
    print(result)
    print(meta)
```

---

## 最佳实践

1. **优先使用 json_schema 强制模式**（生产环境）
2. **json_object 模式作为 fallback**（兼容不支持 json_schema 的模型）
3. **text 模式仅用于教学/对比**（实际应用中不推荐）
4. **Schema 设计原则**：
   - 字段名清晰明确（避免歧义）
   - 必填字段用 `Field(description="...")` 加描述
   - 嵌套不超过 3 层（过深会降低提取成功率）
5. **重试策略**：
   - 提取关键错误信息反馈给 LLM
   - 3 次重试后放弃（避免无限循环）
   - 记录失败案例供后续分析

---

## 未来优化方向

1. **并发提取**：12 组对比可以并行执行，减少总耗时
2. **缓存机制**：相同 prompt + schema + knowledge 的结果可以缓存
3. **动态 schema 生成**：根据用户输入的提取需求，自动生成 Pydantic Model
4. **错误分类统计**：分析哪些字段类型最容易出错，优化 schema 设计
5. **多模型对比**：测试不同模型（gpt-4, claude-3.5-sonnet 等）的结构化输出能力
