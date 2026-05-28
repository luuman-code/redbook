"""
SessionStore - 会话存储

内存存储，支持后续扩展为持久化存储
"""

import json
from pathlib import Path
from typing import Dict, Optional

from ..models.session import Session
from ..debug_logger import get_logger

# 获取日志记录器
logger = get_logger("session_store")


# 单例实例
_session_store_instance: Optional["SessionStore"] = None


def get_session_store() -> "SessionStore":
    """获取 SessionStore 单例实例"""
    global _session_store_instance
    if _session_store_instance is None:
        _session_store_instance = SessionStore()
    return _session_store_instance


class SessionStore:
    """
    会话存储

    当前为内存存储，可扩展为文件存储或数据库存储

    注意：应使用 get_session_store() 获取实例以确保单例模式
    """

    def __init__(self, storage_dir: str = "data/studio/sessions"):
        """
        初始化存储

        Args:
            storage_dir: 存储目录（用于持久化），默认为 data/studio/sessions
        """
        self._sessions: Dict[str, Session] = {}
        self._storage_dir = storage_dir

        if self._storage_dir:
            Path(self._storage_dir).mkdir(parents=True, exist_ok=True)
            logger.debug(f"SessionStore initialized with storage_dir: {storage_dir}")

    async def save(self, session: Session) -> bool:
        """
        保存会话

        Args:
            session: Session 对象

        Returns:
            是否成功
        """
        try:
            self._sessions[session.session_id] = session
            logger.debug(f"Session saved to memory: {session.session_id}")

            # 持久化到文件（如果配置了存储目录）
            if self._storage_dir:
                path = Path(self._storage_dir) / f"{session.session_id}.json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(session.to_dict(), f, ensure_ascii=False, indent=2, default=str)
                logger.debug(f"Session persisted to file: {path}")

            return True

        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            return False

    async def get(self, session_id: str) -> Optional[Session]:
        """
        获取会话

        Args:
            session_id: 会话 ID

        Returns:
            Session 对象或 None
        """
        # 先从内存获取
        if session_id in self._sessions:
            logger.debug(f"Session found in memory: {session_id}")
            return self._sessions[session_id]

        # 如果配置了存储目录，尝试从文件加载
        if self._storage_dir:
            path = Path(self._storage_dir) / f"{session_id}.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session = Session.from_dict(data)
                    self._sessions[session_id] = session
                    logger.debug(f"Session loaded from file: {session_id}")
                    return session
                except Exception as e:
                    logger.error(f"Failed to load session {session_id} from file: {e}")
                    return None

        logger.debug(f"Session not found: {session_id}")
        return None

    async def delete(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Session deleted from memory: {session_id}")

        # 删除文件（如果存在）
        if self._storage_dir:
            path = Path(self._storage_dir) / f"{session_id}.json"
            if path.exists():
                path.unlink()
                logger.debug(f"Session file deleted: {path}")

        return True

    async def list(self) -> list:
        """
        列出所有会话

        Returns:
            会话 ID 列表
        """
        session_ids = list(self._sessions.keys())
        logger.debug(f"Listing sessions: {len(session_ids)} found")
        return session_ids

    async def exists(self, session_id: str) -> bool:
        """
        检查会话是否存在

        Args:
            session_id: 会话 ID

        Returns:
            是否存在
        """
        return session_id in self._sessions

    async def clear(self) -> bool:
        """
        清空所有会话

        Returns:
            是否成功
        """
        self._sessions.clear()

        # 删除所有会话文件
        if self._storage_dir:
            for path in Path(self._storage_dir).glob("*.json"):
                path.unlink()

        logger.info("All sessions cleared")
        return True
