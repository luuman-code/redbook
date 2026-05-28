"""
MemoryManager - 记忆管理器（统一入口）

提供统一的记忆管理接口，协调短期记忆和长期记忆。
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.memory_item import MemoryItem
from ..models.memory_type import MemoryType
from ..models.search_result import SearchResult
from ..vector.chroma_client import ChromaMemoryClient
from ..vector.embeddings import generate_embedding
from .short_term import ShortTermMemory
from .long_term import LongTermMemory


class MemoryManager:
    """记忆管理器 - 统一入口

    管理用户的完整记忆系统，包括：
    - 短期记忆（当前会话）
    - 长期记忆（跨会话）
    """

    def __init__(
        self,
        user_id: str = "default",
        session_id: Optional[str] = None,
        chroma_persist_dir: str = "data/memory/chroma"
    ):
        """
        初始化记忆管理器

        Args:
            user_id: 用户 ID
            session_id: 会话 ID（可选，不提供则自动生成）
            chroma_persist_dir: Chroma 持久化目录
        """
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())

        # 确保目录存在
        Path(chroma_persist_dir).mkdir(parents=True, exist_ok=True)

        # 初始化存储
        self.chroma = ChromaMemoryClient(persist_dir=chroma_persist_dir)

        # 初始化记忆
        self.short_term = ShortTermMemory(
            session_id=self.session_id,
            chroma_client=self.chroma,
            user_id=self.user_id
        )
        self.long_term = LongTermMemory(
            user_id=self.user_id,
            chroma_client=self.chroma
        )

    @property
    def current_session_id(self) -> str:
        """获取当前会话 ID"""
        return self.session_id

    async def initialize_session(self, brief) -> bool:
        """
        初始化新会话记忆

        Args:
            brief: Brief 对象（studio.models.brief.Brief）

        Returns:
            是否成功
        """
        try:
            # 保存 Brief 到短期记忆
            return await self.short_term.save_brief(brief)
        except Exception as e:
            print(f"Failed to initialize session: {e}")
            return False

    async def add_plan(self, plan: str, plan_type: str = "content_plan") -> bool:
        """
        添加内容方案到记忆

        Args:
            plan: 方案文本
            plan_type: 方案类型

        Returns:
            是否成功
        """
        return await self.short_term.save_plan(plan, plan_type)

    async def add_generated_content(self, items: List[Any]) -> bool:
        """
        添加生成的内容到记忆

        Args:
            items: ContentItem 列表

        Returns:
            是否成功
        """
        return await self.short_term.save_generated_content(items)

    async def add_feedback(self, feedback: str, feedback_type: str = "general") -> bool:
        """
        添加用户反馈到记忆

        Args:
            feedback: 反馈文本
            feedback_type: 反馈类型

        Returns:
            是否成功
        """
        return await self.short_term.save_feedback(feedback, feedback_type)

    async def add_review(self, review_result: str, reviewer: str = "critic") -> bool:
        """
        添加审核结果到记忆

        Args:
            review_result: 审核结果
            reviewer: 审核者

        Returns:
            是否成功
        """
        return await self.short_term.save_review(review_result, reviewer)

    async def learn_from_success(
        self,
        content_items: List[Any],
        brief,
        performance_score: float = 0.8
    ) -> bool:
        """
        从成功内容中学习（保存到长期记忆）

        当内容生成成功并被用户接受时，提取有价值的信息保存到长期记忆：
        - 成功的风格偏好
        - 成功的文案模板
        - 品牌资产

        Args:
            content_items: 成功的内容项列表
            brief: 原始 Brief
            performance_score: 性能评分

        Returns:
            是否成功
        """
        try:
            success = True

            # 提取并保存风格偏好
            if brief.style:
                success &= await self.long_term.save_style_preference(
                    style=brief.style,
                    description=f"来源于会话 {self.session_id}",
                    importance=performance_score
                )

            # 保存成功的文案模板
            for item in content_items:
                if item.content and len(item.content) > 50:
                    item_type = item.item_type.value if hasattr(item.item_type, 'value') else "unknown"

                    # 只保存有代表性的内容
                    if item_type in ["title", "headline", "hashtag"]:
                        success &= await self.long_term.save_successful_template(
                            template=item.content,
                            context=f"目标: {brief.goal.value if hasattr(brief.goal, 'value') else brief.goal}",
                            content_type=item_type,
                            performance_score=performance_score
                        )

            # 如果有品牌信息，保存品牌资产
            if brief.extracted_product_info:
                product_name = brief.extracted_product_info.get("brand", "")
                if product_name:
                    success &= await self.long_term.save_brand_asset(
                        brand_name=product_name,
                        asset_type="product_info",
                        content=str(brief.extracted_product_info),
                        description="从参考图提取的产品信息"
                    )

            return success
        except Exception as e:
            print(f"Failed to learn from success: {e}")
            return False

    async def get_context_for_llm(self) -> str:
        """
        获取 LLM 上下文（短期 + 相关长期）

        这是最常用的方法，用于在调用 LLM 时提供记忆上下文。

        Returns:
            格式化的记忆上下文
        """
        try:
            parts = []

            # 添加当前会话ID
            parts.append(f"**当前会话ID**: {self.session_id}\n")

            # 获取当前会话记忆
            session_context = await self.short_term.get_session_context()
            if session_context:
                parts.append(session_context)

            # 获取相关的长期记忆
            recent_items = await self.short_term.get_recent_items(limit=3)
            if recent_items:
                query = " ".join([item.content[:200] for item in recent_items if item.content])
                long_term_context = await self.long_term.get_context_for_generation(
                    current_brief=query if query else None,
                    n=3
                )
                if long_term_context:
                    parts.append(long_term_context)

            if not parts:
                return ""

            return "\n\n".join(parts)

        except Exception as e:
            print(f"Failed to get context for LLM: {e}")
            return ""

    async def get_session_summary(self) -> Dict[str, Any]:
        """
        获取会话摘要

        Returns:
            会话摘要信息
        """
        try:
            items = await self.short_term.get_recent_items(limit=100)

            summary = {
                "session_id": self.session_id,
                "user_id": self.user_id,
                "total_items": len(items),
                "by_type": {},
                "created_at": datetime.now().isoformat(),
            }

            # 按类型统计
            for item in items:
                mem_type = item.memory_type
                if mem_type not in summary["by_type"]:
                    summary["by_type"][mem_type] = 0
                summary["by_type"][mem_type] += 1

            return summary
        except Exception as e:
            print(f"Failed to get session summary: {e}")
            return {}

    async def conclude_session(
        self,
        final_version: int = 1,
        migrate_to_long_term: bool = True
    ) -> bool:
        """
        结束会话

        Args:
            final_version: 最终版本号
            migrate_to_long_term: 是否迁移重要记忆到长期记忆

        Returns:
            是否成功
        """
        try:
            # 如果需要迁移，提取重要记忆
            if migrate_to_long_term:
                await self._migrate_important_memories()

            # 清除短期记忆
            return await self.short_term.clear_session()
        except Exception as e:
            print(f"Failed to conclude session: {e}")
            return False

    async def _migrate_important_memories(self) -> bool:
        """
        将重要记忆迁移到长期记忆

        迁移逻辑：
        - 高重要性的生成内容 -> 成功模板
        - 用户明确的风格偏好 -> 风格偏好记忆
        """
        try:
            items = await self.short_term.get_recent_items(limit=50)

            for item in items:
                # 只迁移已完成的内容
                status = item.metadata.get("status", "")
                if status == "completed" and item.importance >= 0.7:
                    item_type = item.metadata.get("item_type", "unknown")

                    # 高重要性的标题/正文 -> 成功模板
                    if item_type in ["title", "headline", "text"] and len(item.content) > 30:
                        await self.long_term.save_successful_template(
                            template=item.content,
                            context=f"来源于会话 {self.session_id}",
                            content_type=item_type,
                            performance_score=item.importance
                        )

            return True
        except Exception as e:
            print(f"Failed to migrate important memories: {e}")
            return False

    async def search_memories(
        self,
        query: str,
        memory_type: Optional[str] = None,
        n: int = 5
    ) -> List[SearchResult]:
        """
        跨记忆搜索

        Args:
            query: 查询文本
            memory_type: 可选的类型过滤
            n: 返回数量

        Returns:
            搜索结果列表
        """
        try:
            # 生成查询向量
            query_vector = await generate_embedding(query)

            # 搜索所有集合
            if memory_type:
                return await self.chroma.search(
                    query_vector=query_vector,
                    n=n,
                    memory_type=memory_type,
                    user_id=self.user_id
                )
            else:
                # 搜索所有记忆
                all_results: List[SearchResult] = []

                # 搜索短期记忆
                short_results = await self.chroma.search(
                    query_vector=query_vector,
                    n=n,
                    session_id=self.session_id,
                    user_id=self.user_id
                )
                all_results.extend(short_results)

                # 搜索长期记忆
                long_results = await self.chroma.search(
                    query_vector=query_vector,
                    n=n,
                    user_id=self.user_id
                )
                all_results.extend(long_results)

                # 按分数排序
                all_results.sort(key=lambda x: x.score, reverse=True)
                return all_results[:n]

        except Exception as e:
            print(f"Failed to search memories: {e}")
            return []

    async def get_memory_stats(self) -> Dict[str, int]:
        """
        获取记忆统计信息

        Returns:
            各类型的记忆数量统计
        """
        try:
            stats = {
                "short_term_total": await self.chroma.count(MemoryType.SESSION_BRIEF.value),
                "long_term_total": await self.chroma.count(MemoryType.USER_STYLE.value),
                "templates": await self.chroma.count(MemoryType.USER_TEMPLATE.value),
                "brand_assets": await self.chroma.count(MemoryType.USER_BRAND.value),
            }
            return stats
        except Exception as e:
            print(f"Failed to get memory stats: {e}")
            return {}

    def reset_session(self) -> str:
        """
        重置会话 ID（开始新会话）

        Returns:
            新的会话 ID
        """
        self.session_id = str(uuid.uuid4())
        self.short_term = ShortTermMemory(
            session_id=self.session_id,
            chroma_client=self.chroma,
            user_id=self.user_id
        )
        return self.session_id

    async def archive_message(
        self,
        original_content: str,
        summary: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        归档工作窗口消息到向量数据库

        用于当工作窗口上下文需要裁剪时，将旧消息归档存储以便后续检索。

        Args:
            original_content: 原始消息内容
            summary: 消息摘要
            metadata: 元数据（包含 session_id, message_count 等）

        Returns:
            归档消息的 ID
        """
        try:
            # 生成唯一 ID
            archive_id = f"{self.user_id}_archive_{uuid.uuid4().hex[:8]}"

            # 创建记忆条目
            item = MemoryItem(
                id=archive_id,
                memory_type=MemoryType.ARCHIVED_MESSAGE.value,
                content=f"【摘要】\n{summary}\n\n【原始内容】\n{original_content}",
                metadata={
                    "user_id": self.user_id,
                    "session_id": metadata.get("session_id", ""),
                    "message_count": metadata.get("message_count", 1),
                    "summary": summary,
                    "original_length": len(original_content),
                }
            )

            # 存入向量数据库
            await self.chroma.add(item)

            return archive_id

        except Exception as e:
            print(f"Failed to archive message: {e}")
            return ""

    async def search_archived_messages(
        self,
        query: str,
        session_id: Optional[str] = None,
        n: int = 5
    ) -> List[SearchResult]:
        """
        搜索归档消息

        Args:
            query: 查询文本
            session_id: 可选的会话 ID 过滤
            n: 返回数量

        Returns:
            搜索结果列表
        """
        try:
            query_vector = await generate_embedding(query)

            return await self.chroma.search(
                query_vector=query_vector,
                n=n,
                memory_type=MemoryType.ARCHIVED_MESSAGE.value,
                session_id=session_id,
                user_id=self.user_id
            )
        except Exception as e:
            print(f"Failed to search archived messages: {e}")
            return []
