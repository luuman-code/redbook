"""
VersionStore - 版本存储

存储版本快照
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from ..models.version import Version


class VersionStore:
    """
    版本存储

    管理版本快照的持久化
    """

    def __init__(self, storage_dir: str = None):
        """
        初始化存储

        Args:
            storage_dir: 存储目录
        """
        self._versions: Dict[str, List[Version]] = {}  # session_id -> versions
        self._storage_dir = storage_dir

        if self._storage_dir:
            Path(self._storage_dir).mkdir(parents=True, exist_ok=True)

    async def save_version(self, version: Version) -> bool:
        """
        保存版本

        Args:
            version: Version 对象

        Returns:
            是否成功
        """
        try:
            session_id = version.session_id

            if session_id not in self._versions:
                self._versions[session_id] = []

            self._versions[session_id].append(version)

            # 持久化
            if self._storage_dir:
                await self._persist_session_versions(session_id)

            return True

        except Exception:
            return False

    async def get_versions(self, session_id: str) -> List[Version]:
        """
        获取会话的所有版本

        Args:
            session_id: 会话 ID

        Returns:
            Version 列表
        """
        if session_id in self._versions:
            return self._versions[session_id]

        # 尝试从文件加载
        if self._storage_dir:
            path = Path(self._storage_dir) / f"{session_id}_versions.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    versions = [Version.from_dict(v) for v in data]
                    self._versions[session_id] = versions
                    return versions
                except Exception:
                    return []

        return []

    async def get_version(self, session_id: str, version_number: int) -> Optional[Version]:
        """
        获取指定版本

        Args:
            session_id: 会话 ID
            version_number: 版本号

        Returns:
            Version 或 None
        """
        versions = await self.get_versions(session_id)
        for v in versions:
            if v.version_number == version_number:
                return v
        return None

    async def _persist_session_versions(self, session_id: str) -> None:
        """持久化会话版本"""
        if not self._storage_dir or session_id not in self._versions:
            return

        path = Path(self._storage_dir) / f"{session_id}_versions.json"
        versions = [v.to_dict() for v in self._versions[session_id]]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(versions, f, ensure_ascii=False, indent=2, default=str)

    async def delete_session_versions(self, session_id: str) -> bool:
        """
        删除会话的所有版本

        Args:
            session_id: 会话 ID

        Returns:
            是否成功
        """
        if session_id in self._versions:
            del self._versions[session_id]

        if self._storage_dir:
            path = Path(self._storage_dir) / f"{session_id}_versions.json"
            if path.exists():
                path.unlink()

        return True
