"""
WebSocket Manager - Manages WebSocket connections per session for real-time progress updates
"""

import asyncio
import json
from typing import Dict, Set, Optional, Callable, Awaitable
from fastapi import WebSocket
from ..debug_logger import get_logger

logger = get_logger("websocket_manager")


class ProgressEvent:
    """Progress event structure"""

    def __init__(
        self,
        event_type: str,
        item_id: Optional[str] = None,
        item_type: Optional[str] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
        content: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        self.event_type = event_type
        self.item_id = item_id
        self.item_type = item_type
        self.current = current
        self.total = total
        self.message = message
        self.content = content
        self.error = error
        self.metadata = metadata

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        result = {"type": self.event_type}
        if self.item_id is not None:
            result["item_id"] = self.item_id
        if self.item_type is not None:
            result["item_type"] = self.item_type
        if self.current is not None:
            result["current"] = self.current
        if self.total is not None:
            result["total"] = self.total
        if self.message is not None:
            result["message"] = self.message
        if self.content is not None:
            result["content"] = self.content
        if self.error is not None:
            result["error"] = self.error
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def generation_start(cls, item_id: str, item_type: str, message: str) -> "ProgressEvent":
        """Event: generation_start (legacy, use item_start for frontend compatibility)"""
        return cls(
            event_type="generation_start",
            item_id=item_id,
            item_type=item_type,
            message=message,
        )

    @classmethod
    def generation_progress(cls, current: int, total: int, message: str) -> "ProgressEvent":
        """Event: generation_progress (legacy, use progress for frontend compatibility)"""
        return cls(
            event_type="generation_progress",
            current=current,
            total=total,
            message=message,
        )

    @classmethod
    def generation_complete(cls, item_id: str, content: str) -> "ProgressEvent":
        """Event: generation_complete (legacy, use item_complete for frontend compatibility)"""
        return cls(
            event_type="generation_complete",
            item_id=item_id,
            content=content,
        )

    @classmethod
    def generation_error(cls, item_id: str, error: str) -> "ProgressEvent":
        """Event: generation_error (legacy, use item_error for frontend compatibility)"""
        return cls(
            event_type="generation_error",
            item_id=item_id,
            error=error,
        )

    # Frontend-compatible event types
    @classmethod
    def item_start(cls, item_id: str, item_name: str = None, message: str = None) -> "ProgressEvent":
        """Event: item_start - frontend compatible"""
        return cls(
            event_type="item_start",
            item_id=item_id,
            item_type=item_name,
            message=message or f"开始生成 {item_name}" if item_name else "开始生成",
        )

    @classmethod
    def item_complete(cls, item_id: str, content: str = None) -> "ProgressEvent":
        """Event: item_complete - frontend compatible"""
        return cls(
            event_type="item_complete",
            item_id=item_id,
            content=content,
        )

    @classmethod
    def item_error(cls, item_id: str, error: str) -> "ProgressEvent":
        """Event: item_error - frontend compatible"""
        return cls(
            event_type="item_error",
            item_id=item_id,
            error=error,
        )

    @classmethod
    def progress(cls, message: str, current: int = None, total: int = None) -> "ProgressEvent":
        """Event: progress - frontend compatible"""
        return cls(
            event_type="progress",
            current=current,
            total=total,
            message=message,
        )

    @classmethod
    def complete(cls, message: str = "生成完成") -> "ProgressEvent":
        """Event: complete - frontend compatible"""
        return cls(
            event_type="complete",
            message=message,
        )

    @classmethod
    def token_stream(cls, item_id: str, token: str, done: bool = False) -> "ProgressEvent":
        """Event: token_stream - for streaming LLM token output"""
        return cls(
            event_type="token_stream",
            item_id=item_id,
            content=token,
            message="done" if done else None,
        )

    # Chat event types
    @classmethod
    def chat_message(cls, message) -> "ProgressEvent":
        """Event: chat_message - new chat message from AI"""
        return cls(
            event_type="chat_message",
            content=message.content,
            message=message.role,
            metadata=message.metadata if hasattr(message, 'metadata') else None,
        )

    @classmethod
    def typing_start(cls) -> "ProgressEvent":
        """Event: typing_start - AI started typing"""
        return cls(
            event_type="typing_start",
            message="AI is typing...",
        )

    @classmethod
    def typing_end(cls) -> "ProgressEvent":
        """Event: typing_end - AI stopped typing"""
        return cls(
            event_type="typing_end",
            message="AI finished typing",
        )

    # Draw event types
    @classmethod
    def draw_start(cls, item_id: str, item_name: str = None, message: str = None) -> "ProgressEvent":
        """Event: draw_start - 开始绘制"""
        return cls(
            event_type="draw_start",
            item_id=item_id,
            item_type=item_name,
            message=message or f"开始绘制 {item_name}" if item_name else "开始绘制",
        )

    @classmethod
    def draw_progress(cls, item_id: str, content: str, done: bool = False) -> "ProgressEvent":
        """Event: draw_progress - 绘制进度"""
        return cls(
            event_type="draw_progress",
            item_id=item_id,
            content=content,
            message="done" if done else None,
        )

    @classmethod
    def draw_complete(cls, item_id: str, content: str = None) -> "ProgressEvent":
        """Event: draw_complete - 绘制完成"""
        return cls(
            event_type="draw_complete",
            item_id=item_id,
            content=content,
        )

    @classmethod
    def draw_error(cls, item_id: str, error: str) -> "ProgressEvent":
        """Event: draw_error - 绘制错误"""
        return cls(
            event_type="draw_error",
            item_id=item_id,
            error=error,
        )


class WebSocketManager:
    """
    Thread-safe WebSocket connection manager per session.

    Manages WebSocket connections and broadcasts progress events to all clients
    connected to a specific session.
    """

    def __init__(self):
        """Initialize the WebSocket manager"""
        # Dict of session_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        logger.debug("WebSocketManager initialized")

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accept a WebSocket connection and register it for a session.

        Args:
            websocket: The WebSocket connection
            session_id: The session ID to associate with this connection
        """
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(websocket)
        logger.info(f"WebSocket connected: session_id={session_id}, total_connections={len(self._connections.get(session_id, []))}")

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Remove a WebSocket connection from a session.

        Args:
            websocket: The WebSocket connection to remove
            session_id: The session ID to disassociate from
        """
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]
        logger.info(f"WebSocket disconnected: session_id={session_id}")

    async def send_progress(
        self,
        session_id: str,
        event: ProgressEvent,
    ) -> None:
        """
        Send a progress event to all clients connected to a session.

        Args:
            session_id: The session ID to send the event to
            event: The progress event to send
        """
        event_data = json.dumps(event.to_dict())
        dead_connections = []

        async with self._lock:
            connections = self._connections.get(session_id, set()).copy()

        for websocket in connections:
            try:
                await websocket.send_text(event_data)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if session_id in self._connections:
                        self._connections[session_id].discard(ws)

    async def broadcast(
        self,
        session_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """
        Broadcast a custom event to all clients connected to a session.

        Args:
            session_id: The session ID to broadcast to
            event_type: The type of the event
            data: Additional event data
        """
        event_data = json.dumps({"type": event_type, **data})
        dead_connections = []

        async with self._lock:
            connections = self._connections.get(session_id, set()).copy()

        for websocket in connections:
            try:
                await websocket.send_text(event_data)
            except Exception as e:
                logger.warning(f"Failed to broadcast to WebSocket: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if session_id in self._connections:
                        self._connections[session_id].discard(ws)

    def get_connection_count(self, session_id: str) -> int:
        """
        Get the number of active connections for a session.

        Args:
            session_id: The session ID

        Returns:
            Number of active connections
        """
        return len(self._connections.get(session_id, set()))


# Global WebSocket manager instance
_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


def set_websocket_manager(manager: WebSocketManager) -> None:
    """Set the global WebSocket manager instance"""
    global _ws_manager
    _ws_manager = manager
