"""
CanvasStorage - 画板持久化存储

提供画板数据的持久化存储和加载功能
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .canvas_core import CanvasCore, CanvasElement, CanvasSnapshot, SelectionRegion


@dataclass
class CanvasSummary:
    """
    画板摘要信息

    属性说明：
    - canvas_id: 画板ID
    - name: 画板名称
    - element_count: 元素数量
    - thumbnail: 缩略图路径
    - created_at: 创建时间
    - updated_at: 更新时间
    - created_by: 创建者
    """
    canvas_id: str
    name: str = ""
    element_count: int = 0
    thumbnail: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str = "user"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "canvas_id": self.canvas_id,
            "name": self.name,
            "element_count": self.element_count,
            "thumbnail": self.thumbnail,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, 'isoformat') else self.created_at,
            "updated_at": self.updated_at.isoformat() if hasattr(self.updated_at, 'isoformat') else self.updated_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanvasSummary":
        """从字典创建"""
        if data is None:
            return None

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()

        return cls(
            canvas_id=data["canvas_id"],
            name=data.get("name", ""),
            element_count=data.get("element_count", 0),
            thumbnail=data.get("thumbnail"),
            created_at=created_at,
            updated_at=updated_at,
            created_by=data.get("created_by", "user"),
        )


class CanvasStorage:
    """
    画板持久化存储

    职责：
    1. 保存画板数据到文件系统或数据库
    2. 加载画板数据
    3. 列表查询画板
    4. 删除画板
    """

    def __init__(self, storage_dir: str = "data/studio/canvases"):
        """
        初始化存储

        Args:
            storage_dir: 存储目录
        """
        self._storage_dir = Path(storage_dir)
        self._canvas_dir = self._storage_dir / "canvases"
        self._meta_dir = self._storage_dir / "metadata"
        self._canvases: Dict[str, Dict[str, Any]] = {}  # canvas_id -> canvas_data
        self._index: List[str] = []  # canvas_id list for ordering
        self._lock = asyncio.Lock()
        # 【新增】CanvasCore 实例缓存，确保同一 canvas_id 返回相同实例
        self._canvas_instances: Dict[str, CanvasCore] = {}

        # 创建目录
        self._canvas_dir.mkdir(parents=True, exist_ok=True)
        self._meta_dir.mkdir(parents=True, exist_ok=True)

        # 加载已有数据
        asyncio.create_task(self._load_index())

    async def _load_index(self) -> None:
        """加载索引"""
        index_path = self._meta_dir / "index.json"
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._canvases = data.get("canvases", {})
                    self._index = data.get("index", [])
            except Exception:
                pass

    async def _save_index(self) -> None:
        """保存索引"""
        index_path = self._meta_dir / "index.json"
        try:
            data = {
                "canvases": self._canvases,
                "index": self._index,
            }
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    async def save_canvas(self, canvas: CanvasCore) -> bool:
        """
        保存画板

        Args:
            canvas: CanvasCore 对象

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            try:
                canvas_id = canvas.canvas_id

                # 获取快照
                snapshot = canvas.get_snapshot()

                # 保存画板数据
                canvas_path = self._canvas_dir / f"{canvas_id}.json"
                with open(canvas_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2, default=str)

                # 更新索引
                self._canvases[canvas_id] = {
                    "canvas_id": canvas_id,
                    "name": snapshot.name,
                    "element_count": len(snapshot.elements),
                    "updated_at": datetime.now().isoformat(),
                    "created_by": "user",
                }

                if canvas_id not in self._index:
                    self._index.append(canvas_id)

                await self._save_index()
                return True

            except Exception as e:
                print(f"保存画板失败: {e}")
                return False

    async def load_canvas(self, canvas_id: str) -> Optional[CanvasCore]:
        """
        加载画板

        Args:
            canvas_id: 画板ID

        Returns:
            CanvasCore 或 None
        """
        async with self._lock:
            # 【修改】检查缓存，如果有缓存实例直接返回（共享内存）
            if canvas_id in self._canvas_instances:
                return self._canvas_instances[canvas_id]

            try:
                canvas_path = self._canvas_dir / f"{canvas_id}.json"
                if not canvas_path.exists():
                    return None

                with open(canvas_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 使用 from_dict 直接创建 CanvasCore
                canvas = CanvasCore.from_dict(data, canvas_id=canvas_id)

                # 【新增】缓存实例，确保同一 canvas_id 返回相同实例
                self._canvas_instances[canvas_id] = canvas

                return canvas

            except Exception as e:
                print(f"加载画板失败: {e}")
                return None

    async def list_canvases(
        self,
        user_id: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanvasSummary]:
        """
        列出画板

        Args:
            user_id: 用户ID（预留，用于多用户场景）
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            CanvasSummary 列表
        """
        async with self._lock:
            # 按更新时间倒序
            summaries = []
            for canvas_id in reversed(self._index):
                if canvas_id in self._canvases:
                    data = self._canvases[canvas_id]
                    summary = CanvasSummary.from_dict(data)
                    if summary:
                        summaries.append(summary)

            # 应用分页
            return summaries[offset:offset + limit]

    async def get_canvas_summary(self, canvas_id: str) -> Optional[CanvasSummary]:
        """
        获取画板摘要

        Args:
            canvas_id: 画板ID

        Returns:
            CanvasSummary 或 None
        """
        async with self._lock:
            if canvas_id in self._canvases:
                return CanvasSummary.from_dict(self._canvases[canvas_id])
            return None

    async def delete_canvas(self, canvas_id: str) -> bool:
        """
        删除画板

        Args:
            canvas_id: 画板ID

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            try:
                # 删除画板文件
                canvas_path = self._canvas_dir / f"{canvas_id}.json"
                if canvas_path.exists():
                    canvas_path.unlink()

                # 从索引中移除
                if canvas_id in self._canvases:
                    del self._canvases[canvas_id]
                if canvas_id in self._index:
                    self._index.remove(canvas_id)

                await self._save_index()
                return True

            except Exception as e:
                print(f"删除画板失败: {e}")
                return False

    async def rename_canvas(self, canvas_id: str, new_name: str) -> bool:
        """
        重命名画板

        Args:
            canvas_id: 画板ID
            new_name: 新名称

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            try:
                if canvas_id in self._canvases:
                    self._canvases[canvas_id]["name"] = new_name
                    self._canvases[canvas_id]["updated_at"] = datetime.now().isoformat()
                    await self._save_index()
                    return True
                return False

            except Exception as e:
                print(f"重命名画板失败: {e}")
                return False

    async def duplicate_canvas(self, canvas_id: str, new_canvas_id: str = None) -> Optional[CanvasCore]:
        """
        复制画板

        Args:
            canvas_id: 原画板ID
            new_canvas_id: 新画板ID（可选）

        Returns:
            CanvasCore 或 None
        """
        async with self._lock:
            try:
                # 加载原画板
                original = await self.load_canvas(canvas_id)
                if not original:
                    return None

                # 创建新画板
                new_id = new_canvas_id or f"canvas_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                new_canvas = CanvasCore(canvas_id=new_id)

                # 复制元素
                for element in original.elements:
                    element_copy = CanvasElement.from_dict(element.to_dict())
                    element_copy.id = f"{element.id}_copy"
                    new_canvas._elements[element_copy.id] = element_copy

                new_canvas._rebuild_z_index_map()

                # 保存新画板
                await self.save_canvas(new_canvas)

                return new_canvas

            except Exception as e:
                print(f"复制画板失败: {e}")
                return None

    async def export_canvas(self, canvas_id: str, export_path: str) -> bool:
        """
        导出画板到指定路径

        Args:
            canvas_id: 画板ID
            export_path: 导出路径

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            try:
                canvas = await self.load_canvas(canvas_id)
                if not canvas:
                    return False

                snapshot = canvas.get_snapshot()
                export_file = Path(export_path)

                with open(export_file, "w", encoding="utf-8") as f:
                    json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2, default=str)

                return True

            except Exception as e:
                print(f"导出画板失败: {e}")
                return False

    async def import_canvas(self, import_path: str, canvas_id: str = None) -> Optional[CanvasCore]:
        """
        从指定路径导入画板

        Args:
            import_path: 导入路径
            canvas_id: 画板ID（可选）

        Returns:
            CanvasCore 或 None
        """
        async with self._lock:
            try:
                import_file = Path(import_path)
                if not import_file.exists():
                    return None

                with open(import_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                snapshot = CanvasSnapshot.from_dict(data)
                if not snapshot:
                    return None

                # 使用指定的canvas_id或原canvas_id
                new_id = canvas_id or snapshot.canvas_id
                snapshot.canvas_id = new_id

                # 创建 CanvasCore 并加载数据
                canvas = CanvasCore(canvas_id=new_id)
                await canvas.load_from_snapshot(snapshot)

                # 保存
                await self.save_canvas(canvas)

                return canvas

            except Exception as e:
                print(f"导入画板失败: {e}")
                return None

    async def save_canvas_elements(
        self,
        canvas_id: str,
        elements: List[CanvasElement],
    ) -> bool:
        """
        仅保存画板元素（轻量级保存）

        Args:
            canvas_id: 画板ID
            elements: 元素列表

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            try:
                # 加载现有画板数据
                canvas_path = self._canvas_dir / f"{canvas_id}.json"
                if canvas_path.exists():
                    with open(canvas_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {"canvas_id": canvas_id, "elements": [], "operation_history": []}

                # 更新元素
                data["elements"] = [e.to_dict() for e in elements]
                data["timestamp"] = datetime.now().isoformat()

                # 保存
                with open(canvas_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)

                # 更新索引
                if canvas_id in self._canvases:
                    self._canvases[canvas_id]["element_count"] = len(elements)
                    self._canvases[canvas_id]["updated_at"] = datetime.now().isoformat()
                    await self._save_index()

                return True

            except Exception as e:
                print(f"保存画板元素失败: {e}")
                return False

    def get_storage_dir(self) -> str:
        """获取存储目录"""
        return str(self._storage_dir)

    def get_canvas_count(self) -> int:
        """获取画板数量"""
        return len(self._canvases)
