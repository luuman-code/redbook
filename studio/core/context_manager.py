"""
ContextManager - 工作窗口上下文管理器

职责：
1. 消息数量控制（滑动窗口）
2. 消息摘要生成
3. 旧消息归档到向量数据库
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SlidingWindowMode(str, Enum):
    """滑动窗口模式"""
    SIMPLE = "simple"        # 简单滑动窗口：直接丢弃旧消息
    SUMMARY = "summary"      # 摘要模式：对旧消息生成摘要
    HYBRID = "hybrid"        # 混合模式：保留最近N条，之前的生成摘要


@dataclass
class ArchivedMessage:
    """归档消息结构"""
    original_content: str
    summary: str
    metadata: Dict[str, Any]
    embedding_id: Optional[str] = None
    archived_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_content": self.original_content,
            "summary": self.summary,
            "metadata": self.metadata,
            "embedding_id": self.embedding_id,
            "archived_at": self.archived_at.isoformat(),
        }


@dataclass
class ContextManagerConfig:
    """上下文管理器配置"""
    max_messages: int = 50                      # 最大消息数
    summary_trigger_ratio: float = 0.8           # 触发摘要的消息数比例
    archive_enabled: bool = True                 # 是否启用归档
    sliding_window_mode: SlidingWindowMode = SlidingWindowMode.HYBRID
    keep_system_prompt: bool = True             # 保留系统提示词
    summarize_older_messages: int = 20          # 超过多少条消息时开始摘要更早的消息


class ContextManager:
    """
    工作窗口上下文管理器

    职责：
    1. 消息数量控制（滑动窗口）
    2. 消息摘要生成
    3. 旧消息归档
    """

    def __init__(
        self,
        config: ContextManagerConfig,
        llm_client=None,
        memory_manager=None
    ):
        """
        初始化 ContextManager

        Args:
            config: 上下文管理器配置
            llm_client: LLM客户端（用于生成摘要）
            memory_manager: 记忆管理器（用于归档存储）
        """
        self.config = config
        self.llm = llm_client
        self.memory_manager = memory_manager

        # 归档消息收集
        self._archived_messages: List[ArchivedMessage] = []

        # 摘要缓存 (session_id -> summary)
        self._summary_cache: Dict[str, str] = {}

    async def process_messages(
        self,
        messages: List[Any],
        session_id: str
    ) -> Tuple[List[Any], List[ArchivedMessage]]:
        """
        处理消息列表，执行滑动窗口和归档

        Args:
            messages: 消息列表 (mini_agent.schema.Message)
            session_id: 会话ID

        Returns:
            (processed_messages, archived_messages)
        """
        if len(messages) <= self.config.max_messages:
            return messages, []

        mode = self.config.sliding_window_mode

        if mode == SlidingWindowMode.SIMPLE:
            return self._simple_sliding_window(messages)
        elif mode == SlidingWindowMode.SUMMARY:
            return await self._summary_sliding_window(messages, session_id)
        elif mode == SlidingWindowMode.HYBRID:
            return await self._hybrid_sliding_window(messages, session_id)
        else:
            return messages, []

    def _simple_sliding_window(self, messages: List[Any]) -> Tuple[List[Any], List[ArchivedMessage]]:
        """
        简单滑动窗口：直接丢弃超出限制的旧消息

        参考 CanvasAgent 的实现
        """
        # 保留系统消息
        system_messages = [m for m in messages if m.role == "system"]
        non_system_messages = [m for m in messages if m.role != "system"]

        # 裁剪非系统消息，只保留最近的一批
        kept_messages = non_system_messages[-self.config.max_messages:]

        logger.debug(
            f"[ContextManager] Simple sliding window: "
            f"{len(non_system_messages)} -> {len(kept_messages)} messages"
        )

        return system_messages + kept_messages, []

    async def _summary_sliding_window(
        self,
        messages: List[Any],
        session_id: str
    ) -> Tuple[List[Any], List[ArchivedMessage]]:
        """
        摘要滑动窗口：将超出限制的旧消息汇总为一条摘要
        """
        system_messages = [m for m in messages if m.role == "system"]
        non_system_messages = [m for m in messages if m.role != "system"]

        if len(non_system_messages) <= self.config.max_messages:
            return messages, []

        # 分割消息：最近的要保留，之前的要汇总
        messages_to_summarize = non_system_messages[:-self.config.max_messages]
        messages_to_keep = non_system_messages[-self.config.max_messages:]

        # 生成摘要
        summary = await self._generate_summary(messages_to_summarize, session_id)

        # 创建摘要消息
        summary_content = f"[历史对话摘要]\n{summary}"
        summary_msg = self._create_message(role="system", content=summary_content)

        archived = [
            ArchivedMessage(
                original_content=self._messages_to_text(messages_to_summarize),
                summary=summary,
                metadata={
                    "session_id": session_id,
                    "message_count": len(messages_to_summarize)
                }
            )
        ]

        logger.debug(
            f"[ContextManager] Summary sliding window: "
            f"{len(messages_to_summarize)} messages summarized"
        )

        return system_messages + [summary_msg] + messages_to_keep, archived

    async def _hybrid_sliding_window(
        self,
        messages: List[Any],
        session_id: str
    ) -> Tuple[List[Any], List[ArchivedMessage]]:
        """
        混合滑动窗口：
        - 保留最近 N 条完整消息
        - 对更早的消息进行摘要
        """
        system_messages = [m for m in messages if m.role == "system"]
        non_system_messages = [m for m in messages if m.role != "system"]

        total = len(non_system_messages)
        if total <= self.config.max_messages:
            return messages, []

        # 混合模式：保留最近的，摘要中间的
        # 假设 max_messages=50，我们保留最后40条，摘要前面10条
        keep_count = int(self.config.max_messages * 0.8)  # 保留80%
        summarize_count = total - keep_count  # 摘要的数量

        if summarize_count <= 0:
            return messages, []

        messages_to_summarize = non_system_messages[:summarize_count]
        messages_to_keep = non_system_messages[summarize_count:]

        archived_messages: List[ArchivedMessage] = []

        # 汇总旧消息
        summary = await self._generate_summary(messages_to_summarize, session_id)
        summary_content = f"[更早对话摘要]\n{summary}"
        summary_msg = self._create_message(role="system", content=summary_content)

        archived = ArchivedMessage(
            original_content=self._messages_to_text(messages_to_summarize),
            summary=summary,
            metadata={
                "session_id": session_id,
                "message_count": len(messages_to_summarize)
            }
        )
        archived_messages.append(archived)

        logger.debug(
            f"[ContextManager] Hybrid sliding window: "
            f"{len(messages_to_summarize)} summarized, "
            f"{len(messages_to_keep)} kept"
        )

        return system_messages + [summary_msg] + messages_to_keep, archived_messages

    def _create_message(self, role: str, content: str) -> Any:
        """创建消息对象"""
        # 导入 mini_agent.schema.Message
        from mini_agent.schema import Message
        return Message(role=role, content=content)

    async def _generate_summary(
        self,
        messages: List[Any],
        session_id: str
    ) -> str:
        """
        调用 LLM 生成消息摘要

        Args:
            messages: 需要摘要的消息列表
            session_id: 会话ID（用于缓存）

        Returns:
            摘要文本
        """
        # 检查缓存
        cache_key = f"{session_id}_{len(messages)}"
        if cache_key in self._summary_cache:
            logger.debug(f"[ContextManager] Using cached summary for {cache_key}")
            return self._summary_cache[cache_key]

        if not self.llm:
            return f"[{len(messages)}条旧消息已省略]"

        content = self._messages_to_text(messages)

        prompt = f"""请将以下对话历史总结为一段简洁的摘要，保留关键信息：

