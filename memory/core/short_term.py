"""
ShortTermMemory - 短期记忆（会话级）

管理当前会话的：
- Brief 内容
- 生成的历史内容
- 用户反馈
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.memory_item import MemoryItem
from ..models.memory_type import MemoryType
from ..models.search_result import SearchResult
from ..vector.chroma_client import ChromaMemoryClient


class ShortTermMemory:
    """短期记忆 - 会话级

    管理单个会话的生命周期内的记忆。
    会话结束后，可选择性地将重要记忆迁移到长期记忆。
    """

    def __init__(
        self,
        session_id: str,
        chroma_client: ChromaMemoryClient,
        user_id: str = "default"
    ):
        """
        初始化短期记忆

        Args:
            session_id: 会话 ID
            chroma_client: Chroma 向量数据库客户端
            user_id: 用户 ID
        """
        self.session_id = session_id
        self.user_id = user_id
        self.chroma = chroma_client

    async def save_brief(self, brief) -> bool:
        """
        保存 Brief 到记忆

        Args:
            brief: Brief 对象（studio.models.brief.Brief）

        Returns:
            是否成功
        """
        try:
            # 将 Brief 转为文本
            brief_text = self._brief_to_text(brief)

            item = MemoryItem(
                id=f"{self.session_id}_brief",
                memory_type=MemoryType.SESSION_BRIEF.value,
                content=brief_text,
                metadata={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "goal": brief.goal.value if hasattr(brief.goal, 'value') else str(brief.goal),
                    "style": brief.style,
                    "keywords": ",".join(brief.keywords) if brief.keywords else "",
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save brief: {e}")
            return False

    async def save_plan(self, plan: str, plan_type: str = "content_plan") -> bool:
        """
        保存内容方案到记忆

        Args:
            plan: 方案文本
            plan_type: 方案类型

        Returns:
            是否成功
        """
        try:
            item = MemoryItem(
                id=f"{self.session_id}_plan_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.SESSION_PLAN.value,
                content=plan,
                metadata={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "plan_type": plan_type,
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save plan: {e}")
            return False

    async def save_generated_content(
        self,
        items: List[Any],
        content_type: str = "generated"
    ) -> bool:
        """
        保存生成的内容

        Args:
            items: ContentItem 列表（studio.models.content_item.ContentItem）
            content_type: 内容类型标识

        Returns:
            是否成功
        """
        try:
            memory_items = []
            for item in items:
                # 跳过空内容
                if not item.content:
                    continue

                # 获取内容类型
                item_type = item.item_type.value if hasattr(item.item_type, 'value') else str(item.item_type)

                memory_item = MemoryItem(
                    id=f"{self.session_id}_gen_{item.item_id}",
                    memory_type=MemoryType.SESSION_GENERATED.value,
                    content=item.content,
                    metadata={
                        "session_id": self.session_id,
                        "user_id": self.user_id,
                        "item_type": item_type,
                        "content_type": content_type,
                        "position": str(item.position) if hasattr(item, 'position') else "0",
                        "status": item.status.value if hasattr(item.status, 'value') else str(item.status),
                    }
                )
                memory_items.append(memory_item)

            if memory_items:
                return await self.chroma.add_batch(memory_items)
            return True
        except Exception as e:
            print(f"Failed to save generated content: {e}")
            return False

    async def save_feedback(self, feedback: str, feedback_type: str = "general") -> bool:
        """
        保存用户反馈

        Args:
            feedback: 反馈文本
            feedback_type: 反馈类型（如 "revision", "approval", "rejection"）

        Returns:
            是否成功
        """
        try:
            item = MemoryItem(
                id=f"{self.session_id}_fb_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.SESSION_FEEDBACK.value,
                content=feedback,
                metadata={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "feedback_type": feedback_type,
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save feedback: {e}")
            return False

    async def save_review(self, review_result: str, reviewer: str = "critic") -> bool:
        """
        保存审核结果

        Args:
            review_result: 审核结果文本
            reviewer: 审核者（如 "critic", "user"）

        Returns:
            是否成功
        """
        try:
            item = MemoryItem(
                id=f"{self.session_id}_review_{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.SESSION_REVIEW.value,
                content=review_result,
                metadata={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "reviewer": reviewer,
                }
            )

            return await self.chroma.add(item)
        except Exception as e:
            print(f"Failed to save review: {e}")
            return False

    async def get_session_context(self) -> str:
        """
        获取当前会话的所有记忆上下文（用于 LLM 提示）

        Returns:
            格式化的记忆上下文文本
        """
        try:
            # 获取所有会话记忆
            items = await self.chroma.get_by_session(self.session_id)

            if not items:
                return ""

            # 按类型分组
            by_type: Dict[str, List[MemoryItem]] = {}
            for item in items:
                if item.memory_type not in by_type:
                    by_type[item.memory_type] = []
                by_type[item.memory_type].append(item)

            # 格式化输出
            parts = [f"## 当前会话记忆 (ID: {self.session_id})"]

            # Brief
            if MemoryType.SESSION_BRIEF.value in by_type:
                parts.append("\n### Brief")
                for item in by_type[MemoryType.SESSION_BRIEF.value]:
                    parts.append(f"- {item.content}")

            # Plan
            if MemoryType.SESSION_PLAN.value in by_type:
                parts.append("\n### 内容方案")
                for item in by_type[MemoryType.SESSION_PLAN.value]:
                    parts.append(f"- {item.content[:200]}..." if len(item.content) > 200 else f"- {item.content}")

            # Generated
            if MemoryType.SESSION_GENERATED.value in by_type:
                parts.append("\n### 已生成内容")
                for item in by_type[MemoryType.SESSION_GENERATED.value]:
                    item_type = item.metadata.get("item_type", "unknown")
                    content_preview = item.content[:100] + "..." if len(item.content) > 100 else item.content
                    parts.append(f"- [{item_type}] {content_preview}")

            # Feedback
            if MemoryType.SESSION_FEEDBACK.value in by_type:
                parts.append("\n### 用户反馈")
                for item in by_type[MemoryType.SESSION_FEEDBACK.value]:
                    fb_type = item.metadata.get("feedback_type", "general")
                    parts.append(f"- [{fb_type}] {item.content}")

            # Review
            if MemoryType.SESSION_REVIEW.value in by_type:
                parts.append("\n### 审核结果")
                for item in by_type[MemoryType.SESSION_REVIEW.value]:
                    reviewer = item.metadata.get("reviewer", "unknown")
                    parts.append(f"- [{reviewer}] {item.content}")

            return "\n".join(parts)

        except Exception as e:
            print(f"Failed to get session context: {e}")
            return ""

    async def get_recent_items(self, limit: int = 5, memory_type: Optional[str] = None) -> List[MemoryItem]:
        """
        获取最近的记忆条目

        Args:
            limit: 返回数量限制
            memory_type: 可选的类型过滤

        Returns:
            记忆条目列表
        """
        try:
            items = await self.chroma.get_by_session(self.session_id)

            # 按时间排序（假设 created_at 存在）
            if items:
                items.sort(key=lambda x: x.created_at, reverse=True)

            # 应用类型过滤
            if memory_type:
                items = [item for item in items if item.memory_type == memory_type]

            return items[:limit]
        except Exception as e:
            print(f"Failed to get recent items: {e}")
            return []

    async def search_session(self, query_vector: List[float], n: int = 5) -> List[SearchResult]:
        """
        在当前会话记忆中搜索

        Args:
            query_vector: 查询向量
            n: 返回数量

        Returns:
            搜索结果列表
        """
        try:
            return await self.chroma.search(
                query_vector=query_vector,
                n=n,
                memory_type=MemoryType.SESSION_BRIEF.value,  # 主要搜索 Brief
                session_id=self.session_id,
                user_id=self.user_id
            )
        except Exception as e:
            print(f"Failed to search session: {e}")
            return []

    async def clear_session(self) -> bool:
        """
        清除会话记忆（会话结束后调用）

        注意：通常在清除前应该先迁移重要记忆到长期记忆

        Returns:
            是否成功
        """
        try:
            return await self.chroma.delete_by_session(self.session_id)
        except Exception as e:
            print(f"Failed to clear session: {e}")
            return False

    def _brief_to_text(self, brief) -> str:
        """将 Brief 对象转换为文本"""
        try:
            parts = [f"[Brief - {brief.goal.value if hasattr(brief.goal, 'value') else brief.goal}]"]
            parts.append(f"风格: {brief.style}")

            if brief.keywords:
                parts.append(f"关键词: {', '.join(brief.keywords)}")

            if brief.must_include:
                parts.append(f"必须包含: {', '.join(brief.must_include)}")

            if brief.target_audience:
                parts.append(f"目标受众: {brief.target_audience}")

            if brief.image_style:
                parts.append(f"配图风格: {brief.image_style}")

            parts.append(f"需要视频: {'是' if brief.need_video else '否'}")
            parts.append(f"需要配音: {'是' if brief.need_voiceover else '否'}")

            if brief.reference_materials:
                parts.append(f"参考素材数量: {len(brief.reference_materials)}")

            if brief.raw_input:
                parts.append(f"\n原始需求:\n{brief.raw_input[:500]}...")

            return "\n".join(parts)
        except Exception:
            return str(brief)
