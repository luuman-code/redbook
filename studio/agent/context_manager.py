"""
AgentContextManagementMixin - Agent 上下文管理混入类

为 XiaohongshuAgent 提供工作窗口上下文管理功能：
- 滑动窗口
- 消息摘要
- 归档功能
"""

import logging
from typing import Any, Dict, List, Optional

from studio.core.context_manager import (
    ContextManager,
    ContextManagerConfig,
    SlidingWindowMode,
)

logger = logging.getLogger(__name__)


class AgentContextManagementMixin:
    """
    Agent 上下文管理混入类

    使用方式：
    class XiaohongshuAgent(AgentContextManagementMixin):
        def __init__(self, ...):
            self._init_context_manager(config)
    """

    def _init_context_manager(
        self,
        max_messages: int = 50,
        sliding_window_mode: str = "hybrid",
        llm_client=None,
        memory_manager=None
    ) -> None:
        """
        初始化上下文管理器

        Args:
            max_messages: 最大消息数
            sliding_window_mode: 滑动窗口模式 (simple/summary/hybrid)
            llm_client: LLM 客户端（用于生成摘要）
            memory_manager: 记忆管理器（用于归档存储）
        """
        # 转换模式字符串到枚举
        mode = SlidingWindowMode(sliding_window_mode)

        config = ContextManagerConfig(
            max_messages=max_messages,
            sliding_window_mode=mode,
        )

        self.context_manager = ContextManager(
            config=config,
            llm_client=llm_client,
            memory_manager=memory_manager
        )

        # 归档消息收集
        self._archived_messages: List[Any] = []

        logger.info(
            f"[ContextManagement] Initialized with mode={mode.value}, "
            f"max_messages={max_messages}"
        )

    def _should_trim_messages(self) -> bool:
        """
        检查是否需要裁剪消息

        Returns:
            是否需要裁剪
        """
        if not hasattr(self, 'context_manager'):
            return False

        return self.context_manager._should_trim_messages(self.messages)

    async def _trim_and_archive_messages(self, session_id: str) -> None:
        """
        裁剪消息并归档旧消息

        在对话结束后调用，将超出限制的旧消息进行摘要或归档。
        """
        if not hasattr(self, 'context_manager'):
            return

        if not self._should_trim_messages():
            return

        try:
            processed_messages, archived = await self.context_manager.process_messages(
                self.messages,
                session_id
            )

            # 更新消息列表
            old_count = len(self.messages)
            self.messages = processed_messages
            new_count = len(self.messages)

            # 收集归档消息
            if archived:
                self._archived_messages.extend(archived)

                # 存入向量数据库
                if self.context_manager.memory_manager:
                    for msg in archived:
                        await self.context_manager.memory_manager.archive_message(
                            original_content=msg.original_content,
                            summary=msg.summary,
                            metadata=msg.metadata
                        )

            logger.info(
                f"[ContextManagement] Trimmed messages: "
                f"{old_count} -> {new_count}, "
                f"{len(archived)} archived"
            )

        except Exception as e:
            logger.error(f"[ContextManagement] Failed to trim messages: {e}")

    def get_context_stats(self) -> Dict[str, Any]:
        """
        获取上下文统计信息

        Returns:
            统计信息字典
        """
        if not hasattr(self, 'context_manager'):
            return {"error": "Context manager not initialized"}

        return self.context_manager.get_stats(self.messages)

    def get_archived_messages(self) -> List[Any]:
        """
        获取归档消息列表

        Returns:
            归档消息列表
        """
        if not hasattr(self, 'context_manager'):
            return []

        return self.context_manager.get_archived_messages()
