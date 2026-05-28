"""
CanvasToolResultStore - 画板工具结果存储

用于持久化存储画板Agent的工具调用结果，支持版本管理、历史查询和字段获取。
"""

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CanvasToolResultRecord:
    """画板工具结果记录"""
    tool_call_id: str
    tool_name: str  # draw, generate, edit, understand, suggest
    arguments: dict
    result_content: str  # 结果内容（JSON字符串）
    result_data: Optional[dict] = None  # 解析后的数据
    element_id: Optional[str] = None  # 画板元素ID（如果有）
    element_type: Optional[str] = None  # 元素类型（TEXT/IMAGE/SHAPE等）
    # 【新增】关联的图案会话ID
    drawing_session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        d = {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result_content": self.result_content,
            "result_data": self.result_data,
            "element_id": self.element_id,
            "element_type": self.element_type,
            "drawing_session_id": self.drawing_session_id,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
        }
        return d

    @staticmethod
    def from_dict(data: dict) -> "CanvasToolResultRecord":
        data = data.copy()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return CanvasToolResultRecord(**data)


class CanvasToolResultStore:
    """画板工具结果存储器"""

    # 类常量
    ARCHIVE_STORAGE_DIR = "data/canvas_tool_results_archive"

    def __init__(self, canvas_id: str, storage_dir: str = "data/canvas_tool_results"):
        self.canvas_id = canvas_id
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.storage_dir / f"{canvas_id}_tool_results.json"
        self._lock = threading.Lock()
        self._records: List[CanvasToolResultRecord] = []
        self._load()

    def _load(self):
        """从文件加载记录"""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._records = [CanvasToolResultRecord.from_dict(r) for r in data]
            except Exception as e:
                logger.warning(f"Failed to load canvas tool results: {e}")
                self._records = []

    def _save(self):
        """保存记录到文件"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._records], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save canvas tool results: {e}")

    def add(self, record: CanvasToolResultRecord):
        """添加记录"""
        with self._lock:
            self._records.append(record)
            self._save()

    def get_latest(self, tool_name: Optional[str] = None, index: int = 0) -> Optional[CanvasToolResultRecord]:
        """按添加顺序获取工具结果

        index=0 返回最老的记录（V1）
        index=1 返回第二个记录（V2）
        index=2 返回第三个记录（V3）
        以此类推...

        负索引：index=-1 返回最新的记录，index=-2 返回倒数第二个，以此类推
        """
        with self._lock:
            records = [r for r in self._records if r.tool_name == tool_name] if tool_name else self._records
            if not records:
                return None
            # 按 timestamp 升序排序（最老在前）
            sorted_records = sorted(records, key=lambda r: r.timestamp, reverse=False)

            # 处理负索引
            if index < 0:
                # 负索引从最后开始计算
                actual_index = len(sorted_records) + index
                if actual_index < 0:
                    return None
                return sorted_records[actual_index]

            # 安全检查
            if index < 0 or index >= len(sorted_records):
                return None
            return sorted_records[index]

    def get_field(self, tool_name: str, field_name: str, index: int = 0) -> Any:
        """从工具结果中获取特定字段

        index=0 获取最老版本，index=1 获取第二个版本，以此类推"""
        record = self.get_latest(tool_name, index)
        if not record or not record.result_data:
            return None
        return record.result_data.get(field_name)

    def get_all_records(self) -> List[CanvasToolResultRecord]:
        """获取所有记录"""
        with self._lock:
            return self._records.copy()

    def get_history(self, tool_name: Optional[str] = None, limit: int = 10) -> List[dict]:
        """获取历史记录（按添加顺序，最老在前）

        返回格式：[V1, V2, V3, ...]"""
        with self._lock:
            records = [r for r in self._records if r.tool_name == tool_name] if tool_name else self._records
            # 按 timestamp 升序排序（最老在前）
            sorted_records = sorted(records, key=lambda r: r.timestamp, reverse=False)
            return [r.to_dict() for r in sorted_records[:limit]]

    def get_by_element_id(self, element_id: str) -> List[CanvasToolResultRecord]:
        """根据元素ID查询相关记录"""
        with self._lock:
            return [r for r in self._records if r.element_id == element_id]

    def search(self, query: str) -> List[CanvasToolResultRecord]:
        """搜索包含查询字符串的记录"""
        with self._lock:
            query_lower = query.lower()
            return [
                r for r in self._records
                if query_lower in r.result_content.lower()
                or (r.result_data and query_lower in str(r.result_data).lower())
            ]

    def rollback(self, index: int = 1) -> Optional[CanvasToolResultRecord]:
        """回滚到第 N 个最新记录（默认回滚到上一个）"""
        with self._lock:
            if len(self._records) < index + 1:
                return None
            removed = self._records[-index:]
            self._records = self._records[:-index]
            self._save()
            return removed[0] if removed else None

    def pop_by_tool_name(self, tool_name: str) -> Optional[CanvasToolResultRecord]:
        """移除最新的指定工具类型记录并返回

        遍历 _records（按添加顺序，最老的在前），找到最后一个匹配的记录并移除。
        返回被移除的记录，如果不存在则返回 None

        注意：这里移除的是"最新添加"的记录（_records 中最后一个匹配的），
        与 _records 的添加顺序一致。
        """
        with self._lock:
            # 倒序遍历 _records，找到最后一个匹配的记录
            for i in range(len(self._records) - 1, -1, -1):
                if self._records[i].tool_name == tool_name:
                    removed = self._records.pop(i)
                    self._save()
                    return removed
            return None

    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._records.clear()
            self._save()

    def _generate_archive_filename(self, drawing_session_id: str) -> str:
        """
        生成归档文件名

        格式: canvas-{canvas_id}-{drawing_session_id}-{timestamp}.json
        使用 - 作为分隔符，避免与 UUID 中的 _ 混淆
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        return f"canvas-{self.canvas_id}-{drawing_session_id}-{timestamp}.json"

    def archive_by_drawing_session(self, drawing_session_id: str) -> str:
        """按 drawing_session_id 归档指定图案的所有记录"""
        with self._lock:
            pattern_records = [r for r in self._records if r.drawing_session_id == drawing_session_id]
            if not pattern_records:
                return ""

            archive_filename = self._generate_archive_filename(drawing_session_id)
            archive_dir = Path(self.ARCHIVE_STORAGE_DIR)
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / archive_filename

            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in pattern_records], f, ensure_ascii=False, indent=2)

            self._records = [r for r in self._records if r.drawing_session_id != drawing_session_id]
            self._save()

            logger.info(f"Archived {len(pattern_records)} records for drawing_session_id={drawing_session_id}")
            return str(archive_path)

    def archive_all_and_clear(self) -> List[str]:
        """归档所有记录并清空（退出画板时调用）"""
        with self._lock:
            if not self._records:
                return []

            from collections import defaultdict
            grouped = defaultdict(list)
            for r in self._records:
                session_id = r.drawing_session_id or "unsessionized"
                grouped[session_id].append(r)

            archive_paths = []
            archive_dir = Path(self.ARCHIVE_STORAGE_DIR)
            archive_dir.mkdir(parents=True, exist_ok=True)

            for session_id, records in grouped.items():
                archive_filename = self._generate_archive_filename(session_id)
                archive_path = archive_dir / archive_filename
                with open(archive_path, "w", encoding="utf-8") as f:
                    json.dump([r.to_dict() for r in records], f, ensure_ascii=False, indent=2)
                archive_paths.append(str(archive_path))

            self._records.clear()
            if self.file_path.exists():
                self.file_path.unlink()

            return archive_paths

    @staticmethod
    def list_archives(canvas_id: str) -> List[dict]:
        """
        列出某 canvas 的所有归档

        文件名格式: canvas-{canvas_id}-{drawing_session_id}-{timestamp}.json
        解析方式: 按 - 分割，canvas_id 长度为 36（UUID格式），drawing_session_id 在其后
        """
        archive_dir = Path(CanvasToolResultStore.ARCHIVE_STORAGE_DIR)
        if not archive_dir.exists():
            return []

        archives = []
        prefix = f"canvas-{canvas_id}-"

        for archive_file in archive_dir.glob(f"{prefix}*.json"):
            try:
                with open(archive_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 解析 drawing_session_id
                # 文件名: canvas-{canvas_id}-{drawing_session_id}-{timestamp}
                # timestamp格式: YYYYMMDD-HHMMSS-ffffff (8+1+6+1+6=22字符)
                # drawing_session_id在canvas_id之后，timestamp之前
                idx = archive_file.stem.find(canvas_id)
                if idx > 0:
                    # 计算canvas_id之后的剩余部分
                    after_canvas_id = archive_file.stem[idx + len(canvas_id) + 1:]
                    # timestamp固定22字符（YYYYMMDD-HHMMSS-ffffff）加1个连字符=23
                    # 剩余部分 = drawing_session_id + "-" + timestamp
                    if len(after_canvas_id) > 23:
                        drawing_session_id = after_canvas_id[:-23]
                    else:
                        drawing_session_id = after_canvas_id.rsplit("-", 2)[0] if "-" in after_canvas_id else after_canvas_id
                else:
                    drawing_session_id = None

                archives.append({
                    "archive_path": str(archive_file),
                    "archive_name": archive_file.name,
                    "record_count": len(data),
                    "drawing_session_id": drawing_session_id,
                })
            except Exception as e:
                logger.warning(f"Failed to read archive {archive_file}: {e}")

        archives.sort(key=lambda x: x["archive_name"], reverse=True)
        return archives

    def get_by_drawing_session(self, drawing_session_id: str) -> List[CanvasToolResultRecord]:
        """获取指定图案会话的所有记录"""
        with self._lock:
            return [r for r in self._records if r.drawing_session_id == drawing_session_id]

    def load_archive(self, archive_path: str) -> List[CanvasToolResultRecord]:
        """从归档加载记录到内存"""
        with self._lock:
            archive_file = Path(archive_path)
            if not archive_file.exists():
                raise FileNotFoundError(f"Archive not found: {archive_path}")

            with open(archive_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                loaded_records = [CanvasToolResultRecord.from_dict(r) for r in data]

            self._records.extend(loaded_records)
            self._save()
            return loaded_records

    @staticmethod
    def load_archive_static(archive_path: str) -> List[dict]:
        """直接从归档文件读取，不加载到内存（用于查询）"""
        archive_file = Path(archive_path)
        if not archive_file.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        with open(archive_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    @staticmethod
    def get_archive_by_drawing_session_id(canvas_id: str, drawing_session_id: str) -> Optional[dict]:
        """
        根据 drawing_session_id 直接从归档文件查询（无需先加载到内存）

        遍历归档目录，找到匹配的 drawing_session_id 的归档文件
        """
        archive_dir = Path(CanvasToolResultStore.ARCHIVE_STORAGE_DIR)
        if not archive_dir.exists():
            return None

        prefix = f"canvas-{canvas_id}-{drawing_session_id}-"

        for archive_file in archive_dir.glob(f"{prefix}*.json"):
            try:
                with open(archive_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "archive_path": str(archive_file),
                    "archive_name": archive_file.name,
                    "records": data,
                    "record_count": len(data),
                    "drawing_session_id": drawing_session_id,
                }
            except Exception as e:
                logger.warning(f"Failed to read archive {archive_file}: {e}")

        return None
