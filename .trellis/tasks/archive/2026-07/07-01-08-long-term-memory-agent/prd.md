# 08-long-term-memory：长期记忆 Agent

## Goal

实现一个支持**跨 session 长期记忆**的 Agent，通过 ChromaDB 向量数据库持久化存储对话历史，
用语义检索在新 session 中找回相关旧记忆并注入 context，直观展示长期记忆对 Agent 能力的影响。

核心学习目标：
- 理解向量数据库的存储/检索原理（embedding + 余弦相似度）
- 掌握 RAG（Retrieval-Augmented Generation）在记忆系统中的应用
- 体验跨 session 记忆的实际效果（Session 1 建立 → Session 2 回忆）
- 与 07-short-term-memory 形成对比：短期（截断策略）vs 长期（语义检索）

---

## Requirements

### 向量数据库
- 使用 **ChromaDB**（本地文件持久化，SQLite + HNSW 索引）
- Embedding：自定义端点（OpenAI 兼容 API），通过环境变量配置：
  ```
  EMBEDDING_BASE_URL=...
  EMBEDDING_API_KEY=...
  EMBEDDING_MODEL=...
  ```
- 持久化目录：`projects/08-long-term-memory/chroma_db/`（写入 .gitignore）

### 存储内容
- 每轮对话（user + assistant）作为一条记忆存入向量库
- 存储格式：
  - `document`：`"用户: {user}\n助手: {assistant}"`（用于 embedding）
  - `metadata`：`{session_id, turn_id, timestamp, user_query, assistant_answer}`

### 检索策略
- 查询时用当前 user 问题做语义检索
- top-k：默认 3 条
- 相似度阈值：默认 0.7（低于此值的结果不注入）
- 检索到的记忆注入 system prompt 末尾：
  ```
  [长期记忆] 以下是过去对话中的相关内容：
  - [Session X, 第N轮] 用户问：...  助手答：...
  ```

### 知识库
- 复用 `projects/07-short-term-memory/knowledge_base.py`（星际学院）
- 复用 `projects/07-short-term-memory/tools.py`（search/lookup/calculate/compare）

### 架构模块

```
long_term_memory.py   # LongTermMemory：ChromaDB封装，store()/retrieve()/clear()
agent.py              # LongMemoryAgent：注入 LongTermMemory，ask() 接口
display.py            # 展示检索到的记忆、注入内容、回答
main.py               # 入口：--demo / --interactive / --clear-memory
knowledge_base.py     # 软链接或直接复制自 07
tools.py              # 软链接或直接复制自 07
.env.example          # 配置模板
requirements.txt      # openai + chromadb + python-dotenv
```

### 运行模式

1. **`--demo` 模式（核心）**：自动走完 3 个模拟 session：
   - **Session 1**：问 3~4 个关于星际学院的问题（建立记忆）
   - **Session 2**：清空短期 messages，长期记忆保留 → 问"上次我们聊了什么关于量子院的内容？"
   - **Session 3**：追问 Session 1 中涉及的人物（验证跨 session 检索）
   - 每轮打印：检索到哪些记忆、注入了什么、最终回答

2. **`--interactive` 模式**：交互式对话，每轮自动存入长期记忆，启动时自动加载历史
   - 支持 `reset` 命令（清空短期 messages，不清长期记忆）
   - 支持 `clear-memory` 命令（清空长期记忆）

3. **`--clear-memory`**：清空 ChromaDB 持久化数据

### 展示内容（每轮）
```
── Session 2 · 第 1 轮 ──
📤 用户：上次我们聊了什么关于量子院的内容？

🔍 检索长期记忆（top-3，阈值0.7）：
  [相似度 0.92] Session 1 · 第2轮：用户问"量子院的院长是谁"，助手答"方若冰"
  [相似度 0.87] Session 1 · 第1轮：用户问"林晨在哪个院系"，助手答"量子院"

💉 注入 context：2 条记忆

🤖 回答：根据我们之前的对话，量子院的院长是方若冰，林晨是量子院的学员。
```

### 与 07 的对比展示
`--demo` 结束后打印对比表：

```
             短期记忆（07）          长期记忆（08）
存储位置      内存 messages 列表      ChromaDB 磁盘
跨session     ❌ 清空即失             ✅ 持久化
检索方式      全量截断/压缩           语义相似度检索
记忆容量      受 context 窗口限制     理论无上限
```

---

## Acceptance Criteria

