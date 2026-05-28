"""
LongTermMemory - 长期记忆（用户级）

管理用户的：
- 风格偏好
- 品牌资产
- 成功文案模板
- 其他偏好
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.memory_item import MemoryItem
from ..models.memory_type import MemoryType
from ..models.search_result import SearchResult
from ..vector.chroma_client import ChromaMemoryClient
from ..vector.embeddings import generate_embedding


class LongTermMemory:
    """长期记忆 - 用户级

    跨会话存储和管理用户的持久记忆。
    """

    def __init__(
        self,
        user_id: str,
        chroma_client: ChromaMemoryClient
    ):
        """
        初始化长期记忆

        Args:
            user_id: 用户 ID
            chroma_client: Chroma 向量数据库客户端
        """
        self.user_id = user_id
        self.chroma = chroma_client

    async def save_style_preference(
        self,
        style: str,
        description: str = "",
        importance: float = 0.8
    ) -> bool:
        """
        保存用户风格偏好

        Args:
            style: 风格名称（如 "小清新", "专业测评"）
            description: 风格描述
            importance: 重要性评分（0.0 - 1.0）

        Returns:
            是否成功
        """
        try:
            content = f"风格: {style}"
            if description:
                content += f"\n描述: {description}"

            item = MemoryItem(
                id=f"{self.user_id}_style_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.USER_STYLE.value,
                content=content,
                importance=importance,
                metadata={
                    "user_id": self.user_id,
                    "style": style,
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save style preference: {e}")
            return False

    async def save_brand_asset(
        self,
        brand_name: str,
        asset_type: str,
        content: str,
        description: str = ""
    ) -> bool:
        """
        保存品牌资产（Logo、配色、口号等）

        Args:
            brand_name: 品牌名称
            asset_type: 资产类型（如 "logo", "color", "slogan", "template"）
            content: 资产内容（可以是文本或 base64 图像）
            description: 资产描述

        Returns:
            是否成功
        """
        try:
            item = MemoryItem(
                id=f"{self.user_id}_brand_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.USER_BRAND.value,
                content=content,
                metadata={
                    "user_id": self.user_id,
                    "brand_name": brand_name,
                    "asset_type": asset_type,
                    "description": description,
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save brand asset: {e}")
            return False

    async def save_successful_template(
        self,
        template: str,
        context: str = "",
        content_type: str = "post",
        performance_score: float = 0.0
    ) -> bool:
        """
        保存成功的文案模板

        Args:
            template: 模板内容
            context: 使用场景描述
            content_type: 内容类型（如 "post", "title", "hashtag"）
            performance_score: 性能评分（0.0 - 1.0）

        Returns:
            是否成功
        """
        try:
            item = MemoryItem(
                id=f"{self.user_id}_template_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.USER_TEMPLATE.value,
                content=template,
                metadata={
                    "user_id": self.user_id,
                    "context": context,
                    "content_type": content_type,
                    "performance_score": str(performance_score),
                },
                importance=max(performance_score, 0.5)  # 至少 0.5 重要性
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save successful template: {e}")
            return False

    async def save_preference(
        self,
        category: str,
        preference: str,
        value: str = "",
        importance: float = 0.6
    ) -> bool:
        """
        保存其他用户偏好

        Args:
            category: 偏好类别（如 "writing", "image", "video"）
            preference: 偏好内容
            value: 偏好值（可选）
            importance: 重要性评分

        Returns:
            是否成功
        """
        try:
            content = f"{category}: {preference}"
            if value:
                content += f" = {value}"

            item = MemoryItem(
                id=f"{self.user_id}_pref_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.USER_PREFERENCE.value,
                content=content,
                importance=importance,
                metadata={
                    "user_id": self.user_id,
                    "category": category,
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save preference: {e}")
            return False

    async def search_similar(
        self,
        query: str,
        n: int = 5,
        memory_types: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        搜索相似记忆

        Args:
            query: 查询文本
            n: 返回数量
            memory_types: 可选的类型过滤列表

        Returns:
            搜索结果列表
        """
        try:
            # 生成查询向量
            query_vector = await generate_embedding(query)

            # 如果指定了类型，在各类型中搜索
            if memory_types:
                all_results: List[SearchResult] = []
                for mem_type in memory_types:
                    results = await self.chroma.search(
                        query_vector=query_vector,
                        n=n,
                        memory_type=mem_type,
                        user_id=self.user_id
                    )
                    all_results.extend(results)

                # 按分数排序
                all_results.sort(key=lambda x: x.score, reverse=True)
                return all_results[:n]

            # 默认搜索长期记忆
            return await self.chroma.search(
                query_vector=query_vector,
                n=n,
                user_id=self.user_id
            )
        except Exception as e:
            print(f"Failed to search similar memories: {e}")
            return []

    async def get_style_preferences(self) -> List[str]:
        """
        获取用户的所有风格偏好

        Returns:
            风格偏好文本列表
        """
        try:
            # 搜索所有风格记忆
            results = await self.chroma.search(
                query_vector=[0.0] * 1536,  # 空向量，获取所有
                n=100,
                memory_type=MemoryType.USER_STYLE.value,
                user_id=self.user_id
            )

            # 如果搜索不支持空向量，使用文本搜索
            if not results:
                return await self._get_by_type(MemoryType.USER_STYLE.value)

            return [r.item.content for r in results]
        except Exception as e:
            print(f"Failed to get style preferences: {e}")
            return []

    async def get_brand_assets(self, brand_name: Optional[str] = None) -> List[MemoryItem]:
        """
        获取品牌资产

        Args:
            brand_name: 可选的品牌名称过滤

        Returns:
            品牌资产列表
        """
        try:
            items = await self._get_by_type(MemoryType.USER_BRAND.value)

            if brand_name:
                items = [
                    item for item in items
                    if item.metadata.get("brand_name") == brand_name
                ]

            return items
        except Exception as e:
            print(f"Failed to get brand assets: {e}")
            return []

    async def get_successful_templates(
        self,
        content_type: Optional[str] = None,
        min_score: float = 0.0
    ) -> List[MemoryItem]:
        """
        获取成功的文案模板

        Args:
            content_type: 可选的内容类型过滤
            min_score: 最低性能评分

        Returns:
            模板列表
        """
        try:
            items = await self._get_by_type(MemoryType.USER_TEMPLATE.value)

            # 应用过滤
            if content_type:
                items = [
                    item for item in items
                    if item.metadata.get("content_type") == content_type
                ]

            if min_score > 0:
                items = [
                    item for item in items
                    if float(item.metadata.get("performance_score", 0)) >= min_score
                ]

            # 按重要性排序
            items.sort(key=lambda x: x.importance, reverse=True)

            return items
        except Exception as e:
            print(f"Failed to get successful templates: {e}")
            return []

    async def get_context_for_generation(
        self,
        current_brief: Optional[str] = None,
        n: int = 5
    ) -> str:
        """
        获取用于生成的长期记忆上下文

        Args:
            current_brief: 当前的 Brief 描述（用于相关记忆检索）
            n: 检索的记忆数量

        Returns:
            格式化的记忆上下文
        """
        try:
            parts = ["## 用户历史记忆"]

            # 获取风格偏好
            styles = await self.get_style_preferences()
            if styles:
                parts.append("\n### 风格偏好")
                for style in styles[:3]:
                    parts.append(f"- {style}")

            # 获取成功的模板
            templates = await self.get_successful_templates(min_score=0.5)
            if templates:
                parts.append("\n### 成功文案模板")
                for tmpl in templates[:3]:
                    content_type = tmpl.metadata.get("content_type", "unknown")
                    preview = tmpl.content[:100] + "..." if len(tmpl.content) > 100 else tmpl.content
                    parts.append(f"- [{content_type}] {preview}")

            # 如果有当前 Brief，搜索相关记忆
            if current_brief:
                related = await self.search_similar(current_brief, n=3)
                if related:
                    parts.append("\n### 相关历史内容")
                    for r in related:
                        item_type = r.item.metadata.get("item_type", "unknown")
                        preview = r.item.content[:100] + "..." if len(r.item.content) > 100 else r.item.content
                        parts.append(f"- [{item_type}] (相似度: {r.score:.2f}) {preview}")

            return "\n".join(parts) if len(parts) > 1 else ""

        except Exception as e:
            print(f"Failed to get context for generation: {e}")
            return ""

    async def _get_by_type(self, memory_type: str) -> List[MemoryItem]:
        """获取指定类型的所有记忆"""
        try:
            # 使用 Chroma 的 get 方法获取该用户该类型的所有记忆
            results = await self.chroma.search(
                query_vector=[0.0] * 1536,
                n=100,
                memory_type=memory_type,
                user_id=self.user_id
            )
            return [r.item for r in results]
        except Exception:
            return []

    async def update_importance(
        self,
        item_id: str,
        new_importance: float
    ) -> bool:
        """
        更新记忆条目的重要性

        Args:
            item_id: 记忆 ID
            new_importance: 新的重要性评分

        Returns:
            是否成功
        """
        # Chroma 不直接支持更新，如果需要应该使用 SQLite 存储结构化数据
        # 这里暂时不支持
        print(f"update_importance not fully supported in Chroma backend")
        return False
