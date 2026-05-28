"""
AgentMessageStore - Agent 消息分块存储管理器

关键设计：工作模式下使用 _working_stream 维护 assistant/tool 的交错时序，
避免简单拼接导致 tool_call_id 无法匹配的问题。

文件路径: studio/agent/message_store.py
"""

from datetime import datetime
from enum import Enum
import uuid
from typing import Any, Dict, List, Optional

from studio.models.message import Message


class AgentMode(Enum):
    """Agent 工作模式"""
    DAILY = "daily"           # 日常对话模式（默认）
    PLANNING = "planning"     # 规划模式
    WORKING = "working"        # 工作模式


class AgentMessageStore:
    """Agent 消息分块存储

    System 消息分类管理，组装时动态拼接，不持久化 system_messages 列表。

    消息分块：
    - system_base: 技能目录等不变内容（只初始化一次）
    - system_context: 画布状态等动态内容（随操作更新）
    - system_mode: 当前模式 prompt（只在组装时注入，不持久化）
    - user_messages: 用户消息块
    - assistant_messages: 助手消息块
    - tool_messages: 工具消息块
    - _current_plan: 存储当前计划文本（非消息）
    - _working_stream: 工作模式专用，维护 assistant/tool 交错顺序
    """

    def __init__(self):
        # System 消息分类存储
        self.system_base: str = ""      # 技能目录等不变内容
        self.system_context: str = ""   # 画布状态等动态内容

        # 用户/助手/工具消息
        self.user_messages: List[Message] = []
        self.assistant_messages: List[Message] = []
        self.tool_messages: List[Message] = []

        # 当前计划（非消息，字符串）
        self._current_plan: Optional[str] = None

        # 工作模式专用：维护 assistant/tool 交错顺序
        # 仅在 WORKING 模式下使用，确保 tool_call_id 时序正确
        self._working_stream: List[Message] = []

        # 用户确认消息（只在工作模式使用）
        self._user_confirmation: Optional[Message] = None

        # 当前模式
        self._current_mode: AgentMode = AgentMode.DAILY

    @property
    def current_mode(self) -> AgentMode:
        """获取当前模式"""
        return self._current_mode

    @property
    def current_plan(self) -> Optional[str]:
        """获取当前计划"""
        return self._current_plan

    def set_mode(self, mode: AgentMode):
        """设置当前模式"""
        self._current_mode = mode

    def set_plan(self, plan_content: str):
        """设置当前计划"""
        self._current_plan = plan_content

    def set_system_base(self, content: str):
        """设置系统基础内容（技能目录等不变信息）"""
        self.system_base = content

    def set_system_context(self, content: str):
        """设置系统上下文内容（画布状态等动态信息）"""
        self.system_context = content

    def set_user_confirmation(self, message: Message):
        """保存用户确认消息（工作模式第一条 user 消息）"""
        self._user_confirmation = message

    def get_user_confirmation(self) -> Optional[Message]:
        """获取用户确认消息"""
        return self._user_confirmation

    def add_message(self, message: Message):
        """根据 role 添加到对应块，并维护工作流顺序

        Args:
            message: 要添加的消息
        """
        if message.role == "user":
            self.user_messages.append(message)
        elif message.role == "assistant":
            # 【关键】工作模式下只加入 _working_stream，不加入 assistant_messages
            # 这样返回日常模式时，工作阶段的消息不会混入
            if self._current_mode == AgentMode.WORKING:
                self._working_stream.append(message)
            else:
                self.assistant_messages.append(message)
        elif message.role == "tool":
            # 【关键】工作模式下只加入 _working_stream，不加入 tool_messages
            if self._current_mode == AgentMode.WORKING:
                self._working_stream.append(message)
            else:
                self.tool_messages.append(message)
        # system 消息不再通过 add_message 添加（使用字符串存储）

    def build_messages(self, mode: AgentMode) -> List[Message]:
        """根据模式组装消息

        Args:
            mode: 目标模式

        Returns:
            组装后的消息列表
        """
        messages = []

        # 【关键】组装完整的 system prompt
        system_content = self._build_system_prompt(mode)
        messages.append(Message(
            message_id=str(uuid.uuid4()),
            role="system",
            content=system_content
        ))

        if mode == AgentMode.PLANNING:
            # 规划模式：user + assistant（按时间顺序交错）
            messages.extend(self._interleave_user_assistant())

        elif mode == AgentMode.WORKING:
            # 【关键】工作模式：user_confirmation + _working_stream
            # 用户确认消息（明确授权）
            if self._user_confirmation:
                messages.append(self._user_confirmation)
            messages.extend(self._working_stream)  # assistant + tool 交错顺序

        elif mode == AgentMode.DAILY:
            # 日常模式：user + assistant（对话历史）
            messages.extend(self._interleave_user_assistant())

        return messages

    def _interleave_user_assistant(self) -> List[Message]:
        """按时间顺序交错 user 和 assistant 消息

        Returns:
            交错后的消息列表
        """
        # 将所有消息合并后按时间戳排序
        all_messages = self.user_messages + self.assistant_messages
        # 按时间戳和 message_id 排序，确保稳定
        #兼容没有 timestamp 的 Message 对象
        def get_sort_key(m):
            ts = getattr(m, 'timestamp', None)
            msg_id = getattr(m, 'message_id', None)
            return (ts if ts else datetime.min, msg_id if msg_id else '')
        all_messages.sort(key=get_sort_key)
        return all_messages

    def _build_system_prompt(self, mode: AgentMode) -> str:
        """组装当前模式的完整 system prompt

        组成结构：
        [system_base] + [system_mode] + [system_context]

        Args:
            mode: 目标模式

        Returns:
            完整的 system prompt
        """
        from studio.canvas.canvas_prompt import (
            DAILY_SYSTEM_PROMPT,
            PLANNING_SYSTEM_PROMPT,
            WORKING_SYSTEM_PROMPT,
        )
        import logging
        logger = logging.getLogger("studio")

        parts = []

        # 1. 基础信息（不变）
        if self.system_base:
            parts.append(self.system_base)

        # 2. 模式 prompt（动态）
        if mode == AgentMode.DAILY:
            parts.append(DAILY_SYSTEM_PROMPT)
        elif mode == AgentMode.PLANNING:
            parts.append(PLANNING_SYSTEM_PROMPT)
        elif mode == AgentMode.WORKING:
            plan_content = self._current_plan or "（无计划）"
            parts.append(WORKING_SYSTEM_PROMPT.format(plan_content=plan_content))

        # 3. 上下文信息（动态）
        if self.system_context:
            parts.append(self.system_context)
            logger.debug(f"[MessageStore] system_context appended, length: {len(self.system_context)}")
            # 检查是否包含选择区域边界
            if "selection_x_start" in self.system_context or "选择区域" in self.system_context:
                logger.info(f"[MessageStore] system_context contains selection info")
        else:
            logger.warning(f"[MessageStore] system_context is empty or None!")

        result = "\n\n".join(parts)
        logger.debug(f"[MessageStore] _build_system_prompt total length: {len(result)}")
        return result

    def clear_working_stream(self):
        """清空工作流（工作模式退出时调用）"""
        self._working_stream.clear()

    def clear_working_messages(self):
        """清空工作模式消息（保留当前计划）

        清空 assistant_messages 和 tool_messages，
        但保留 _current_plan 以便后续使用。
        """
        self.assistant_messages.clear()
        self.tool_messages.clear()

    def clear_user_confirmation(self):
        """清空用户确认消息"""
        self._user_confirmation = None

    def clear_planning_messages(self):
        """清空规划相关消息（进入新规划时调用）"""
        # 保留 user 和 assistant 历史用于规划上下文
        # 但清空工作流
        self._working_stream.clear()

    def clear_except_system(self):
        """清空除系统消息外的所有消息

        用于"新建会话"时重置。
        """
        self.user_messages.clear()
        self.assistant_messages.clear()
        self.tool_messages.clear()
        self._working_stream.clear()
        self._current_plan = None
        self._user_confirmation = None

    def trim_for_daily_mode(self, max_pairs: int = 20):
        """裁剪日常模式历史，保留最近 N 轮对话

        Args:
            max_pairs: 最大保留的对话轮数（每轮包含 user + assistant）
        """
        # 由于 sort 不保证相同 key 的稳定性，我们采用不同的策略：
        # 分别保留 user 和 assistant 的最后 max_pairs 条消息
        # 这样可以确保每种角色都保留正确数量的消息

        if len(self.user_messages) > max_pairs:
            self.user_messages = self.user_messages[-max_pairs:]

        if len(self.assistant_messages) > max_pairs:
            self.assistant_messages = self.assistant_messages[-max_pairs:]

    def clear_all_messages(self):
        """清空所有消息（仅在"新建会话"时调用）"""
        self.user_messages.clear()
        self.assistant_messages.clear()
        self.tool_messages.clear()
        self._working_stream.clear()
        self._current_plan = None
        self._user_confirmation = None

    def get_message_count(self) -> Dict[str, int]:
        """获取各消息类型的数量

        Returns:
            各消息类型的数量统计
        """
        return {
            "user": len(self.user_messages),
            "assistant": len(self.assistant_messages),
            "tool": len(self.tool_messages),
            "working_stream": len(self._working_stream),
        }

    def get_all_messages(self) -> List[Message]:
        """获取所有消息（用于调试）

        Returns:
            所有消息的列表
        """
        return self.user_messages + self.assistant_messages + self.tool_messages

    def trim_messages(self, max_per_block: Dict[str, int]):
        """按块裁剪消息

        Args:
            max_per_block: 每个块的最大消息数，如 {"user": 20, "assistant": 20}
        """
        for block_name, max_count in max_per_block.items():
            block = getattr(self, f"{block_name}_messages", None)
            if block and len(block) > max_count:
                # 保留最近的消息
                setattr(self, f"{block_name}_messages", block[-max_count:])

    def trim_for_mode(self, mode: AgentMode):
        """根据模式执行特定的裁剪策略

        Args:
            mode: 当前模式
        """
        if mode == AgentMode.DAILY:
            # 日常模式：保留最近 20 轮对话
            self.trim_for_daily_mode(max_pairs=20)
        elif mode == AgentMode.PLANNING:
            # 规划模式：不裁剪，保留完整规划历史
            pass
        elif mode == AgentMode.WORKING:
            # 工作模式：tool_messages 最多保留 50 条
            if len(self.tool_messages) > 50:
                self.tool_messages = self.tool_messages[-50:]
