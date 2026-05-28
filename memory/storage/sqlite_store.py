"""
SQLiteStore - 结构化数据存储

使用 SQLite 存储记忆的结构化数据（如元数据、访问统计等）
向量数据仍使用 Chroma 存储
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


class SQLiteStore:
    """SQLite 结构化存储

    用于存储：
    - 记忆条目的元数据
    - 访问统计
    - 用户偏好
    - 会话信息
    """

    def __init__(self, db_path: str = "data/memory/memory.db"):
        """
        初始化 SQLite 存储

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path

        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 记忆条目表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,  -- JSON 字符串
                    importance REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT,
                    session_id TEXT,
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # 访问历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_item_id TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_type TEXT,  -- read, update, search
                    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id)
                )
            """)

            # 用户偏好表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    preference TEXT NOT NULL,
                    value TEXT,
                    importance REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_type
                ON memory_items(memory_type)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_session
                ON memory_items(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_user
                ON memory_items(user_id)
            """)

    def insert_memory_item(
        self,
        item_id: str,
        memory_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 1.0,
        session_id: Optional[str] = None,
        user_id: str = "default"
    ) -> bool:
        """插入记忆条目"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                cursor.execute("""
                    INSERT INTO memory_items
                    (id, memory_type, content, metadata, importance, session_id, user_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item_id,
                    memory_type,
                    content,
                    json.dumps(metadata) if metadata else None,
                    importance,
                    session_id,
                    user_id,
                    now,
                    now
                ))

                return True
        except Exception as e:
            print(f"Failed to insert memory item: {e}")
            return False

    def update_memory_item(
        self,
        item_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None
    ) -> bool:
        """更新记忆条目"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                updates = []
                values = []

                if content is not None:
                    updates.append("content = ?")
                    values.append(content)

                if metadata is not None:
                    updates.append("metadata = ?")
                    values.append(json.dumps(metadata))

                if importance is not None:
                    updates.append("importance = ?")
                    values.append(importance)

                updates.append("updated_at = ?")
                values.append(now)

                values.append(item_id)

                cursor.execute(f"""
                    UPDATE memory_items
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, values)

                return cursor.rowcount > 0
        except Exception as e:
            print(f"Failed to update memory item: {e}")
            return False

    def record_access(self, memory_item_id: str, access_type: str = "read") -> bool:
        """记录一次访问"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                # 更新访问统计
                cursor.execute("""
                    UPDATE memory_items
                    SET access_count = access_count + 1, last_accessed = ?
                    WHERE id = ?
                """, (now, memory_item_id))

                # 记录访问历史
                cursor.execute("""
                    INSERT INTO access_history (memory_item_id, accessed_at, access_type)
                    VALUES (?, ?, ?)
                """, (memory_item_id, now, access_type))

                return True
        except Exception as e:
            print(f"Failed to record access: {e}")
            return False

    def get_memory_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """获取记忆条目"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM memory_items WHERE id = ?", (item_id,))
                row = cursor.fetchone()

                if row:
                    return dict(row)
                return None
        except Exception as e:
            print(f"Failed to get memory item: {e}")
            return None

    def get_memory_items(
        self,
        memory_type: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取记忆条目列表"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM memory_items WHERE 1=1"
                params = []

                if memory_type:
                    query += " AND memory_type = ?"
                    params.append(memory_type)

                if session_id:
                    query += " AND session_id = ?"
                    params.append(session_id)

                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [dict(row) for row in rows]
        except Exception as e:
            print(f"Failed to get memory items: {e}")
            return []

    def delete_memory_item(self, item_id: str) -> bool:
        """删除记忆条目"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM memory_items WHERE id = ?", (item_id,))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Failed to delete memory item: {e}")
            return False

    def save_user_preference(
        self,
        user_id: str,
        category: str,
        preference: str,
        value: Optional[str] = None,
        importance: float = 0.5
    ) -> bool:
        """保存用户偏好"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                # 检查是否已存在
                cursor.execute("""
                    SELECT id FROM user_preferences
                    WHERE user_id = ? AND category = ? AND preference = ?
                """, (user_id, category, preference))

                existing = cursor.fetchone()

                if existing:
                    # 更新
                    cursor.execute("""
                        UPDATE user_preferences
                        SET value = ?, importance = ?, updated_at = ?
                        WHERE id = ?
                    """, (value, importance, now, existing["id"]))
                else:
                    # 插入
                    cursor.execute("""
                        INSERT INTO user_preferences
                        (user_id, category, preference, value, importance, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, category, preference, value, importance, now, now))

                return True
        except Exception as e:
            print(f"Failed to save user preference: {e}")
            return False

    def get_user_preferences(
        self,
        user_id: str,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取用户偏好列表"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM user_preferences WHERE user_id = ?"
                params = [user_id]

                if category:
                    query += " AND category = ?"
                    params.append(category)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [dict(row) for row in rows]
        except Exception as e:
            print(f"Failed to get user preferences: {e}")
            return []

    def get_access_stats(self, item_id: str) -> Dict[str, Any]:
        """获取记忆条目的访问统计"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 获取基本统计
                cursor.execute("""
                    SELECT access_count, last_accessed, created_at
                    FROM memory_items WHERE id = ?
                """, (item_id,))
                row = cursor.fetchone()

                if not row:
                    return {}

                # 获取最近访问历史
                cursor.execute("""
                    SELECT accessed_at, access_type
                    FROM access_history
                    WHERE memory_item_id = ?
                    ORDER BY accessed_at DESC
                    LIMIT 10
                """, (item_id,))
                history = [dict(r) for r in cursor.fetchall()]

                return {
                    "access_count": row["access_count"],
                    "last_accessed": row["last_accessed"],
                    "created_at": row["created_at"],
                    "recent_history": history
                }
        except Exception as e:
            print(f"Failed to get access stats: {e}")
            return {}

    def cleanup_old_data(self, days: int = 30) -> int:
        """清理旧数据（保留指定天数）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cutoff = datetime.now().isoformat()

                # 使用日期计算
                cursor.execute("""
                    DELETE FROM memory_items
                    WHERE created_at < datetime(?, '-' || ? || ' days')
                """, (cutoff, days))

                deleted = cursor.rowcount

                # 清理孤立访问历史
                cursor.execute("""
                    DELETE FROM access_history
                    WHERE memory_item_id NOT IN (SELECT id FROM memory_items)
                """)

                return deleted
        except Exception as e:
            print(f"Failed to cleanup old data: {e}")
            return 0
