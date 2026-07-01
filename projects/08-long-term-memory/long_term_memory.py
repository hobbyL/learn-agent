"""
长期记忆管理器
==============

使用 ChromaDB 向量数据库持久化存储对话历史。
每轮对话（user + assistant）作为一条记忆存入向量库，
查询时用当前问题做语义检索，返回最相关的历史记忆。

核心原理：
- embedding：将文本转换为高维向量，语义相似的文本距离近
- cosine distance：ChromaDB 默认用余弦距离，distance = 1 - cosine_similarity
- HNSW 索引：高效近似最近邻搜索，支持大规模向量检索

与短期记忆（07）的本质区别：
- 短期：内存 messages 列表，session 结束即清除
- 长期：磁盘向量库，跨 session 持久化，语义检索而非全量传入
"""

import chromadb
from chromadb import EmbeddingFunction, Embeddings
from openai import OpenAI
from datetime import datetime


# ============================================================
# 自定义 Embedding 函数
# ============================================================

class OpenAICompatibleEF(EmbeddingFunction):
    """
    通过 OpenAI 兼容 API 生成文本向量的自定义 embedding 函数。

    ChromaDB 要求 EmbeddingFunction 子类实现 __call__ 方法：
    - 输入：文本列表 list[str]
    - 输出：向量列表 list[list[float]]

    重要：不使用 ChromaDB 默认的 embedding function（会加载本地模型），
    所有 embedding 调用通过外部 API 完成。

    参数：
        base_url  — embedding 服务端点（OpenAI 兼容）
        api_key   — API 密钥
        model     — 模型名称（如 text-embedding-3-small）
    """

    def __init__(self, base_url: str, api_key: str, model: str):
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def __call__(self, input: list[str]) -> Embeddings:
        """调用 embedding API，返回向量列表。"""
        response = self._client.embeddings.create(
            model=self._model,
            input=input,
        )
        return [item.embedding for item in response.data]


# ============================================================
# 长期记忆管理器
# ============================================================

class LongTermMemory:
    """
    长期记忆管理器。

    使用 ChromaDB PersistentClient 将对话存储到磁盘，
    重启程序后记忆仍然存在（跨 session 持久化）。

    核心接口：
        store()    — 存储一轮对话到向量库
        retrieve() — 语义检索相关记忆（返回超过阈值的结果）
        clear()    — 清空所有记忆（删除并重建 collection）
        count()    — 当前记忆条数

    存储格式：
        document：  "用户: {query}\n助手: {answer}"（用于生成 embedding）
        metadata：  {session_id, turn_id, timestamp, user_query, assistant_answer}
        id：        "{session_id}_turn_{turn_id}"（唯一标识，防止重复存储）
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        embedding_fn: EmbeddingFunction,
    ):
        # PersistentClient 自动持久化到磁盘，重启后记忆仍在
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection_name = collection_name
        self._embedding_fn = embedding_fn

        # 使用余弦相似度空间（ChromaDB 默认即为 cosine）
        # distance = 1 - cosine_similarity，所以 similarity = 1 - distance
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def store(
        self,
        session_id: str,
        turn_id: int,
        user_query: str,
        assistant_answer: str,
    ) -> None:
        """
        将一轮对话存入向量库。

        document 字段同时作为 embedding 的输入，
        将 user 和 assistant 内容合并可以捕获两者的语义。

        参数：
            session_id       — 当前会话 ID（如 "session_1"）
            turn_id          — 当前轮次编号（从 1 开始）
            user_query       — 用户问题
            assistant_answer — 助手回答
        """
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
            # 唯一 ID 防止重复存储同一轮对话
            ids=[f"{session_id}_turn_{turn_id}"],
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        threshold: float = 0.7,
    ) -> list[dict]:
        """
        语义检索相关记忆。

        ChromaDB 的 query() 返回 cosine distance（越小越相似），
        转换公式：similarity = 1.0 - distance

        只返回 similarity >= threshold 的结果，
        按相似度降序排列（最相关的排最前）。

        参数：
            query     — 检索查询文本（通常是当前用户问题）
            top_k     — 最多返回多少条
            threshold — 相似度阈值，低于此值的结果不注入

        返回：
            list[dict]，每项包含 document、metadata、similarity
            collection 为空时返回 []（不崩溃）
        """
        # 首次运行时 collection 为空，直接返回避免报错
        if self._collection.count() == 0:
            return []

        # n_results 不能超过 collection 中的实际条数
        n = min(top_k, self._collection.count())
        results = self._collection.query(
            query_texts=[query],
            n_results=n,
        )

        memories = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # cosine distance → similarity
            similarity = 1.0 - dist
            if similarity >= threshold:
                memories.append({
                    "document": doc,
                    "metadata": meta,
                    "similarity": round(similarity, 3),
                })

        # 按相似度降序（最相关排前面）
        return sorted(memories, key=lambda x: x["similarity"], reverse=True)

    def clear(self) -> None:
        """
        清空所有记忆。

        删除整个 collection 再重建，比逐条删除更高效。
        重建时保持相同的 collection_name 和 embedding_fn 配置。
        """
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """返回当前存储的记忆条数。"""
        return self._collection.count()


# ============================================================
# 快速验证（不调用真实 API）
# ============================================================

if __name__ == "__main__":
    print("=== LongTermMemory 结构验证 ===\n")

    # 验证 OpenAICompatibleEF 能实例化
    print("OpenAICompatibleEF 实例化验证:")
    ef = OpenAICompatibleEF(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        model="text-embedding-3-small",
    )
    print(f"  OpenAICompatibleEF 创建成功 ✓ (model={ef._model})")

    print("\n所有结构验证通过 ✓")
    print("（实际存储/检索需要配置 .env 并运行 main.py）")
