"""
DragFileHandler - 拖拽文件处理器

将拖拽的文件转换为画板元素
"""

import asyncio
import base64
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .canvas_core import CanvasElement, ElementMetadata, ElementStyles, ElementType


@dataclass
class FileTypeMapping:
    """文件类型映射配置"""
    element_type: str
    mime_types: List[str]


class DragFileHandler:
    """
    拖拽文件处理器

    职责：
    1. 根据文件扩展名和MIME类型确定元素类型
    2. 处理文件数据并创建画板元素
    3. 支持文本、图片、视频、音频等多种文件类型
    """

    # 文件类型映射
    FILE_TYPE_MAPPING: Dict[str, Dict[str, Any]] = {
        # 文本文件
        ".txt": {
            "element_type": ElementType.TEXT.value,
            "mime_types": ["text/plain"],
            "max_size": 1024 * 1024,  # 1MB
        },
        ".md": {
            "element_type": ElementType.TEXT.value,
            "mime_types": ["text/markdown", "text/x-markdown"],
            "max_size": 1024 * 1024,
        },
        ".json": {
            "element_type": ElementType.TEXT.value,
            "mime_types": ["application/json"],
            "max_size": 1024 * 1024,
        },
        # 图片文件
        ".png": {
            "element_type": ElementType.IMAGE.value,
            "mime_types": ["image/png"],
            "max_size": 50 * 1024 * 1024,  # 50MB
        },
        ".jpg": {
            "element_type": ElementType.IMAGE.value,
            "mime_types": ["image/jpeg"],
            "max_size": 50 * 1024 * 1024,
        },
        ".jpeg": {
            "element_type": ElementType.IMAGE.value,
            "mime_types": ["image/jpeg"],
            "max_size": 50 * 1024 * 1024,
        },
        ".gif": {
            "element_type": ElementType.IMAGE.value,
            "mime_types": ["image/gif"],
            "max_size": 50 * 1024 * 1024,
        },
        ".webp": {
            "element_type": ElementType.IMAGE.value,
            "mime_types": ["image/webp"],
            "max_size": 50 * 1024 * 1024,
        },
        ".svg": {
            "element_type": ElementType.IMAGE.value,
            "mime_types": ["image/svg+xml", "image/svg"],
            "max_size": 10 * 1024 * 1024,  # 10MB
        },
        # 视频文件
        ".mp4": {
            "element_type": ElementType.VIDEO.value,
            "mime_types": ["video/mp4"],
            "max_size": 500 * 1024 * 1024,  # 500MB
        },
        ".webm": {
            "element_type": ElementType.VIDEO.value,
            "mime_types": ["video/webm"],
            "max_size": 500 * 1024 * 1024,
        },
        ".mov": {
            "element_type": ElementType.VIDEO.value,
            "mime_types": ["video/quicktime"],
            "max_size": 500 * 1024 * 1024,
        },
        # 音频文件
        ".mp3": {
            "element_type": ElementType.AUDIO.value,
            "mime_types": ["audio/mpeg", "audio/mp3"],
            "max_size": 100 * 1024 * 1024,  # 100MB
        },
        ".wav": {
            "element_type": ElementType.AUDIO.value,
            "mime_types": ["audio/wav", "audio/x-wav"],
            "max_size": 100 * 1024 * 1024,
        },
        ".ogg": {
            "element_type": ElementType.AUDIO.value,
            "mime_types": ["audio/ogg"],
            "max_size": 100 * 1024 * 1024,
        },
        ".m4a": {
            "element_type": ElementType.AUDIO.value,
            "mime_types": ["audio/mp4", "audio/x-m4a"],
            "max_size": 100 * 1024 * 1024,
        },
    }

    def __init__(
        self,
        storage_dir: str = "data/studio/uploads",
        auto_save_files: bool = True,
    ):
        """
        初始化拖拽文件处理器

        Args:
            storage_dir: 文件存储目录
            auto_save_files: 是否自动保存文件到本地
        """
        self._storage_dir = Path(storage_dir)
        self._auto_save_files = auto_save_files
        self._file_id_counter = 0

        if self._auto_save_files:
            self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _generate_file_id(self) -> str:
        """生成唯一文件ID"""
        self._file_id_counter += 1
        return f"file_{uuid.uuid4().hex[:12]}_{self._file_id_counter}"

    def get_file_extension(self, filename: str) -> str:
        """
        获取文件扩展名

        Args:
            filename: 文件名

        Returns:
            扩展名（包含点号）
        """
        return Path(filename).suffix.lower()

    def detect_element_type(
        self,
        filename: str,
        mime_type: str = None,
    ) -> Optional[str]:
        """
        检测元素类型

        Args:
            filename: 文件名
            mime_type: MIME类型（可选）

        Returns:
            元素类型或 None
        """
        ext = self.get_file_extension(filename)

        if ext in self.FILE_TYPE_MAPPING:
            mapping = self.FILE_TYPE_MAPPING[ext]
            if mime_type is None or mime_type in mapping["mime_types"]:
                return mapping["element_type"]

        # 如果没有精确匹配，尝试通过 mime_type 查找
        if mime_type:
            for mapping_ext, mapping in self.FILE_TYPE_MAPPING.items():
                if mime_type in mapping["mime_types"]:
                    return mapping["element_type"]

        return None

    def validate_file(
        self,
        filename: str,
        file_size: int,
        mime_type: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        验证文件

        Args:
            filename: 文件名
            file_size: 文件大小（字节）
            mime_type: MIME类型

        Returns:
            (是否有效, 错误信息)
        """
        ext = self.get_file_extension(filename)

        # 检查扩展名是否支持
        if ext not in self.FILE_TYPE_MAPPING:
            return False, f"不支持的文件类型: {ext}"

        mapping = self.FILE_TYPE_MAPPING[ext]

        # 检查 MIME 类型
        if mime_type and mime_type not in mapping["mime_types"]:
            return False, f"MIME 类型不匹配: {mime_type}"

        # 检查文件大小
        max_size = mapping.get("max_size", 0)
        if max_size > 0 and file_size > max_size:
            return False, f"文件大小超过限制: {file_size} > {max_size}"

        return True, None

    async def handle_file_drop(
        self,
        file_data: bytes,
        filename: str,
        position: Dict[str, float],
        mime_type: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Optional[CanvasElement]:
        """
        处理拖拽的文件

        Args:
            file_data: 文件数据
            filename: 文件名
            position: 放置位置 {x, y}
            mime_type: MIME类型
            metadata: 额外的元数据

        Returns:
            CanvasElement 或 None
        """
        # 检测元素类型
        element_type = self.detect_element_type(filename, mime_type)
        if not element_type:
            return None

        # 验证文件
        is_valid, error = self.validate_file(filename, len(file_data), mime_type)
        if not is_valid:
            print(f"文件验证失败: {error}")
            return None

        # 生成文件ID
        file_id = self._generate_file_id()

        # 保存文件（如果启用）
        local_path = None
        if self._auto_save_files:
            local_path = await self._save_file(file_data, file_id, filename)

        # 创建元素
        element = await self._create_element(
            element_type=element_type,
            element_id=file_id,
            filename=filename,
            position=position,
            file_data=file_data,
            local_path=local_path,
            mime_type=mime_type,
            metadata=metadata,
        )

        return element

    async def _save_file(
        self,
        file_data: bytes,
        file_id: str,
        filename: str,
    ) -> Optional[str]:
        """
        保存文件到本地

        Args:
            file_data: 文件数据
            file_id: 文件ID
            filename: 原文件名

        Returns:
            本地文件路径或 None
        """
        try:
            ext = self.get_file_extension(filename)
            subdir = self._get_file_subdir(ext)
            target_dir = self._storage_dir / subdir
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / f"{file_id}{ext}"

            with open(target_path, "wb") as f:
                f.write(file_data)

            return str(target_path)

        except Exception as e:
            print(f"保存文件失败: {e}")
            return None

    def _get_file_subdir(self, ext: str) -> str:
        """根据扩展名获取子目录"""
        mapping = self.FILE_TYPE_MAPPING.get(ext, {})
        element_type = mapping.get("element_type", "other")

        subdir_map = {
            ElementType.TEXT.value: "texts",
            ElementType.IMAGE.value: "images",
            ElementType.VIDEO.value: "videos",
            ElementType.AUDIO.value: "audio",
        }

        return subdir_map.get(element_type, "other")

    async def _create_element(
        self,
        element_type: str,
        element_id: str,
        filename: str,
        position: Dict[str, float],
        file_data: bytes,
        local_path: Optional[str],
        mime_type: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> CanvasElement:
        """
        创建画板元素

        Args:
            element_type: 元素类型
            element_id: 元素ID
            filename: 文件名
            position: 位置
            file_data: 文件数据
            local_path: 本地路径
            mime_type: MIME类型
            metadata: 额外元数据

        Returns:
            CanvasElement
        """
        ext = self.get_file_extension(filename)

        # 创建元数据和样式
        element_metadata = ElementMetadata()
        element_styles = ElementStyles()

        # 根据元素类型设置属性
        if element_type == ElementType.TEXT.value:
            # 文本文件
            try:
                text_content = file_data.decode("utf-8")
            except UnicodeDecodeError:
                text_content = file_data.decode("latin-1")

            element_metadata.text_content = text_content
            element_metadata.font_size = 14
            element_metadata.font_family = "Arial"

            # 根据内容估算尺寸
            lines = text_content.split("\n")
            max_line_len = max(len(line) for line in lines) if lines else 0
            width = min(max_line_len * 8 + 40, 600)
            height = min(len(lines) * 24 + 40, 400)
            size = {"width": width, "height": height}

        elif element_type == ElementType.IMAGE.value:
            # 图片文件
            element_metadata.mime_type = mime_type or self._get_mime_from_ext(ext)
            element_metadata.local_path = local_path

            # 尝试获取图片尺寸
            width, height = await self._get_image_dimensions(file_data, ext)
            size = {"width": width, "height": height}

            # 如果有URL，使用URL
            if metadata and "url" in metadata:
                element_metadata.url = metadata["url"]

        elif element_type == ElementType.VIDEO.value:
            # 视频文件
            element_metadata.mime_type = mime_type or self._get_mime_from_ext(ext)
            element_metadata.local_path = local_path

            # 默认尺寸
            size = {"width": 640, "height": 360}

            # 获取视频时长
            if metadata and "duration" in metadata:
                element_metadata.duration = metadata["duration"]

            # 缩略图
            if metadata and "thumbnail" in metadata:
                element_metadata.thumbnail_url = metadata["thumbnail"]

        elif element_type == ElementType.AUDIO.value:
            # 音频文件
            element_metadata.mime_type = mime_type or self._get_mime_from_ext(ext)
            element_metadata.local_path = local_path

            # 默认尺寸（显示为音频条）
            size = {"width": 300, "height": 60}

            # 获取音频时长
            if metadata and "duration" in metadata:
                element_metadata.duration = metadata["duration"]

            # 波形数据
            if metadata and "waveform" in metadata:
                element_metadata.waveform_data = metadata["waveform"]

        else:
            # 默认尺寸
            size = {"width": 100, "height": 100}

        # 设置位置
        element_position = position.copy()

        # 设置样式
        element_styles.x = element_position["x"]
        element_styles.y = element_position["y"]
        element_styles.width = size["width"]
        element_styles.height = size["height"]

        # 创建元素
        element = CanvasElement(
            id=element_id,
            type=element_type,
            position=element_position,
            size=size,
            z_index=0,  # 稍后由 CanvasCore 设置
            locked=False,
            visible=True,
            metadata=element_metadata,
            styles=element_styles,
            created_by="user",
        )

        return element

    def _get_mime_from_ext(self, ext: str) -> str:
        """从扩展名获取MIME类型"""
        mapping = self.FILE_TYPE_MAPPING.get(ext, {})
        mime_types = mapping.get("mime_types", [])
        return mime_types[0] if mime_types else "application/octet-stream"

    async def _get_image_dimensions(
        self,
        file_data: bytes,
        ext: str,
    ) -> Tuple[float, float]:
        """
        获取图片尺寸

        Args:
            file_data: 图片数据
            ext: 扩展名

        Returns:
            (宽度, 高度)
        """
        # 默认尺寸
        default_width = 400
        default_height = 300

        try:
            if ext == ".png":
                # PNG 文件头: 89 50 4E 47 0D 0A 1A 0A
                if len(file_data) >= 24:
                    width = int.from_bytes(file_data[16:20], "big")
                    height = int.from_bytes(file_data[20:24], "big")
                    return float(width), float(height)

            elif ext in [".jpg", ".jpeg"]:
                # JPEG 文件 - 简单检测
                # 尝试查找 SOF0 标记 (FF C0)
                # 简化处理，返回默认尺寸
                return default_width, default_height

            elif ext == ".gif":
                # GIF 文件头: 47 49 46 38
                if len(file_data) >= 10:
                    width = int.from_bytes(file_data[6:8], "little")
                    height = int.from_bytes(file_data[8:10], "little")
                    return float(width), float(height)

            elif ext == ".webp":
                # WebP 文件
                if len(file_data) >= 30:
                    # RIFF header
                    if file_data[0:4] == b"RIFF" and file_data[8:12] == b"WEBP":
                        # 简单尺寸检测
                        pass

        except Exception:
            pass

        return default_width, default_height

    async def handle_multiple_files(
        self,
        files: List[Tuple[bytes, str, str]],  # (data, filename, mime_type)
        position: Dict[str, float],
        direction: str = "right",  # 排列方向: right, down
        spacing: float = 20,
    ) -> List[CanvasElement]:
        """
        处理多个文件

        Args:
            files: 文件列表 [(data, filename, mime_type), ...]
            position: 起始位置
            direction: 排列方向
            spacing: 元素间距

        Returns:
            创建的元素列表
        """
        elements = []
        current_x = position["x"]
        current_y = position["y"]
        max_height = 0

        for file_data, filename, mime_type in files:
            element = await self.handle_file_drop(
                file_data=file_data,
                filename=filename,
                position={"x": current_x, "y": current_y},
                mime_type=mime_type,
            )

            if element:
                elements.append(element)

                # 更新位置
                if direction == "right":
                    current_x += element.size["width"] + spacing
                    max_height = max(max_height, element.size["height"])
                else:  # down
                    current_y += element.size["height"] + spacing
                    max_height = max(max_height, element.size["width"])

        return elements

    async def create_element_from_url(
        self,
        url: str,
        element_type: str,
        position: Dict[str, float],
        size: Dict[str, float] = None,
        metadata: Dict[str, Any] = None,
    ) -> CanvasElement:
        """
        从URL创建元素

        Args:
            url: 资源URL
            element_type: 元素类型
            position: 位置
            size: 尺寸（可选）
            metadata: 额外元数据

        Returns:
            CanvasElement
        """
        element_id = self._generate_file_id()
        ext = Path(url).suffix.lower()

        # 默认尺寸
        default_size = {"width": 400, "height": 300}
        if element_type == ElementType.VIDEO.value:
            default_size = {"width": 640, "height": 360}
        elif element_type == ElementType.AUDIO.value:
            default_size = {"width": 300, "height": 60}

        element_size = size or default_size

        # 创建元数据
        element_metadata = ElementMetadata(
            url=url,
            mime_type=self._get_mime_from_ext(ext),
        )

        # 应用额外元数据
        if metadata:
            if "duration" in metadata:
                element_metadata.duration = metadata["duration"]
            if "thumbnail" in metadata:
                element_metadata.thumbnail_url = metadata["thumbnail"]
            if "waveform" in metadata:
                element_metadata.waveform_data = metadata["waveform"]

        # 创建样式
        element_styles = ElementStyles(
            x=position["x"],
            y=position["y"],
            width=element_size["width"],
            height=element_size["height"],
        )

        # 创建元素
        element = CanvasElement(
            id=element_id,
            type=element_type,
            position=position,
            size=element_size,
            z_index=0,
            locked=False,
            visible=True,
            metadata=element_metadata,
            styles=element_styles,
            created_by="user",
        )

        return element

    def get_supported_extensions(self) -> List[str]:
        """获取支持的文件扩展名"""
        return list(self.FILE_TYPE_MAPPING.keys())

    def get_supported_mime_types(self) -> List[str]:
        """获取支持的MIME类型"""
        mime_types = set()
        for mapping in self.FILE_TYPE_MAPPING.values():
            mime_types.update(mapping["mime_types"])
        return list(mime_types)

    def is_supported_file(self, filename: str, mime_type: str = None) -> bool:
        """
        检查是否支持该文件

        Args:
            filename: 文件名
            mime_type: MIME类型

        Returns:
            是否支持
        """
        return self.detect_element_type(filename, mime_type) is not None
