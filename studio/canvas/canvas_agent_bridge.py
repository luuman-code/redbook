"""
CanvasAgentBridge - 画板与 Agent 的桥接层

负责画板操作与 CanvasAgent 之间的通信和状态同步。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from .canvas_core import CanvasCore, CanvasOperation, CanvasSnapshot, SelectionRegion
from .canvas_agent import CanvasAgent, CanvasSession, AgentResponse

logger = logging.getLogger(__name__)


@dataclass
class PendingOperation:
    """待处理的画板操作"""
    operation: CanvasOperation
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


class CanvasAgentBridge:
    """
    画板与 Agent 的桥接层

    职责：
    1. 接收画板操作并发送到 Agent 处理
    2. 批量操作节流处理
    3. 将 Agent 的操作应用到画板
    4. 维护操作同步状态
    """

    def __init__(
        self,
        canvas_core: CanvasCore,
        agent: CanvasAgent,
        throttle_ms: int = 100,
    ):
        """
        初始化 CanvasAgentBridge

        Args:
            canvas_core: 画板核心实例
            agent: CanvasAgent 实例（不是 XiaohongshuAgent）
            throttle_ms: 批量操作节流时间（毫秒）
        """
        self.canvas = canvas_core
        self.agent = agent
        self.throttle_ms = throttle_ms

        # 待处理的画板操作队列
        self.pending_operations: List[PendingOperation] = []

        # 操作锁
        self._operation_lock = asyncio.Lock()

        # 回调函数
        self._on_agent_action_callbacks: List[Callable] = []

        # 节流任务
        self._throttle_task: Optional[asyncio.Task] = None

        # 注册画板变更回调
        self.canvas.on_change(self._on_canvas_change)

    def _on_canvas_change(self, operation: Optional[CanvasOperation] = None) -> None:
        """
        画板变更回调

        Args:
            operation: 触发变更的操作
        """
        if operation:
            logger.debug(f"Canvas changed: {operation.type} on {len(operation.target_ids)} elements")

    async def send_operation(self, op: CanvasOperation) -> AgentResponse:
        """
        发送操作到 Agent 处理

        Args:
            op: 画板操作

        Returns:
            AgentResponse
        """
        async with self._operation_lock:
            # 如果是用户操作，添加到待处理队列
            if op.creator == "user":
                pending = PendingOperation(operation=op)
                self.pending_operations.append(pending)

                # 如果没有正在运行的节流任务，启动一个新的
                if self._throttle_task is None or self._throttle_task.done():
                    self._throttle_task = asyncio.create_task(self._process_throttled_operations())

                # 等待处理完成
                await asyncio.sleep(self.throttle_ms / 1000)

                # 尝试获取处理结果
                # 注意：这里简化处理，实际应该通过更复杂的机制传递结果
                return AgentResponse(
                    success=True,
                    message="操作已发送给 Agent",
                )
            else:
                # Agent 自己的操作不需要发送回去
                return AgentResponse(
                    success=True,
                    message="Agent 操作跳过",
                )

    async def send_batch(
        self,
        ops: List[CanvasOperation],
        throttle_ms: Optional[int] = None,
    ) -> List[AgentResponse]:
        """
        批量发送操作（节流）

        Args:
            ops: 操作列表
            throttle_ms: 节流时间（毫秒），默认使用初始化时的值

        Returns:
            AgentResponse 列表
        """
        effective_throttle = throttle_ms or self.throttle_ms

        # 添加到待处理队列
        async with self._operation_lock:
            for op in ops:
                pending = PendingOperation(operation=op)
                self.pending_operations.append(pending)

        # 等待节流时间
        await asyncio.sleep(effective_throttle / 1000)

        # 处理所有待处理的操作
        results = []
        async with self._operation_lock:
            for pending in self.pending_operations:
                result = await self._process_single_operation(pending.operation)
                results.append(result)
            self.pending_operations.clear()

        return results

    async def _process_throttled_operations(self) -> None:
        """处理节流操作"""
        try:
            await asyncio.sleep(self.throttle_ms / 1000)

            async with self._operation_lock:
                if not self.pending_operations:
                    return

                # 合并多个操作（如果有）
                operations_to_process = self.pending_operations.copy()
                self.pending_operations.clear()

            # 依次处理每个操作
            for pending in operations_to_process:
                await self._process_single_operation(pending.operation)

        except Exception as e:
            logger.error(f"Error processing throttled operations: {e}", exc_info=True)
        finally:
            self._throttle_task = None

    async def _process_single_operation(self, op: CanvasOperation) -> AgentResponse:
        """
        处理单个操作

        Args:
            op: 画板操作

        Returns:
            AgentResponse
        """
        try:
            # 构建上下文信息
            context = self._build_operation_context(op)

            # 如果是选择操作，先执行
            if op.type == "lasso_select" or op.type == "element_select":
                result = await self.canvas.execute_operation(op)
                if not result.success:
                    return AgentResponse(success=False, error=result.error or "选择操作失败")

            # 获取画板快照
            snapshot = self.canvas.get_snapshot()

            # 构建发送给 Agent 的消息
            user_message = self._build_user_message(op, snapshot)

            # 调用 Agent 处理
            response = await self.agent.think(user_message, context)

            return response

        except Exception as e:
            logger.error(f"Error processing operation: {e}", exc_info=True)
            return AgentResponse(success=False, error=str(e))

    def _build_operation_context(self, op: CanvasOperation) -> Dict[str, Any]:
        """
        构建操作上下文

        Args:
            op: 画板操作

        Returns:
            上下文字典
        """
        return {
            "canvas_id": self.canvas.canvas_id,
            "operation_type": op.type,
            "target_ids": op.target_ids,
            "timestamp": op.timestamp.isoformat() if hasattr(op.timestamp, 'isoformat') else op.timestamp,
        }

    def _build_user_message(self, op: CanvasOperation, snapshot: CanvasSnapshot) -> str:
        """
        构建发送给 Agent 的用户消息

        Args:
            op: 画板操作
            snapshot: 画板快照

        Returns:
            用户消息字符串
        """
        # 根据操作类型构建消息
        if op.type == "lasso_select":
            element_count = len(op.target_ids)
            return f"用户进行了自由框选，选中了 {element_count} 个元素。"
        elif op.type == "element_select":
            element_count = len(op.target_ids)
            return f"用户选择了 {element_count} 个元素。"
        elif op.type == "create":
            return f"用户创建了新的 {op.after_state.get('element', {}).get('type', '元素')}。"
        elif op.type == "delete":
            return f"用户删除了 {len(op.target_ids)} 个元素。"
        elif op.type == "move":
            delta = op.after_state.get("delta", {})
            return f"用户移动了元素，偏移量: x={delta.get('x', 0)}, y={delta.get('y', 0)}。"
        elif op.type == "update":
            return f"用户修改了 {len(op.target_ids)} 个元素的属性。"
        else:
            return f"用户执行了操作: {op.type}"

    def apply_agent_actions(self, actions: List[CanvasOperation]) -> List[str]:
        """
        应用 Agent 执行的操作到画板

        Args:
            actions: Agent 操作列表

        Returns:
            成功应用的元素 ID 列表
        """
        applied_ids = []

        for action in actions:
            try:
                # 确保操作创建者是 agent
                action.creator = "agent"
                result = asyncio.run(self.canvas.execute_operation(action))
                if result.success:
                    applied_ids.extend(result.affected_ids)
            except Exception as e:
                logger.error(f"Failed to apply agent action: {e}", exc_info=True)

        return applied_ids

    async def apply_agent_actions_async(self, actions: List[CanvasOperation]) -> List[str]:
        """
        异步应用 Agent 执行的操作到画板

        Args:
            actions: Agent 操作列表

        Returns:
            成功应用的元素 ID 列表
        """
        applied_ids = []

        for action in actions:
            try:
                # 确保操作创建者是 agent
                action.creator = "agent"
                result = await self.canvas.execute_operation(action)
                if result.success:
                    applied_ids.extend(result.affected_ids)
            except Exception as e:
                logger.error(f"Failed to apply agent action: {e}", exc_info=True)

        return applied_ids

    def on_agent_action(self, callback: Callable) -> None:
        """
        注册 Agent 操作回调

        Args:
            callback: 回调函数，签名为 (actions: List[CanvasOperation]) -> None
        """
        self._on_agent_action_callbacks.append(callback)

    def trigger_agent_action_callbacks(self, actions: List[CanvasOperation]) -> None:
        """
        触发 Agent 操作回调

        Args:
            actions: Agent 操作列表
        """
        for callback in self._on_agent_action_callbacks:
            try:
                callback(actions)
            except Exception as e:
                logger.error(f"Error in agent action callback: {e}", exc_info=True)

    def get_pending_count(self) -> int:
        """
        获取待处理操作数量

        Returns:
            待处理操作数量
        """
        return len(self.pending_operations)

    async def wait_for_processing(self, timeout_ms: int = 5000) -> bool:
        """
        等待所有待处理操作完成

        Args:
            timeout_ms: 超时时间（毫秒）

        Returns:
            是否所有操作都已处理完成
        """
        try:
            start_time = asyncio.get_event_loop().time()
            timeout_sec = timeout_ms / 1000

            while len(self.pending_operations) > 0:
                if asyncio.get_event_loop().time() - start_time > timeout_sec:
                    return False
                await asyncio.sleep(0.01)

            return True
        except Exception as e:
            logger.error(f"Error waiting for processing: {e}", exc_info=True)
            return False

    def clear_pending(self) -> None:
        """清空待处理操作队列"""
        self.pending_operations.clear()
