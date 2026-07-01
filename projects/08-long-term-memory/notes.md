# 08-long-term-memory 踩坑记录 & 学习要点

## 踩坑记录

### 1. ChromaDB 默认 Embedding Function 会加载本地模型

**现象**：直接创建 collection 不传 `embedding_function` 参数，ChromaDB 会尝试加载 `sentence-transformers` 模型，需要下载大量本地模型文件（~400MB），且依赖 `torch`。

**解决**：必须实现自定义 `EmbeddingFunction` 子类，继承 `chromadb.EmbeddingFunction`，在 `__call__` 中调用外部 embedding API：

```python
class OpenAICompatibleEF(chromadb.EmbeddingFunction):
    def __call__(self, input: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=input)
        return [item.embedding for item in response.data]
```

**教训**：使用向量数据库时，要提前确认 embedding 方案，避免意外加载本地模型。

---

### 2. ChromaDB cosine distance vs similarity

**现象**：ChromaDB 的 `query()` 返回的 `distances` 字段是 cosine **distance**（越小越相似），不是 similarity（越大越相似）。

**关系**：
```
cosine_distance = 1 - cosine_similarity
similarity = 1 - distance
```

**代码中**：
```python
similarity = 1.0 - dist  # dist 是 cosine distance
```

**注意**：不同的向量数据库返回格式不同，Milvus 返回 IP（内积），Pinecone 返回 score 等。要仔细看文档。

---

### 3. collection 为空时 query() 会报错

**现象**：第一次运行时 collection 为空，直接调用 `_collection.query()` 会抛出异常。

**解决**：
```python
def retrieve(self, query, top_k=3, threshold=0.7):
    if self._collection.count() == 0:
        return []  # 空 collection 直接返回，不崩溃
    n = min(top_k, self._collection.count())
    results = self._collection.query(query_texts=[query], n_results=n)
    ...
```

**额外**：`n_results` 不能超过 collection 中的实际条数，所以用 `min(top_k, count)`。

---

### 4. 跨 session 演示：短期记忆和长期记忆的界限

**容易混淆的点**：
- `new_session()` 清空 `_short_term`（当前 session 的 messages 列表）
- 但 `_ltm`（ChromaDB）不受影响，Session 1 存入的记忆在 Session 2 仍然可检索

**代码实现**：
```python
def new_session(self, session_id: str) -> None:
    self._short_term = []   # 清空短期
    self._session_id = session_id
    self._turn_id = 0
    # self._ltm 不变！
```

---

### 5. EmbeddingFunction 的 `__call__` 返回类型

**现象**：ChromaDB 的 `EmbeddingFunction.__call__` 类型标注要求返回 `Embeddings`（即 `list[list[float]]`），直接返回列表推导式即可。

```python
def __call__(self, input: list[str]) -> Embeddings:
    response = self._client.embeddings.create(...)
    return [item.embedding for item in response.data]  # list[list[float]]
```

---

## 学习要点

### RAG（Retrieval-Augmented Generation）在记忆系统中的应用

长期记忆本质上是一个简化版 RAG：
- **文档库** = 历史对话（每轮 user+assistant 作为一条文档）
- **检索** = 用当前问题语义检索相似历史（向量相似度）
- **增强** = 将检索到的历史注入 system prompt
- **生成** = LLM 基于增强后的 context 回答

区别于传统 RAG（用外部知识库增强），记忆 RAG 的数据来源是对话历史本身。

---

### 向量数据库核心概念

| 概念 | 说明 |
|------|------|
| Embedding | 将文本转换为高维向量（如 1536 维），语义相似的文本在向量空间中距离近 |
| HNSW | Hierarchical Navigable Small World，高效近似最近邻搜索算法 |
| cosine similarity | 两向量夹角余弦值，1 表示完全相同，0 表示无关，-1 表示相反 |
| cosine distance | 1 - cosine_similarity，ChromaDB 用这个作为距离度量 |
| top-k 检索 | 返回最相似的 k 条结果 |
| 阈值过滤 | 相似度低于阈值的结果不注入，避免无关记忆干扰 |

---

### 短期 vs 长期记忆设计权衡

| 场景 | 适合方案 |
|------|---------|
| 对话轮数少（< 20 轮），需要完整上下文 | 短期记忆（全量 messages） |
| 长期使用，跨多次会话 | 长期记忆（向量数据库） |
| 需要精确引用前几句话 | 短期记忆（最近 N 轮） |
| 需要"记住你上次提到的某件事" | 长期记忆（语义检索） |
| 对延迟要求极低 | 短期记忆（无额外 API 调用） |

实际生产系统通常**组合使用**：短期记忆保留当前 session 对话，长期记忆跨 session 检索关键信息。

---

### ChromaDB PersistentClient

```python
client = chromadb.PersistentClient(path="./chroma_db")
```

- 数据自动持久化到 SQLite + HNSW 索引文件
- 进程重启后数据仍在
- `get_or_create_collection` 幂等（存在就获取，不存在才创建）
- 删除 collection：`client.delete_collection(name)`

---

## 待探索

- **记忆去重**：语义相近的问题问两次会存两条，可用余弦相似度阈值过滤重复
- **记忆遗忘**：基于时间戳的衰减机制（老旧记忆权重降低）
- **记忆索引**：按 session_id 过滤，或按主题分类（多个 collection）
- **记忆摘要**：定期用 LLM 将多条相关记忆压缩为一条（减少存储量）
- **混合检索**：向量相似度 + BM25 关键词检索（提高召回率）
