# 08-long-term-memory：跨 Session 长期记忆 Agent

## 项目概述

本项目实现了一个支持**跨 session 长期记忆**的对话 Agent，使用 ChromaDB 向量数据库持久化存储对话历史，通过语义检索在新 session 中找回相关旧记忆并注入 context。

与 `07-short-term-memory` 形成对比：
- **07 短期记忆**：内存 messages 列表，截断/压缩策略，session 结束即清除
- **08 长期记忆**：ChromaDB 磁盘存储，语义相似度检索，跨 session 持久化

---

## 架构图

```
┌─────────────────────────────────────────────────────────┐
│                     main.py (入口)                       │
│           --demo / --interactive / --clear-memory        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  agent.py (LongMemoryAgent)              │
│                                                          │
│  ask(question):                                          │
│    1. retrieve(query) → 语义检索长期记忆                  │
│    2. 注入 system prompt                                 │
│    3. Function Calling 循环（调工具）                     │
│    4. store(session_id, turn_id, q, a) → 存入向量库      │
└──────┬───────────────────────────────────────┬──────────┘
       │                                       │
       ▼                                       ▼
┌─────────────────┐                 ┌──────────────────────┐
│ long_term_      │                 │ tools.py             │
│ memory.py       │                 │  search / lookup /   │
│                 │                 │  calculate / compare │
│ OpenAICompatEF  │                 └──────────────────────┘
│ (Embedding API) │                           │
│                 │                 ┌──────────────────────┐
│ ChromaDB        │                 │ knowledge_base.py    │
│ PersistClient   │                 │  星际学院虚构知识库   │
└─────────────────┘                 └──────────────────────┘
```

### 数据流

```
用户问题
  → embedding API（向量化问题）
  → ChromaDB HNSW 索引检索（返回 cosine distance）
  → similarity = 1 - distance，过滤低于阈值的结果
  → 注入 system prompt
  → LLM + Function Calling 推理
  → 回答
  → embedding API（向量化对话）
  → ChromaDB 存储（持久化到磁盘）
```

---

## 文件结构

```
08-long-term-memory/
├── .env.example          # 配置模板
├── .gitignore            # 排除 chroma_db/ 和 .env
├── requirements.txt      # openai + chromadb + python-dotenv
├── knowledge_base.py     # 星际学院虚构知识库（复制自 07）
├── tools.py              # 工具函数（复制自 07）
├── long_term_memory.py   # LongTermMemory + OpenAICompatibleEF
├── agent.py              # LongMemoryAgent
├── display.py            # 展示格式化
├── main.py               # 入口：--demo / --interactive / --clear-memory
├── README.md             # 本文档
└── notes.md              # 踩坑记录和学习要点
```

---

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入实际的 API Key 和端点
```

`.env` 必须包含以下配置：

```ini
# 聊天模型
OPENAI_API_KEY=your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini

# Embedding 模型（必须配置，不使用本地模型）
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=your-embedding-key-here
EMBEDDING_MODEL=text-embedding-3-small

# 长期记忆
CHROMA_PERSIST_DIR=./chroma_db
MEMORY_TOP_K=3
MEMORY_THRESHOLD=0.7
```

### 2. 安装依赖

```bash
# 使用共享 venv
source ../01-simple-agent/.venv/bin/activate

# 安装（若未安装 chromadb）
uv pip install "chromadb>=0.4.0"
```

### 3. 运行 Demo

```bash
python3 main.py --demo
```

Demo 模式自动运行 3 个模拟 session：

```
Session 1 · 建立记忆：询问星际学院信息
  → 问 4 个关于量子院、林晨、苏明哲的问题
  → 每轮问答存入 ChromaDB

Session 2 · 跨 session 回忆：清空短期记忆，测试长期记忆检索
  → 问"上次我们聊了什么关于量子院的内容？"
  → 长期记忆检索 Session 1 相关内容并注入

Session 3 · 深层追问：基于长期记忆继续探索
  → 追问 Session 1 涉及的人物和关系
```

### 4. 交互模式

```bash
python3 main.py --interactive
```

支持命令：
- `reset` — 清空短期记忆（保留长期记忆），开始新 session
- `clear-memory` — 清空所有 ChromaDB 数据
- `exit` / `quit` — 退出

### 5. 清空记忆

```bash
python3 main.py --clear-memory
```

---

## 核心技术点

### ChromaDB 余弦相似度

ChromaDB 使用余弦距离（cosine distance）：

```
cosine_distance = 1 - cosine_similarity
similarity = 1 - cosine_distance
```

创建 collection 时指定：
```python
metadata={"hnsw:space": "cosine"}
```

### 自定义 Embedding 函数

项目**不使用本地模型**，所有 embedding 通过 OpenAI 兼容 API：

```python
class OpenAICompatibleEF(chromadb.EmbeddingFunction):
    def __call__(self, input: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=input)
        return [item.embedding for item in response.data]
```

必须继承 `chromadb.EmbeddingFunction` 并实现 `__call__` 方法。

### 相似度阈值过滤

```python
similarity = 1.0 - distance
if similarity >= threshold:  # 默认 0.7
    memories.append(...)
```

低于阈值的结果不注入 context，避免无关记忆干扰。

---

## 短期记忆（07）vs 长期记忆（08）对比

| 维度       | 短期记忆（07）         | 长期记忆（08）       |
|------------|----------------------|---------------------|
| 存储位置   | 内存 messages 列表    | ChromaDB 磁盘        |
| 跨session  | ❌ 清空即失           | ✅ 持久化            |
| 检索方式   | 全量截断/压缩         | 语义相似度检索        |
| 记忆容量   | 受 context 窗口限制   | 理论无上限           |
| 首轮延迟   | 无（直接截断）        | 有（embedding API 调用）|
| 记忆精度   | 按时序保留近期对话    | 按语义相关性检索      |

---

## 注意事项

- `chroma_db/` 目录已加入 `.gitignore`，不提交持久化数据
- Embedding API 有网络延迟，每轮问答都会调用两次（检索时向量化查询 + 存储时向量化对话）
- 首次运行时 collection 为空，`retrieve()` 返回 `[]`，程序正常运行
- 重复运行 `--demo` 时，旧 session 的记忆仍在，会影响检索结果（可先 `--clear-memory`）
