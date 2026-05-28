"""
ContentStore - 内容文件存储

管理生成的媒体文件（图片、视频、音频）的本地存储
"""

import asyncio
import base64
import httpx
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse


class ContentStore:
    """内容文件存储管理器"""

    def __init__(self, base_dir: str = "data/studio/sessions"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_session_dir(self, session_id: str, version: int = None) -> Path:
        """获取会话目录

        Args:
            session_id: 会话 ID
            version: 版本号（可选），为 None 时返回 current 目录

        Returns:
            Path 对象
        """
        if version:
            return self.base_dir / session_id / "versions" / f"v{version}"
        return self.base_dir / session_id / "current"

    def get_content_type_subdir(self, content_type: str) -> str:
        """获取内容类型对应的子目录名"""
        type_map = {
            "image": "images",
            "video": "videos",
            "audio": "audio",
        }
        return type_map.get(content_type, "others")

    async def save_content(
        self,
        session_id: str,
        item_id: str,
        content: str,
        content_type: str,
        version: int = None,
    ) -> Optional[str]:
        """
        保存内容到本地文件

        Args:
            session_id: 会话 ID
            item_id: 内容项 ID
            content: 内容（URL 或 base64）
            content_type: image/video/audio
            version: 版本号（可选）

        Returns:
            本地文件路径，失败返回 None
        """
        if not content:
            return None

        subdir = self.get_content_type_subdir(content_type)
        session_dir = self.get_session_dir(session_id, version)
        content_dir = session_dir / subdir
        content_dir.mkdir(parents=True, exist_ok=True)

        try:
            if content.startswith("data:"):
                # base64 格式
                ext = self._get_ext_from_mime(content)
                file_path = content_dir / f"{item_id}.{ext}"
                data = base64.b64decode(content.split(",")[1])
                with open(file_path, "wb") as f:
                    f.write(data)
                return str(file_path)

            elif content.startswith("http"):
                # URL 格式，需要下载
                ext = self._get_ext_from_url(content)
                file_path = content_dir / f"{item_id}.{ext}"
                async with httpx.AsyncClient() as client:
                    response = await client.get(content, timeout=30.0)
                    response.raise_for_status()
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                return str(file_path)

        except Exception as e:
            print(f"保存内容失败: {e}")
            return None

        return None

    def _get_ext_from_mime(self, base64_content: str) -> str:
        """从 MIME 类型获取扩展名"""
        try:
            mime = base64_content.split(";")[0].split("/")[1]
            return {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}.get(mime, "jpg")
        except Exception:
            return "jpg"

    def _get_ext_from_url(self, url: str) -> str:
        """从 URL 获取扩展名"""
        try:
            parsed = urlparse(url)
            path = parsed.path
            ext = Path(path).suffix.lstrip(".") or "jpg"
            return ext
        except Exception:
            return "jpg"

    def load_content(self, file_path: str) -> Optional[bytes]:
        """加载本地文件"""
        try:
            with open(file_path, "rb") as f:
                return f.read()
        except Exception:
            return None

    def delete_session_content(self, session_id: str):
        """删除会话的所有内容文件"""
        import shutil

        session_dir = self.base_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def get_version_dirs(self, session_id: str) -> List[int]:
        """获取所有版本号"""
        versions_dir = self.base_dir / session_id / "versions"
        if not versions_dir.exists():
            return []
        return sorted(
            [
                int(d.name[1:])  # "v1" -> 1
                for d in versions_dir.iterdir()
                if d.is_dir() and d.name.startswith("v")
            ]
        )

    def save_items_snapshot(
        self, session_id: str, items_data: List[dict], version: int
    ) -> bool:
        """保存版本快照的 items 数据到文件"""
        try:
            version_dir = self.get_session_dir(session_id, version)
            version_dir.mkdir(parents=True, exist_ok=True)

            snapshot_path = version_dir / "items.json"
            with open(snapshot_path, "w", encoding="utf-8") as f:
                import json

                json.dump(items_data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            print(f"保存 items 快照失败: {e}")
            return False

    def load_items_snapshot(self, session_id: str, version: int) -> Optional[List[dict]]:
        """加载版本快照的 items 数据"""
        try:
            version_dir = self.get_session_dir(session_id, version)
            snapshot_path = version_dir / "items.json"

            if not snapshot_path.exists():
                return None

            with open(snapshot_path, "r", encoding="utf-8") as f:
                import json

                return json.load(f)
        except Exception:
            return None

    def save_plan_snapshot(
        self, session_id: str, plan_data: dict, version: int
    ) -> bool:
        """保存版本快照的 plan 数据到文件"""
        try:
            version_dir = self.get_session_dir(session_id, version)
            version_dir.mkdir(parents=True, exist_ok=True)

            plan_path = version_dir / "plan.json"
            with open(plan_path, "w", encoding="utf-8") as f:
                import json

                json.dump(plan_data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            print(f"保存 plan 快照失败: {e}")
            return False

    def load_plan_snapshot(self, session_id: str, version: int) -> Optional[dict]:
        """加载版本快照的 plan 数据"""
        try:
            version_dir = self.get_session_dir(session_id, version)
            plan_path = version_dir / "plan.json"

            if not plan_path.exists():
                return None

            with open(plan_path, "r", encoding="utf-8") as f:
                import json

                return json.load(f)
        except Exception:
            return None
