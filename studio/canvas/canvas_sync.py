"""
CanvasSync - 画板WebSocket同步处理器

提供画板操作的实时同步功能，支持：
1. 客户端操作的广播和确认
2. Agent操作的发送和响应
3. 操作节流策略
4. 多客户端状态同步
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Awaitable

from fastapi import WebSocket

from .canvas_core import CanvasCore, CanvasElement, CanvasOperation, OperationResult
from ..debug_logger import get_logger

logger = get_logger("canvas_sync")


class OperationCategory(Enum):
    """操作分类（用于节流策略）"""
    DRAG = "drag"          # 拖拽/缩放 - 100ms
    TEXT_EDIT = "text_edit" # 文本编辑 - 500ms
    DELETE = "delete"       # 删除/添加 - 立即


# 操作节流策略配置
OPERATION_THROTTLE = {
    OperationCategory.DRAG: 100,       # 拖拽/缩放 - 100ms
    OperationCategory.TEXT_EDIT: 500,   # 文本编辑 - 500ms
    OperationCategory.DELETE: 0,        # 删除/添加 - 立即
}


def get_operation_category(op_type: str) -> OperationCategory:
    """根据操作类型获取分类"""
    if op_type in ("move", "resize", "rotate"):
        return OperationCategory.DRAG
    elif op_type == "text_edit":
        return OperationCategory.TEXT_EDIT
    elif op_type in ("create", "delete", "duplicate", "group", "ungroup"):
        return OperationCategory.DELETE
    else:
        return OperationCategory.TEXT_EDIT  # 默认使用中等节流


@dataclass
class ThrottleEntry:
    """节流条目"""
    client_id: str
    operation_id: str
    operation_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    cancelled: bool = False


@dataclass
class ClientConnection:
    """客户端连接信息"""
    client_id: str
    websocket: WebSocket
    canvas_id: str
    is_agent: bool = False
    subscribed_canvases: Set[str] = field(default_factory=set)
    last_activity: datetime = field(default_factory=datetime.now)


class WSMessageType:
    """WebSocket消息类型常量"""
    # 客户端 -> 服务端
    REPORT_OPERATION = "REPORT_OPERATION"
    SUBSCRIBE_CANVAS = "SUBSCRIBE_CANVAS"
    UNSUBSCRIBE_CANVAS = "UNSUBSCRIBE_CANVAS"
    PING = "PING"

    # 服务端 -> 客户端
    OPERATION_ACK = "OPERATION_ACK"
    SUGGESTION = "SUGGESTION"
    AGENT_ACTION = "AGENT_ACTION"
    CANVAS_UPDATE = "CANVAS_UPDATE"
    PONG = "PONG"
    ERROR = "ERROR"


@dataclass
class WSReportOperation:
    """前端 -> 服务端：报告操作"""
    type: str = WSMessageType.REPORT_OPERATION
    payload: Dict[str, Any] = field(default_factory=dict)
    expect_response: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "payload": self.payload,
            "expect_response": self.expect_response,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WSReportOperation":
        return cls(
            type=data.get("type", WSMessageType.REPORT_OPERATION),
            payload=data.get("payload", {}),
            expect_response=data.get("expect_response", True),
        )


@dataclass
class WSAgentResponse:
    """服务端 -> 前端：Agent响应"""
    type: str  # OPERATION_ACK, SUGGESTION, AGENT_ACTION
    operation_id: str
    actions: Optional[List[Dict[str, Any]]] = None
    content: Optional[str] = None
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "operationId": self.operation_id,
            "success": self.success,
        }
        if self.actions is not None:
            result["actions"] = self.actions
        if self.content is not None:
            result["content"] = self.content
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class CanvasUpdateMessage:
    """服务端 -> 前端：画板更新通知"""
    type: str = WSMessageType.CANVAS_UPDATE
    canvas_id: str = ""
    operation: Optional[Dict[str, Any]] = None
    elements: Optional[List[Dict[str, Any]]] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "canvas_id": self.canvas_id,
            "operation": self.operation,
            "elements": self.elements,
            "timestamp": self.timestamp or datetime.now().isoformat(),
        }


class CanvasSyncHandler:
    """
    画板WebSocket同步处理器

    职责：
    1. 管理客户端连接（用户和Agent）
    2. 处理和广播画板操作
    3. 实现操作节流
    4. 发送操作确认和建议
    """

    def __init__(self, canvas_manager: Optional[Callable[[str], Optional[CanvasCore]]] = None):
        """
        初始化同步处理器

        Args:
            canvas_manager: 获取canvas_core实例的回调函数
        """
        self._clients: Dict[str, ClientConnection] = {}  # client_id -> ClientConnection
        self._canvas_clients: Dict[str, Set[str]] = {}   # canvas_id -> set of client_ids
        self._canvas_manager = canvas_manager
        self._lock = asyncio.Lock()

        # 节流跟踪
        self._throttle_entries: Dict[str, ThrottleEntry] = {}  # client_id+op_type -> entry
        self._throttle_tasks: Dict[str, asyncio.Task] = {}

        # 操作处理回调
        self._operation_handlers: List[Callable[[str, CanvasOperation], Optional[CanvasOperation]]] = []

        # Agent回调
        self._agent_callbacks: List[Callable[[str, CanvasOperation], Awaitable[Optional[CanvasOperation]]]] = []

        logger.debug("CanvasSyncHandler initialized")

    def set_canvas_manager(self, manager: Callable[[str], Optional[CanvasCore]]) -> None:
        """设置canvas_manager回调"""
        self._canvas_manager = manager

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        canvas_id: str,
        is_agent: bool = False,
    ) -> None:
        """
        接受WebSocket连接并注册

        Args:
            websocket: WebSocket连接
            client_id: 客户端ID
            canvas_id: 初始画板ID
            is_agent: 是否为Agent客户端
        """
        await websocket.accept()

        async with self._lock:
            conn = ClientConnection(
                client_id=client_id,
                websocket=websocket,
                canvas_id=canvas_id,
                is_agent=is_agent,
                subscribed_canvases={canvas_id},
            )
            self._clients[client_id] = conn

            # 添加到画板订阅列表
            if canvas_id not in self._canvas_clients:
                self._canvas_clients[canvas_id] = set()
            self._canvas_clients[canvas_id].add(client_id)

        logger.info(
            f"WebSocket connected: client_id={client_id}, canvas_id={canvas_id}, "
            f"is_agent={is_agent}, total_clients={len(self._clients)}"
        )

    async def disconnect(self, client_id: str) -> None:
        """
        断开WebSocket连接

        Args:
            client_id: 客户端ID
        """
        async with self._lock:
            if client_id not in self._clients:
                return

            conn = self._clients[client_id]

            # 从所有订阅的画板中移除
            for canvas_id in conn.subscribed_canvases:
                if canvas_id in self._canvas_clients:
                    self._canvas_clients[canvas_id].discard(client_id)
                    if not self._canvas_clients[canvas_id]:
                        del self._canvas_clients[canvas_id]

            # 取消节流任务
            throttle_keys = [k for k in self._throttle_entries if k.startswith(client_id)]
            for key in throttle_keys:
                if key in self._throttle_entries:
                    self._throttle_entries[key].cancelled = True
                if key in self._throttle_tasks:
                    self._throttle_tasks[key].cancel()

            del self._clients[client_id]

        logger.info(f"WebSocket disconnected: client_id={client_id}, remaining_clients={len(self._clients)}")

    async def handle_operation(self, client_id: str, operation: CanvasOperation) -> bool:
        """
        处理画板操作

        Args:
            client_id: 客户端ID
            operation: 操作对象

        Returns:
            bool: 是否处理成功
        """
        if client_id not in self._clients:
            logger.warning(f"Operation from unknown client: {client_id}")
            return False

        conn = self._clients[client_id]
        canvas_id = conn.canvas_id

        # 检查节流
        throttle_key = f"{client_id}_{operation.type}"
        category = get_operation_category(operation.type)
        throttle_ms = OPERATION_THROTTLE.get(category, 0)

        if throttle_ms > 0:
            # 检查是否有未完成的同类操作
            if throttle_key in self._throttle_entries:
                entry = self._throttle_entries[throttle_key]
                if not entry.cancelled:
                    # 取消前一个节流任务
                    entry.cancelled = True
                    if throttle_key in self._throttle_tasks:
                        self._throttle_tasks[throttle_key].cancel()

                # 合并操作：更新待处理操作
                entry.operation_id = operation.id
                entry.timestamp = datetime.now()

                # 创建新的节流任务
                self._throttle_entries[throttle_key] = ThrottleEntry(
                    client_id=client_id,
                    operation_id=operation.id,
                    operation_type=operation.type,
                )

                async def delayed_broadcast():
                    await asyncio.sleep(throttle_ms / 1000.0)
                    async with self._lock:
                        if not self._throttle_entries.get(throttle_key, ThrottleEntry("", "")).cancelled:
                            await self._do_broadcast(canvas_id, operation)
                            if throttle_key in self._throttle_entries:
                                del self._throttle_entries[throttle_key]
                    if throttle_key in self._throttle_tasks:
                        del self._throttle_tasks[throttle_key]

                self._throttle_tasks[throttle_key] = asyncio.create_task(delayed_broadcast())
                return True

            # 创建新的节流条目
            self._throttle_entries[throttle_key] = ThrottleEntry(
                client_id=client_id,
                operation_id=operation.id,
                operation_type=operation.type,
            )

            # 延迟广播
            async def delayed_broadcast():
                await asyncio.sleep(throttle_ms / 1000.0)
                async with self._lock:
                    if not self._throttle_entries.get(throttle_key, ThrottleEntry("", "")).cancelled:
                        await self._do_broadcast(canvas_id, operation)
                        if throttle_key in self._throttle_entries:
                            del self._throttle_entries[throttle_key]
                if throttle_key in self._throttle_tasks:
                    del self._throttle_tasks[throttle_key]

            self._throttle_tasks[throttle_key] = asyncio.create_task(delayed_broadcast())
            return True
        else:
            # 立即广播
            return await self._do_broadcast(canvas_id, operation)

    async def _do_broadcast(self, canvas_id: str, operation: CanvasOperation) -> bool:
        """执行广播操作"""
        # 获取canvas_core执行操作
        if self._canvas_manager:
            canvas = self._canvas_manager(canvas_id)
            if canvas:
                result = await canvas.execute_operation(operation)
                if not result.success:
                    logger.warning(f"Operation execution failed: {result.error}")
                    return False

        # 广播到所有订阅该画板的客户端（除了发送者）
        message = CanvasUpdateMessage(
            canvas_id=canvas_id,
            operation=operation.to_dict(),
            timestamp=datetime.now().isoformat(),
        )

        await self.broadcast_to_clients(canvas_id, message.to_dict(), exclude_agent=True)

        # 如果有Agent回调，异步处理
        if self._agent_callbacks:
            asyncio.create_task(self._notify_agent(canvas_id, operation))

        return True

    async def _notify_agent(self, canvas_id: str, operation: CanvasOperation) -> None:
        """通知Agent处理操作"""
        for callback in self._agent_callbacks:
            try:
                result = await callback(canvas_id, operation)
                if result:
                    # Agent返回了建议操作
                    await self.send_suggestion(canvas_id, {
                        "original_operation": operation.to_dict(),
                        "suggested_operations": [result.to_dict()] if isinstance(result, CanvasOperation) else result,
                    })
            except Exception as e:
                logger.error(f"Agent callback error: {e}")

    def register_operation_handler(
        self,
        handler: Callable[[str, CanvasOperation], Optional[CanvasOperation]]
    ) -> None:
        """注册操作处理回调"""
        self._operation_handlers.append(handler)

    def register_agent_callback(
        self,
        callback: Callable[[str, CanvasOperation], Awaitable[Optional[CanvasOperation]]]
    ) -> None:
        """注册Agent回调"""
        self._agent_callbacks.append(callback)

    async def broadcast_to_clients(
        self,
        canvas_id: str,
        message: Dict[str, Any],
        exclude_client_id: Optional[str] = None,
        exclude_agent: bool = False,
    ) -> None:
        """
        广播消息到订阅画板的客户端

        Args:
            canvas_id: 画板ID
            message: 消息内容
            exclude_client_id: 排除的客户端ID
            exclude_agent: 是否排除Agent客户端
        """
        if canvas_id not in self._canvas_clients:
            return

        message_data = json.dumps(message)
        dead_clients = []

        async with self._lock:
            client_ids = self._canvas_clients[canvas_id].copy()

        for client_id in client_ids:
            if client_id == exclude_client_id:
                continue

            async with self._lock:
                conn = self._clients.get(client_id)
                if not conn:
                    continue

                # 检查是否排除Agent
                if exclude_agent and conn.is_agent:
                    continue

            try:
                await conn.websocket.send_text(message_data)
                conn.last_activity = datetime.now()
            except Exception as e:
                logger.warning(f"Failed to send to client {client_id}: {e}")
                dead_clients.append(client_id)

        # 清理断开的客户端
        for client_id in dead_clients:
            await self.disconnect(client_id)

    async def send_to_agent(self, canvas_id: str, operation: CanvasOperation) -> bool:
        """
        发送操作到Agent

        Args:
            canvas_id: 画板ID
            operation: 操作对象

        Returns:
            bool: 是否发送成功
        """
        # 查找Agent客户端
        agent_conn: Optional[ClientConnection] = None

        async with self._lock:
            for conn in self._clients.values():
                if conn.is_agent and canvas_id in conn.subscribed_canvases:
                    agent_conn = conn
                    break

        if not agent_conn:
            logger.debug(f"No agent connected for canvas: {canvas_id}")
            return False

        try:
            message = {
                "type": WSMessageType.REPORT_OPERATION,
                "canvas_id": canvas_id,
                "operation": operation.to_dict(),
                "timestamp": datetime.now().isoformat(),
            }
            await agent_conn.websocket.send_text(json.dumps(message))
            agent_conn.last_activity = datetime.now()
            return True
        except Exception as e:
            logger.error(f"Failed to send to agent: {e}")
            return False

    async def send_ack(
        self,
        client_id: str,
        operation_id: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        发送操作确认

        Args:
            client_id: 客户端ID
            operation_id: 操作ID
            success: 是否成功
            error: 错误信息
        """
        if client_id not in self._clients:
            return

        conn = self._clients[client_id]

        response = WSAgentResponse(
            type=WSMessageType.OPERATION_ACK,
            operation_id=operation_id,
            success=success,
            error=error,
        )

        try:
            await conn.websocket.send_text(json.dumps(response.to_dict()))
        except Exception as e:
            logger.warning(f"Failed to send ACK to {client_id}: {e}")

    async def send_suggestion(self, canvas_id: str, suggestion: Dict[str, Any]) -> None:
        """
        发送建议到画板所有客户端

        Args:
            canvas_id: 画板ID
            suggestion: 建议内容
        """
        message = {
            "type": WSMessageType.SUGGESTION,
            "canvas_id": canvas_id,
            "suggestion": suggestion,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast_to_clients(canvas_id, message)

    async def send_agent_action(
        self,
        canvas_id: str,
        operation_id: str,
        actions: List[CanvasOperation],
        content: Optional[str] = None,
    ) -> None:
        """
        发送Agent操作到画板所有客户端

        Args:
            canvas_id: 画板ID
            operation_id: 操作ID
            actions: Agent执行的操作列表
            content: 额外内容
        """
        message = WSAgentResponse(
            type=WSMessageType.AGENT_ACTION,
            operation_id=operation_id,
            actions=[a.to_dict() for a in actions],
            content=content,
        )
        await self.broadcast_to_clients(canvas_id, message.to_dict())

    async def subscribe_canvas(self, client_id: str, canvas_id: str) -> bool:
        """
        订阅画板

        Args:
            client_id: 客户端ID
            canvas_id: 画板ID

        Returns:
            bool: 是否成功
        """
        if client_id not in self._clients:
            return False

        async with self._lock:
            conn = self._clients[client_id]
            conn.subscribed_canvases.add(canvas_id)

            if canvas_id not in self._canvas_clients:
                self._canvas_clients[canvas_id] = set()
            self._canvas_clients[canvas_id].add(client_id)

        logger.info(f"Client {client_id} subscribed to canvas {canvas_id}")
        return True

    async def unsubscribe_canvas(self, client_id: str, canvas_id: str) -> bool:
        """
        取消订阅画板

        Args:
            client_id: 客户端ID
            canvas_id: 画板ID

        Returns:
            bool: 是否成功
        """
        if client_id not in self._clients:
            return False

        async with self._lock:
            conn = self._clients[client_id]
            conn.subscribed_canvases.discard(canvas_id)

            if canvas_id in self._canvas_clients:
                self._canvas_clients[canvas_id].discard(client_id)

        logger.info(f"Client {client_id} unsubscribed from canvas {canvas_id}")
        return True

    async def switch_canvas(self, client_id: str, canvas_id: str) -> bool:
        """
        切换客户端当前画板

        Args:
            client_id: 客户端ID
            canvas_id: 画板ID

        Returns:
            bool: 是否成功
        """
        if client_id not in self._clients:
            return False

        async with self._lock:
            conn = self._clients[client_id]
            old_canvas_id = conn.canvas_id
            conn.canvas_id = canvas_id

            # 订阅新画板
            conn.subscribed_canvases.add(canvas_id)
            if canvas_id not in self._canvas_clients:
                self._canvas_clients[canvas_id] = set()
            self._canvas_clients[canvas_id].add(client_id)

            # 从旧画板移除订阅
            if old_canvas_id != canvas_id:
                self._canvas_clients[old_canvas_id].discard(client_id)
                conn.subscribed_canvases.discard(old_canvas_id)

        logger.info(f"Client {client_id} switched from canvas {old_canvas_id} to {canvas_id}")
        return True

    def get_client_count(self, canvas_id: Optional[str] = None) -> int:
        """
        获取客户端数量

        Args:
            canvas_id: 画板ID（可选，不提供则返回总数）

        Returns:
            int: 客户端数量
        """
        if canvas_id:
            return len(self._canvas_clients.get(canvas_id, set()))
        return len(self._clients)

    def get_canvas_subscribers(self, canvas_id: str) -> List[str]:
        """
        获取画板订阅者ID列表

        Args:
            canvas_id: 画板ID

        Returns:
            List[str]: 订阅者ID列表
        """
        return list(self._canvas_clients.get(canvas_id, set()))

    async def handle_message(self, client_id: str, message: Dict[str, Any]) -> None:
        """
        处理收到的WebSocket消息

        Args:
            client_id: 客户端ID
            message: 消息内容
        """
        msg_type = message.get("type")

        if msg_type == WSMessageType.REPORT_OPERATION:
            payload = message.get("payload", {})
            if isinstance(payload, dict):
                operation = CanvasOperation.from_dict(payload)
                await self.handle_operation(client_id, operation)

                # 发送确认
                if message.get("expect_response", True):
                    await self.send_ack(client_id, operation.id)

        elif msg_type == WSMessageType.SUBSCRIBE_CANVAS:
            canvas_id = message.get("canvas_id")
            if canvas_id:
                await self.subscribe_canvas(client_id, canvas_id)

        elif msg_type == WSMessageType.UNSUBSCRIBE_CANVAS:
            canvas_id = message.get("canvas_id")
            if canvas_id:
                await self.unsubscribe_canvas(client_id, canvas_id)

        elif msg_type == WSMessageType.PING:
            if client_id in self._clients:
                try:
                    await self._clients[client_id].websocket.send_text(json.dumps({
                        "type": WSMessageType.PONG,
                        "timestamp": datetime.now().isoformat(),
                    }))
                except Exception:
                    pass

        else:
            logger.warning(f"Unknown message type: {msg_type}")


# 全局同步处理器实例
_sync_handler: Optional[CanvasSyncHandler] = None


def get_canvas_sync_handler() -> CanvasSyncHandler:
    """获取全局CanvasSyncHandler实例"""
    global _sync_handler
    if _sync_handler is None:
        _sync_handler = CanvasSyncHandler()
    return _sync_handler


def set_canvas_sync_handler(handler: CanvasSyncHandler) -> None:
    """设置全局CanvasSyncHandler实例"""
    global _sync_handler
    _sync_handler = handler
