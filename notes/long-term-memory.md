# 长期记忆（Long-Term Memory）

长期记忆让 Agent 跨越 session 边界"记住"过去的对话。
核心技术：**向量数据库 + 语义检索**（RAG 模式在记忆系统中的应用）。

---

## 短期 vs 长期记忆对比

| | 短期记忆（07） | 长期记忆（08） |
|--|-------------|-------------|
| **存储位置** | 内存（messages 列表） | 磁盘（向量数据库） |
| **生命周期** | 单次 session，重启即丢 | 持久化，跨 session 保留 |
| **检索方式** | 全量传入 / 按规则截断 | 语义相似度检索（top-k） |
| **记忆容量** | 受 context 窗口限制 | 理论无上限 |
| **实现复杂度** | 中（截断策略） | 高（向量库 + embedding） |
| **适用场景** | 当前对话连贯性 | 跨会话历史回忆 |

---

## 核心架构：RAG 记忆模式

```
用户提问
   ↓
1. 语义检索：用问题向量检索历史记忆（top-k + 阈值过滤）
   ↓
2. 注入 context：相关记忆追加到 system prompt 末尾
   ↓
3. LLM 推理：利用注入的历史记忆回答问题
   ↓
4. 存储记忆：将本轮对话（user + assistant）存入向量库
   ↓
回答用户
```

这本质上是 **RAG（Retrieval-Augmented Generation）**：
- 检索（Retrieval）= 向量相似度搜索历史对话
- 增强（Augmented）= 将检索结果注入 system prompt
- 生成（Generation）= LLM 基于增强后的 context 回答

---

## 向量数据库：ChromaDB

### 核心操作

```python
import chromadb

# 持久化客户端（写磁盘，重启后保留）
client = chromadb.PersistentClient(path="./chroma_db")

# 创建/获取 collection（指定 cosine 距离）
collection = client.get_or_create_collection(
    name="memory",
    embedding_function=my_ef,           # 必须显式传入！
    metadata={"hnsw:space": "cosine"},  # 使用余弦相似度
)

# 存储
collection.add(
    documents=["用户: 林晨在哪个院系\n助手: 量子院"],
    metadatas=[{"session_id": "s1", "turn_id": 1}],
    ids=["s1_turn_1"],
)

# 检索
results = collection.query(
    query_texts=["林晨的导师是谁"],
    n_results=3,
)
# results["distances"][0] = cosine distance（越小越相似）
# similarity = 1.0 - distance
```

### 重要陷阱：默认 embedding 会下载本地模型

```python
# ❌ 不传 embedding_function → ChromaDB 自动下载 sentence-transformers
collection = client.get_or_create_collection(name="memory")

# ✅ 必须显式传入自定义 EF
collection = client.get_or_create_collection(
    name="memory",
    embedding_function=OpenAICompatibleEF(...)
)
```

---

## 自定义 Embedding 函数

通过 OpenAI 兼容 API 生成向量，无需本地模型：

```python
from chromadb import EmbeddingFunction, Embeddings
from openai import OpenAI

class OpenAICompatibleEF(EmbeddingFunction):
    """
    自定义 embedding 函数：通过 API 调用生成向量。
    支持任何 OpenAI 兼容的 embedding 端点。
    """
    def __init__(self, base_url: str, api_key: str, model: str):
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def __call__(self, input: list[str]) -> Embeddings:
        # ChromaDB 要求返回 list[list[float]]
        response = self._client.embeddings.create(
            model=self._model,
            input=input,
        )
        return [item.embedding for item in response.data]
```

配置：
```
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
```

---

## 相似度阈值过滤

ChromaDB 返回 **cosine distance**（越小越相似），需转换：

```python
# distance ∈ [0, 2]，cosine：0=完全相同，2=完全相反
# similarity = 1 - distance，∈ [-1, 1]，通常在 [0, 1]

similarity = 1.0 - distance  # 转换

# 只注入相似度 >= 阈值的记忆（过滤噪声）
if similarity >= threshold:  # 默认 threshold=0.7
    memories.append(...)
```

**为什么需要阈值？**  
无关的历史记忆注入 context 会干扰 LLM 推理（"幻觉式关联"）。
0.7 是实践中常用的起点，可根据业务场景调整。

---

## 跨 Session 的关键设计

```python
class LongMemoryAgent:
    def new_session(self, session_id: str):
        """开始新 session：只清短期记忆，长期记忆保留"""
        self._short_term = []      # ← 清空当前 session messages
        self._session_id = session_id
        self._turn_id = 0
        # self._ltm 不动！ChromaDB 数据持久化在磁盘
```

**这是长期记忆的核心**：
- `new_session()` = 人类"换了个话题"，但过去的记忆还在
- 不是 `clear()`（清空 ChromaDB），而是 `_short_term = []`（清空当前会话）

---

## 记忆注入格式

检索到相关记忆后，注入 system prompt 末尾：

```python
system_content = base_system_prompt
if memories:
    lines = [
        f"- [Session {m['metadata']['session_id']} · 第{m['metadata']['turn_id']}轮 · "
        f"相似度{m['similarity']}] 用户问：{m['metadata']['user_query']}  "
        f"助手答：{m['metadata']['assistant_answer']}"
        for m in memories
    ]
    system_content += "\n\n[长期记忆] 以下是过去对话中的相关内容：\n" + "\n".join(lines)
```

---

## 实战教训

### 1. Collection 为空时 query() 崩溃

```python
# ❌ 直接 query 会在空 collection 上报错
results = collection.query(query_texts=[question], n_results=3)

# ✅ 先判断
if collection.count() == 0:
    return []
results = collection.query(...)
```

### 2. n_results 不能超过 collection 中的文档数

```python
# ❌ 文档数 < n_results 时报错
results = collection.query(query_texts=[q], n_results=5)  # 只有 2 条

# ✅ 取较小值
n = min(top_k, collection.count())
results = collection.query(query_texts=[q], n_results=n)
```

### 3. PersistentClient 路径是相对路径时的陷阱

```python
# ❌ 相对路径基于当前工作目录，不同目录运行会创建不同位置的数据库
client = chromadb.PersistentClient(path="./chroma_db")

# ✅ 使用绝对路径（通过 __file__ 计算）
persist_dir = Path(__file__).parent / "chroma_db"
client = chromadb.PersistentClient(path=str(persist_dir))
```

---

## 与 07 的承接关系

07 的 `MemoryManager` 抽象基类是 08 的设计参考：
- 07：`_history` + `get_messages()` 分离 → 08：`_short_term` + ChromaDB 分离
- 07：策略决定"看到多少历史" → 08：检索决定"注入哪些历史"
- 07 处理**当前 session 内**的记忆压力 → 08 处理**跨 session**的记忆延续

---

**最后更新**：2026-07-02  
**来源项目**：08-long-term-memory