{content}

要求：
1. 总结对话的主要话题和用户需求
2. 保留重要的决策和结论
3. 控制在200字以内"""

        try:
            from mini_agent.schema import Message
            response = await self.llm.generate(
                messages=[Message(role="user", content=prompt)],
                tools=None
            )

            summary = response.content if hasattr(response, 'content') else str(response)
            self._summary_cache[cache_key] = summary
            return summary

        except Exception as e:
            logger.error(f"[ContextManager] Failed to generate summary: {e}")
            return f"[{len(messages)}条旧消息摘要失败]"

    def _messages_to_text(self, messages: List[Any]) -> str:
        """
        将消息列表转换为文本

        Args:
            messages: 消息列表

        Returns:
            格式化文本
        """
        lines = []
        for msg in messages:
            role_label = {"user": "用户", "assistant": "助手", "tool": "工具"}.get(msg.role, msg.role)

            # 处理 content，可能是字符串或列表
            if isinstance(msg.content, str):
                content = msg.content
            elif isinstance(msg.content, list):
                # 多模态内容，提取文本部分
                text_parts = []
                for item in msg.content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = "\n".join(text_parts)
            else:
                content = str(msg.content)

            # 截断过长内容
            if len(content) > 500:
                content = content[:500] + "..."

            lines.append(f"{role_label}：{content}")

        return "\n\n".join(lines)

    def _should_trim_messages(self, messages: List[Any]) -> bool:
        """
        检查是否需要裁剪消息

        Args:
            messages: 消息列表

        Returns:
            是否需要裁剪
        """
        non_system_count = sum(1 for m in messages if m.role != "system")
        return non_system_count > self.config.max_messages

    def get_archived_messages(self) -> List[ArchivedMessage]:
        """获取归档消息列表"""
        return self._archived_messages

    def clear_archived_messages(self) -> None:
        """清空归档消息"""
        self._archived_messages.clear()

    def get_stats(self, messages: List[Any]) -> Dict[str, Any]:
        """
        获取上下文统计信息

        Args:
            messages: 当前消息列表

        Returns:
            统计信息字典
        """
        total = len(messages)
        non_system = sum(1 for m in messages if m.role != "system")
        archived = len(self._archived_messages)

        return {
            "total_messages": total,
            "non_system_messages": non_system,
            "archived_messages": archived,
            "max_messages": self.config.max_messages,
            "sliding_window_mode": self.config.sliding_window_mode.value,
            "needs_trim": self._should_trim_messages(messages)
        }