- [ ] ChromaDB 本地文件持久化：重启程序后记忆仍在
- [ ] `--demo` 模式：3 个模拟 session 自动运行，Session 2 能正确引用 Session 1 的对话
- [ ] 相似度阈值过滤：低于 0.7 的结果不注入
- [ ] 每轮展示检索到的记忆条数、相似度分数、注入内容摘要
- [ ] `--clear-memory` 能清空持久化数据
- [ ] collection 为空时（首次运行）优雅处理（不崩溃）
- [ ] `.env` + `.env.example` 配置 embedding 端点三要素

---

## Definition of Done

- 代码注释密度与 07 一致（关键逻辑有中文注释）
- README.md：架构图 + 快速开始 + 与 07 的对比表
- notes.md：踩坑记录 + 学习要点
- 通过真机验证（至少运行一次 `--demo` 完整流程）

---

## Technical Approach

### LongTermMemory 核心接口

```python
class LongTermMemory:
    def __init__(self, persist_dir: str, collection_name: str, embedding_fn):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
        )

    def store(self, session_id: str, turn_id: int,
              user_query: str, assistant_answer: str) -> None:
        """将一轮对话存入向量库"""
        document = f"用户: {user_query}\n助手: {assistant_answer}"
        self._collection.add(
            documents=[document],
            metadatas=[{
                "session_id": session_id,
                "turn_id": turn_id,
                "timestamp": datetime.now().isoformat(),
                "user_query": user_query,
                "assistant_answer": assistant_answer,
            }],
            ids=[f"{session_id}_turn_{turn_id}"],
        )

    def retrieve(self, query: str, top_k: int = 3,
                 threshold: float = 0.7) -> list[dict]:
        """语义检索相关记忆，返回超过阈值的结果"""
        if self._collection.count() == 0:
            return []
        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self._collection.count()),
        )
        # ChromaDB 返回距离（越小越相似），转换为相似度
        memories = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            similarity = 1 - dist  # cosine distance → similarity
            if similarity >= threshold:
                memories.append({"document": doc, "metadata": meta,
                                  "similarity": similarity})
        return memories

    def clear(self) -> None:
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(...)
```

### 自定义 Embedding 函数

```python
from chromadb import EmbeddingFunction

class OpenAICompatibleEF(EmbeddingFunction):
    def __init__(self, base_url, api_key, model):
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def __call__(self, input: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self._model,
            input=input,
        )
        return [item.embedding for item in response.data]
```

### 环境变量

```
OPENAI_API_KEY=...
OPENAI_BASE_URL=...          # 聊天模型端点
MODEL_NAME=...               # 聊天模型名
EMBEDDING_BASE_URL=...       # embedding 端点
EMBEDDING_API_KEY=...        # embedding key
EMBEDDING_MODEL=...          # embedding 模型名
CHROMA_PERSIST_DIR=./chroma_db
MEMORY_TOP_K=3
MEMORY_THRESHOLD=0.7
```

---

## Decision (ADR-lite)

**Context**：长期记忆需要向量数据库支持语义检索，有多种库可选

**Decision**：
- ChromaDB（本地持久化，开箱即用）
- 存完整对话轮次（最直观）
- 自定义 embedding 端点（用户提供 URL/Key/Model，复用已有基础设施）
- 复用星际学院知识库（07→08 跨 session 记忆演示）
- 模拟多 session 演示（单次运行自动走完建立→检索完整循环）

**Consequences**：
- ChromaDB 首次 `query()` 时需要调 embedding API，有网络延迟
- `chroma_db/` 目录加入 .gitignore，不提交持久化数据
- 复用 07 知识库减少重复代码，但 08 项目目录需要 copy 或 import

---

## Out of Scope

- 记忆去重（相似问题问两次会存两条，可留 notes 待探索）
- 记忆遗忘/过期机制
- 多用户隔离
- OpenAI 官方 Embedding API（用自定义端点代替）
- 与 07 MemoryManager 的继承集成（08 独立实现，为清晰起见）

---

## Technical Notes

- 共用 venv：`projects/01-simple-agent/.venv/`
- 新增依赖：`chromadb>=0.4.0`
- ChromaDB cosine distance：默认使用 cosine，`distance = 1 - cosine_similarity`，所以 `similarity = 1 - distance`
- 复用文件：`projects/07-short-term-memory/knowledge_base.py`、`tools.py`
- `.gitignore` 需加：`projects/08-long-term-memory/chroma_db/`
