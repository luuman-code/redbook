"""
ChromaClient - Chroma 向量数据库客户端封装
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None

from ..models.memory_item import MemoryItem
from ..models.memory_type import MemoryType
from ..models.search_result import SearchResult


class ChromaMemoryClient:
    """Chroma 向量数据库客户端

    Chroma 是一个轻量级的向量数据库，专为 LLM 应用设计。
    支持持久化存储和元数据过滤。
    """

    # Collection 名称
    SHORT_TERM_COLLECTION = "short_term_memory"
    LONG_TERM_COLLECTION = "long_term_memory"
    MULTIMODAL_COLLECTION = "multimodal_memory"

    def __init__(self, persist_dir: str = "data/memory/chroma"):
        """
        初始化 Chroma 客户端

        Args:
            persist_dir: 持久化存储目录
        """
        if not CHROMA_AVAILABLE:
            raise ImportError(
                "Chroma is not installed. Please install it with: pip install chromadb"
            )

        # 确保目录存在
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        # 初始化 collections
        self._init_collections()

    def _init_collections(self):
        """初始化 collections"""
        self.short_term = self.client.get_or_create_collection(
            name=self.SHORT_TERM_COLLECTION,
            metadata={"description": "短期记忆 - 会话级"}
        )
        self.long_term = self.client.get_or_create_collection(
            name=self.LONG_TERM_COLLECTION,
            metadata={"description": "长期记忆 - 用户级"}
        )
        self.multimodal = self.client.get_or_create_collection(
            name=self.MULTIMODAL_COLLECTION,
            metadata={"description": "多模态记忆 - 图片/音视频"}
        )

    def _get_collection(self, memory_type: str) -> Any:
        """根据记忆类型获取对应的 collection"""
        if MemoryType(memory_type).is_short_term:
            return self.short_term
        elif MemoryType(memory_type).is_long_term:
            return self.long_term
        elif MemoryType(memory_type).is_multimodal:
            return self.multimodal
        else:
            return self.short_term  # 默认

    async def add(self, item: MemoryItem) -> bool:
        """
        添加记忆条目

        Args:
            item: MemoryItem 对象

        Returns:
            是否成功
        """
        try:
            collection = self._get_collection(item.memory_type)

            # 准备数据
            doc_id = item.id
            document = item.content
            metadata = {
                "memory_type": item.memory_type,
                "session_id": item.session_id or "",
                "user_id": item.user_id or "default",
                "importance": str(item.importance),
                **item.metadata
            }

            # 添加向量（如果有）
            embeddings = [item.vector] if item.vector else None

            collection.add(
                ids=[doc_id],
                documents=[document],
                metadatas=[metadata],
                embeddings=embeddings
            )

            return True

        except Exception as e:
            print(f"Failed to add memory item: {e}")
            return False

    async def add_batch(self, items: List[MemoryItem]) -> bool:
        """
        批量添加记忆条目

        Args:
            items: MemoryItem 列表

        Returns:
            是否成功
        """
        try:
            # 按 collection 分组
            by_collection: Dict[str, List[MemoryItem]] = {}
            for item in items:
                collection = self._get_collection(item.memory_type)
                if collection.name not in by_collection:
                    by_collection[collection.name] = []
                by_collection[collection.name].append(item)

            # 批量添加到各 collection
            for collection_name, collection_items in by_collection.items():
                collection = self._get_collection(collection_items[0].memory_type)

                ids = [item.id for item in collection_items]
                documents = [item.content for item in collection_items]
                metadatas = [
                    {
                        "memory_type": item.memory_type,
                        "session_id": item.session_id or "",
                        "user_id": item.user_id or "default",
                        "importance": str(item.importance),
                        **item.metadata
                    }
                    for item in collection_items
                ]
                embeddings = [item.vector for item in collection_items if item.vector]

                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings if embeddings else None
                )

            return True

        except Exception as e:
            print(f"Failed to add memory items batch: {e}")
            return False

    async def search(
        self,
        query_vector: List[float],
        n: int = 5,
        memory_type: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = "default"
    ) -> List[SearchResult]:
        """
        向量相似性搜索

        Args:
            query_vector: 查询向量
            n: 返回数量
            memory_type: 记忆类型过滤
            session_id: 会话 ID 过滤
            user_id: 用户 ID

        Returns:
            搜索结果列表
        """
        try:
            # 选择 collection
            if memory_type:
                collection = self._get_collection(memory_type)
            else:
                # 搜索所有 collection
                collection = self.short_term

            # 构建 where 过滤条件
            where_filter = {}
            if session_id:
                where_filter["session_id"] = session_id
            if user_id:
                where_filter["user_id"] = user_id

            # 执行查询
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=n,
                where=where_filter if where_filter else None
            )

            # 解析结果
            search_results = []
            if results and results["ids"]:
                distances = results.get("distances", [[]])[0]
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]

                for i, (doc_id, distance, document, metadata) in enumerate(
                    zip(results["ids"][0], distances, documents, metadatas)
                ):
                    item = MemoryItem(
                        id=doc_id,
                        content=document,
                        memory_type=metadata.get("memory_type", ""),
                        session_id=metadata.get("session_id"),
                        user_id=metadata.get("user_id"),
                        importance=float(metadata.get("importance", 1.0)),
                        metadata={k: v for k, v in metadata.items()
                                  if k not in ["memory_type", "session_id", "user_id", "importance"]}
                    )

                    # 将距离转换为相似度分数 (Chroma 距离越小越相似)
                    score = 1.0 - min(distance, 1.0)

                    search_results.append(SearchResult(
                        item=item,
                        score=score,
                        rank=i + 1
                    ))

            return search_results

        except Exception as e:
            print(f"Failed to search memory: {e}")
            return []

    async def text_search(
        self,
        query_text: str,
        n: int = 5,
        memory_type: Optional[str] = None
    ) -> List[SearchResult]:
        """
        文本搜索（使用 Chroma 内置的全文搜索）

        Args:
            query_text: 查询文本
            n: 返回数量
            memory_type: 记忆类型过滤

        Returns:
            搜索结果列表
        """
        try:
            collection = self._get_collection(memory_type) if memory_type else self.short_term

            results = collection.query(
                query_texts=[query_text],
                n_results=n
            )

            # 解析结果
            search_results = []
            if results and results["ids"]:
                distances = results.get("distances", [[]])[0]

                for i, (doc_id, distance, document, metadata) in enumerate(
                    zip(results["ids"][0], distances, results["documents"][0], results["metadatas"][0])
                ):
                    item = MemoryItem(
                        id=doc_id,
                        content=document,
                        memory_type=metadata.get("memory_type", ""),
                        session_id=metadata.get("session_id"),
                        user_id=metadata.get("user_id"),
                    )

                    score = 1.0 - min(distance, 1.0)
                    search_results.append(SearchResult(item=item, score=score, rank=i + 1))

            return search_results

        except Exception as e:
            print(f"Failed to text search: {e}")
            return []

    async def get_by_session(self, session_id: str) -> List[MemoryItem]:
        """
        获取指定会话的所有记忆

        Args:
            session_id: 会话 ID

        Returns:
            记忆条目列表
        """
        try:
            results = self.short_term.get(
                where={"session_id": session_id}
            )

            items = []
            if results and results["ids"]:
                for doc_id, document, metadata in zip(
                    results["ids"], results["documents"], results["metadatas"]
                ):
                    items.append(MemoryItem(
                        id=doc_id,
                        content=document,
                        memory_type=metadata.get("memory_type", ""),
                        session_id=metadata.get("session_id"),
                        user_id=metadata.get("user_id"),
                    ))

            return items

        except Exception as e:
            print(f"Failed to get session memories: {e}")
            return []

    async def delete(self, item_id: str, memory_type: str) -> bool:
        """
        删除记忆条目

        Args:
            item_id: 记忆 ID
            memory_type: 记忆类型

        Returns:
            是否成功
        """
        try:
            collection = self._get_collection(memory_type)
            collection.delete(ids=[item_id])
            return True
        except Exception as e:
            print(f"Failed to delete memory item: {e}")
            return False

    async def delete_by_session(self, session_id: str) -> bool:
        """
        删除指定会话的所有记忆

        Args:
            session_id: 会话 ID

        Returns:
            是否成功
        """
        try:
            # 删除短期记忆
            self.short_term.delete(where={"session_id": session_id})
            return True
        except Exception as e:
            print(f"Failed to delete session memories: {e}")
            return False

    async def count(self, memory_type: Optional[str] = None) -> int:
        """
        获取记忆数量

        Args:
            memory_type: 记忆类型（可选）

        Returns:
            记忆数量
        """
        collection = self._get_collection(memory_type) if memory_type else self.short_term
        return len(collection.get()["ids"])
