"""
CanvasCore - 画板核心

提供画板状态管理和操作引擎
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable


class ElementType(Enum):
    """元素类型"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    SHAPE = "shape"
    GROUP = "group"
    DRAWING = "drawing"


class CreatorType(Enum):
    """创建者类型"""
    USER = "user"
    AGENT = "agent"


class OperationType(Enum):
    """操作类型"""
    CREATE = "create"
    DELETE = "delete"
    UPDATE = "update"
    MOVE = "move"
    RESIZE = "resize"
    ROTATE = "rotate"
    STYLE = "style"
    GROUP = "group"
    UNGROUP = "ungroup"
    PASTE = "paste"
    DUPLICATE = "duplicate"
    ALIGN = "align"
    TEXT_EDIT = "text_edit"
    LASSO_SELECT = "lasso_select"
    ELEMENT_SELECT = "element_select"


@dataclass
class ElementMetadata:
    """元素元数据（类型特定）"""
    # 文本元素
    text_content: Optional[str] = None
    font_size: Optional[int] = None
    font_family: Optional[str] = None
    text_align: Optional[str] = None
    line_height: Optional[float] = None

    # 图片/视频元素
    url: Optional[str] = None
    local_path: Optional[str] = None
    mime_type: Optional[str] = None
    duration: Optional[float] = None  # 视频/音频时长

    # 视频元素
    thumbnail_url: Optional[str] = None

    # 音频元素
    waveform_data: Optional[List[float]] = None

    # 形状元素
    shape_type: Optional[str] = None  # rect, circle, line, polygon
    points: Optional[List[Dict[str, float]]] = None

    # 绘画专用属性
    stroke_color: Optional[str] = None      # 描边颜色
    stroke_width: Optional[float] = None    # 描边宽度
    fill_color: Optional[str] = None        # 填充颜色
    drawing_paths: Optional[List[Dict[str, Any]]] = None  # 绘画路径数据
    svg_path: Optional[str] = None          # SVG path 路径数据（用于自由曲线）

    # 组合元素
    child_ids: Optional[List[str]] = None

    # 通用
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text_content": self.text_content,
            "font_size": self.font_size,
            "font_family": self.font_family,
            "text_align": self.text_align,
            "line_height": self.line_height,
            "url": self.url,
            "local_path": self.local_path,
            "mime_type": self.mime_type,
            "duration": self.duration,
            "thumbnail_url": self.thumbnail_url,
            "waveform_data": self.waveform_data,
            "shape_type": self.shape_type,
            "points": self.points,
            "stroke_color": self.stroke_color,
            "stroke_width": self.stroke_width,
            "fill_color": self.fill_color,
            "drawing_paths": self.drawing_paths,
            "svg_path": self.svg_path,
            "child_ids": self.child_ids,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ElementMetadata":
        """从字典创建"""
        if data is None:
            return cls()
        return cls(
            text_content=data.get("text_content"),
            font_size=data.get("font_size"),
            font_family=data.get("font_family"),
            text_align=data.get("text_align"),
            line_height=data.get("line_height"),
            url=data.get("url"),
            local_path=data.get("local_path"),
            mime_type=data.get("mime_type"),
            duration=data.get("duration"),
            thumbnail_url=data.get("thumbnail_url"),
            waveform_data=data.get("waveform_data"),
            shape_type=data.get("shape_type"),
            points=data.get("points"),
            stroke_color=data.get("stroke_color"),
            stroke_width=data.get("stroke_width"),
            fill_color=data.get("fill_color"),
            drawing_paths=data.get("drawing_paths"),
            svg_path=data.get("svg_path"),
            child_ids=data.get("child_ids"),
            extra=data.get("extra", {}),
        )


@dataclass
class ElementStyles:
    """元素样式"""
    # 位置与尺寸
    x: float = 0
    y: float = 0
    width: float = 100
    height: float = 100
    rotation: float = 0  # 旋转角度（度）

    # 外观
    fill: Optional[str] = None  # 填充色
    stroke: Optional[str] = None  # 边框色
    stroke_width: float = 1
    opacity: float = 1
    corner_radius: float = 0  # 圆角

    # 阴影
    shadow_enabled: bool = False
    shadow_color: Optional[str] = None
    shadow_blur: float = 10
    shadow_offset_x: float = 0
    shadow_offset_y: float = 0

    # 特效
    blur: float = 0
    brightness: float = 1
    contrast: float = 1

    # 文本样式
    color: Optional[str] = None  # 文本颜色
    bold: bool = False
    italic: bool = False
    underline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "fill": self.fill,
            "stroke": self.stroke,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "corner_radius": self.corner_radius,
            "shadow_enabled": self.shadow_enabled,
            "shadow_color": self.shadow_color,
            "shadow_blur": self.shadow_blur,
            "shadow_offset_x": self.shadow_offset_x,
            "shadow_offset_y": self.shadow_offset_y,
            "blur": self.blur,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "color": self.color,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ElementStyles":
        """从字典创建"""
        if data is None:
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CanvasElement:
    """
    画板元素

    属性说明：
    - id: 唯一标识符
    - type: 元素类型（text/image/video/audio/shape/group）
    - position: 位置 {x, y}
    - size: 尺寸 {width, height}
    - zIndex: 层级
    - locked: 是否锁定
    - visible: 是否可见
    - metadata: 类型特定元数据
    - styles: 样式
    - created_by: 创建者（user/agent）
    """
    id: str
    type: str  # ElementType value
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    size: Dict[str, float] = field(default_factory=lambda: {"width": 100, "height": 100})
    z_index: int = 0
    locked: bool = False
    visible: bool = True
    metadata: ElementMetadata = field(default_factory=ElementMetadata)
    styles: ElementStyles = field(default_factory=ElementStyles)
    created_by: str = "user"  # CreatorType value
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    parent_id: Optional[str] = None  # 父元素ID（用于组合）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        metadata_dict = self.metadata.to_dict()
        # 转换 points 格式：从 [{x, y}, ...] 转换为 [[x, y], ...]
        if metadata_dict.get("points") and len(metadata_dict["points"]) > 0:
            if isinstance(metadata_dict["points"][0], dict):
                metadata_dict["points"] = [[p["x"], p["y"]] for p in metadata_dict["points"]]
        return {
            "id": self.id,
            "type": self.type,
            "position": self.position,
            "size": self.size,
            "z_index": self.z_index,
            "locked": self.locked,
            "visible": self.visible,
            "metadata": metadata_dict,
            "styles": self.styles.to_dict(),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, 'isoformat') else self.created_at,
            "updated_at": self.updated_at.isoformat() if hasattr(self.updated_at, 'isoformat') else self.updated_at,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanvasElement":
        """从字典创建"""
        if data is None:
            return None

        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            metadata = ElementMetadata.from_dict(metadata)

        styles = data.get("styles")
        if isinstance(styles, dict):
            styles = ElementStyles.from_dict(styles)

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
            id=data["id"],
            type=data["type"],
            position=data.get("position", {"x": 0, "y": 0}),
            size=data.get("size", {"width": 100, "height": 100}),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            visible=data.get("visible", True),
            metadata=metadata or ElementMetadata(),
            styles=styles or ElementStyles(),
            created_by=data.get("created_by", "user"),
            created_at=created_at,
            updated_at=updated_at,
            parent_id=data.get("parent_id"),
        )

    def get_bounds(self) -> Dict[str, float]:
        """获取元素边界框"""
        return {
            "x": self.position["x"],
            "y": self.position["y"],
            "width": self.size["width"],
            "height": self.size["height"],
        }

    def contains_point(self, x: float, y: float) -> bool:
        """检查点是否在元素内"""
        bounds = self.get_bounds()
        return (
            bounds["x"] <= x <= bounds["x"] + bounds["width"]
            and bounds["y"] <= y <= bounds["y"] + bounds["height"]
        )

    def intersects_rect(self, rect: Dict[str, float]) -> bool:
        """检查是否与矩形相交"""
        bounds = self.get_bounds()
        return not (
            bounds["x"] + bounds["width"] < rect["x"]
            or rect["x"] + rect["width"] < bounds["x"]
            or bounds["y"] + bounds["height"] < rect["y"]
            or rect["y"] + rect["height"] < bounds["y"]
        )


@dataclass
class CanvasOperation:
    """
    画板操作

    属性说明：
    - id: 操作唯一标识符
    - type: 操作类型
    - target_ids: 目标元素ID列表
    - before_state: 操作前的状态
    - after_state: 操作后的状态
    - timestamp: 操作时间
    - creator: 创建者
    """
    id: str
    type: str  # OperationType value
    target_ids: List[str] = field(default_factory=list)
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    creator: str = "user"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "target_ids": self.target_ids,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, 'isoformat') else self.timestamp,
            "creator": self.creator,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanvasOperation":
        """从字典创建"""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            id=data["id"],
            type=data["type"],
            target_ids=data.get("target_ids", []),
            before_state=data.get("before_state", {}),
            after_state=data.get("after_state", {}),
            timestamp=timestamp,
            creator=data.get("creator", "user"),
            description=data.get("description", ""),
        )


@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    operation_id: str
    element_id: Optional[str] = None
    affected_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "operation_id": self.operation_id,
            "element_id": self.element_id,
            "affected_ids": self.affected_ids,
            "error": self.error,
            "warning": self.warning,
        }


@dataclass
class LassoSelection:
    """
    自由框选

    属性说明：
    - id: 框选唯一标识符
    - type: 类型（固定为 'lasso'）
    - points: 自由绘制的点序列
    - closed: 是否闭合
    """
    id: str
    type: str = "lasso"
    points: List[Dict[str, float]] = field(default_factory=list)
    closed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "points": self.points,
            "closed": self.closed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LassoSelection":
        """从字典创建"""
        if data is None:
            return None
        return cls(
            id=data["id"],
            type=data.get("type", "lasso"),
            points=data.get("points", []),
            closed=data.get("closed", False),
        )

    def get_bounds(self) -> Dict[str, float]:
        """获取框选边界框"""
        if not self.points:
            return {"x": 0, "y": 0, "width": 0, "height": 0}

        xs = [p["x"] for p in self.points]
        ys = [p["y"] for p in self.points]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        return {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        }

    def contains_point(self, x: float, y: float) -> bool:
        """检查点是否在多边形内（射线法）"""
        if not self.closed or len(self.points) < 3:
            bounds = self.get_bounds()
            return (
                bounds["x"] <= x <= bounds["x"] + bounds["width"]
                and bounds["y"] <= y <= bounds["y"] + bounds["height"]
            )

        n = len(self.points)
        inside = False
        j = n - 1

        for i in range(n):
            xi, yi = self.points[i]["x"], self.points[i]["y"]
            xj, yj = self.points[j]["x"], self.points[j]["y"]

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside


@dataclass
class SelectionRegion:
    """
    选中区域

    属性说明：
    - type: 区域类型（lasso/rect/element）
    - bounds: 边界框
    - element_ids: 框选区域内的元素ID列表
    - extracted_content: 提取的内容
    - lasso: 自由框选数据（如果 type 为 lasso）
    """
    id: str
    type: str  # 'lasso' | 'rect' | 'element'
    bounds: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "width": 0, "height": 0})
    element_ids: List[str] = field(default_factory=list)
    lasso: Optional[LassoSelection] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "bounds": self.bounds,
            "element_ids": self.element_ids,
            "lasso": self.lasso.to_dict() if self.lasso else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelectionRegion":
        """从字典创建"""
        if data is None:
            return None

        lasso = data.get("lasso")
        if isinstance(lasso, dict):
            lasso = LassoSelection.from_dict(lasso)

        return cls(
            id=data["id"],
            type=data["type"],
            bounds=data.get("bounds", {"x": 0, "y": 0, "width": 0, "height": 0}),
            element_ids=data.get("element_ids", []),
            lasso=lasso,
        )


@dataclass
class ExtractedContent:
    """
    提取的内容

    属性说明：
    - texts: 提取的文本列表
    - images: 提取的图片列表
    - videos: 提取的视频列表
    - audio: 提取的音频列表
    - summary: 区域摘要供Agent理解
    """
    texts: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[Dict[str, Any]] = field(default_factory=list)
    audio: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "texts": self.texts,
            "images": self.images,
            "videos": self.videos,
            "audio": self.audio,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedContent":
        """从字典创建"""
        if data is None:
            return cls()
        return cls(
            texts=data.get("texts", []),
            images=data.get("images", []),
            videos=data.get("videos", []),
            audio=data.get("audio", []),
            summary=data.get("summary", ""),
        )

    def is_empty(self) -> bool:
        """检查是否为空"""
        return not (self.texts or self.images or self.videos or self.audio)


@dataclass
class CanvasSnapshot:
    """
    画板快照

    属性说明：
    - canvas_id: 画板ID
    - name: 画板名称
    - width: 画板宽度
    - height: 画板高度
    - background_color: 背景颜色
    - elements: 元素列表
    - operation_history: 操作历史
    - selection: 当前选中区域
    - timestamp: 快照时间
    """
    canvas_id: str
    name: str = "Untitled"
    width: float = 1920
    height: float = 1080
    background_color: str = "#ffffff"
    elements: List[CanvasElement] = field(default_factory=list)
    operation_history: List[CanvasOperation] = field(default_factory=list)
    selection: Optional[SelectionRegion] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "canvas_id": self.canvas_id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "background_color": self.background_color,
            "elements": [e.to_dict() for e in self.elements],
            "operation_history": [o.to_dict() for o in self.operation_history],
            "selection": self.selection.to_dict() if self.selection else None,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, 'isoformat') else self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanvasSnapshot":
        """从字典创建"""
        if data is None:
            return None

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        selection = data.get("selection")
        if isinstance(selection, dict):
            selection = SelectionRegion.from_dict(selection)

        return cls(
            canvas_id=data["canvas_id"],
            name=data.get("name", "Untitled"),
            width=data.get("width", 1920),
            height=data.get("height", 1080),
            background_color=data.get("background_color", "#ffffff"),
            elements=[CanvasElement.from_dict(e) for e in data.get("elements", [])],
            operation_history=[CanvasOperation.from_dict(o) for o in data.get("operation_history", [])],
            selection=selection,
            timestamp=timestamp,
        )


class CanvasCore:
    """
    画板核心：状态管理、操作引擎

    职责：
    1. 管理画板元素（增删改查）
    2. 执行操作并记录历史
    3. 支持撤销/重做
    4. 管理选择区域
    5. 生成快照
    """

    def __init__(
        self,
        canvas_id: str,
        storage_dir: Optional[str] = None,
        auto_save: bool = True,
        max_history: int = 100,
        name: str = "Untitled",
        width: float = 1920,
        height: float = 1080,
        background_color: str = "#ffffff",
    ):
        """
        初始化画板核心

        Args:
            canvas_id: 画板ID
            storage_dir: 存储目录
            auto_save: 是否自动保存
            max_history: 最大历史记录数
            name: 画板名称
            width: 画板宽度
            height: 画板高度
            background_color: 背景颜色
        """
        self.canvas_id = canvas_id
        self.name = name
        self.width = width
        self.height = height
        self.background_color = background_color
        self._elements: Dict[str, CanvasElement] = {}  # id -> element
        self._z_index_map: Dict[int, str] = {}  # z_index -> element_id
        self._max_z_index: int = 0
        self._undo_stack: List[CanvasOperation] = []
        self._redo_stack: List[CanvasOperation] = []
        self._max_history = max_history
        self._current_selection: Optional[SelectionRegion] = None
        self._storage_dir = storage_dir
        self._auto_save = auto_save
        self._lock = asyncio.Lock()
        self._change_callbacks: List[Callable] = []

    @property
    def elements(self) -> List[CanvasElement]:
        """获取所有元素"""
        return list(self._elements.values())

    @property
    def selection(self) -> Optional[SelectionRegion]:
        """获取当前选择"""
        return self._current_selection

    @property
    def can_undo(self) -> bool:
        """是否可以撤销"""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """是否可以重做"""
        return len(self._redo_stack) > 0

    def on_change(self, callback: Callable) -> None:
        """注册变更回调"""
        self._change_callbacks.append(callback)

    async def _notify_change(self, operation: Optional[CanvasOperation] = None) -> None:
        """通知变更"""
        for callback in self._change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(operation)
                else:
                    callback(operation)
            except Exception:
                pass

    def _generate_id(self) -> str:
        """生成唯一ID"""
        return f"{uuid.uuid4().hex[:12]}"

    def _get_next_z_index(self) -> int:
        """获取下一个z索引"""
        self._max_z_index += 1
        return self._max_z_index

    def _update_z_index_map(self, element: CanvasElement) -> None:
        """更新z索引映射"""
        if element.z_index in self._z_index_map:
            del self._z_index_map[element.z_index]
        self._z_index_map[element.z_index] = element.id

    def _rebuild_z_index_map(self) -> None:
        """重建z索引映射"""
        self._z_index_map.clear()
        for element in sorted(self._elements.values(), key=lambda e: e.z_index):
            self._z_index_map[element.z_index] = element.id
        if self._elements:
            self._max_z_index = max(e.z_index for e in self._elements.values())
        else:
            self._max_z_index = 0

    async def execute_operation(self, op: CanvasOperation) -> OperationResult:
        """
        执行操作

        Args:
            op: 操作对象

        Returns:
            OperationResult: 操作结果
        """
        async with self._lock:
            try:
                op_type = op.type

                # 根据操作类型执行
                if op_type == OperationType.CREATE.value:
                    return await self._execute_create(op)
                elif op_type == OperationType.DELETE.value:
                    return await self._execute_delete(op)
                elif op_type == OperationType.UPDATE.value:
                    return await self._execute_update(op)
                elif op_type == OperationType.MOVE.value:
                    return await self._execute_move(op)
                elif op_type == OperationType.RESIZE.value:
                    return await self._execute_resize(op)
                elif op_type == OperationType.ROTATE.value:
                    return await self._execute_rotate(op)
                elif op_type == OperationType.STYLE.value:
                    return await self._execute_style(op)
                elif op_type == OperationType.GROUP.value:
                    return await self._execute_group(op)
                elif op_type == OperationType.UNGROUP.value:
                    return await self._execute_ungroup(op)
                elif op_type == OperationType.DUPLICATE.value:
                    return await self._execute_duplicate(op)
                elif op_type == OperationType.ALIGN.value:
                    return await self._execute_align(op)
                elif op_type == OperationType.TEXT_EDIT.value:
                    return await self._execute_text_edit(op)
                elif op_type == OperationType.LASSO_SELECT.value:
                    return await self._execute_lasso_select(op)
                elif op_type == OperationType.ELEMENT_SELECT.value:
                    return await self._execute_element_select(op)
                else:
                    return OperationResult(
                        success=False,
                        operation_id=op.id,
                        error=f"Unknown operation type: {op_type}",
                    )

            except Exception as e:
                return OperationResult(
                    success=False,
                    operation_id=op.id,
                    error=str(e),
                )

    async def _execute_create(self, op: CanvasOperation) -> OperationResult:
        """执行创建操作"""
        element_data = op.after_state.get("element")
        if not element_data:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="Missing element data",
            )

        element = CanvasElement.from_dict(element_data)
        if not element.id:
            element.id = self._generate_id()

        # 设置z索引
        if element.z_index == 0:
            element.z_index = self._get_next_z_index()

        # 保存操作前状态
        op.before_state = {"element": None}

        # 添加元素
        self._elements[element.id] = element
        self._update_z_index_map(element)

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            element_id=element.id,
            affected_ids=[element.id],
        )

    async def _execute_delete(self, op: CanvasOperation) -> OperationResult:
        """执行删除操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        # 收集要删除的 ID（包括父组合）
        ids_to_delete = set(target_ids)

        # 检查是否有子元素需要连带删除父组合
        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 如果元素有 parent_id，说明它是组合的子元素
                # 删除时也应该删除父组合
                if element.parent_id and element.parent_id in self._elements:
                    parent = self._elements[element.parent_id]
                    if parent.type == ElementType.GROUP.value:
                        ids_to_delete.add(parent.id)
                        # 如果父组合还有其他子元素，也要一起删除
                        if parent.metadata and parent.metadata.child_ids:
                            for child_id in parent.metadata.child_ids:
                                ids_to_delete.add(child_id)

        # 同时处理删除组合时连带删除所有子元素的情况
        for target_id in list(ids_to_delete):
            if target_id in self._elements:
                element = self._elements[target_id]
                if element.type == ElementType.GROUP.value:
                    # 删除组合时，也要删除所有子元素
                    if element.metadata and element.metadata.child_ids:
                        for child_id in element.metadata.child_ids:
                            ids_to_delete.add(child_id)

        affected_ids = []
        for target_id in ids_to_delete:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 保存删除前的状态
                op.before_state[target_id] = element.to_dict()
                del self._elements[target_id]
                affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No elements found to delete",
            )

        # 重建z索引映射
        self._rebuild_z_index_map()

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_update(self, op: CanvasOperation) -> OperationResult:
        """执行更新操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        updates = op.after_state.get("updates", {})
        affected_ids = []

        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 保存更新前的状态
                op.before_state[target_id] = element.to_dict()

                # 应用更新
                if "position" in updates:
                    element.position = updates["position"]
                if "size" in updates:
                    element.size = updates["size"]
                if "z_index" in updates:
                    element.z_index = updates["z_index"]
                    self._update_z_index_map(element)
                if "locked" in updates:
                    element.locked = updates["locked"]
                if "visible" in updates:
                    element.visible = updates["visible"]
                if "metadata" in updates:
                    metadata = updates["metadata"]
                    if isinstance(metadata, dict):
                        element.metadata = ElementMetadata.from_dict(metadata)
                    else:
                        element.metadata = metadata
                if "styles" in updates:
                    styles = updates["styles"]
                    if isinstance(styles, dict):
                        element.styles = ElementStyles.from_dict(styles)
                    else:
                        element.styles = styles

                element.updated_at = datetime.now()
                affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No elements found to update",
            )

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_move(self, op: CanvasOperation) -> OperationResult:
        """执行移动操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        delta = op.after_state.get("delta", {"x": 0, "y": 0})
        affected_ids = []

        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 保存移动前的状态
                op.before_state[target_id] = element.to_dict()

                # 应用移动
                element.position = {
                    "x": element.position["x"] + delta["x"],
                    "y": element.position["y"] + delta["y"],
                }
                element.updated_at = datetime.now()
                affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No elements found to move",
            )

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_resize(self, op: CanvasOperation) -> OperationResult:
        """执行缩放操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        new_size = op.after_state.get("size", {"width": 100, "height": 100})
        affected_ids = []

        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 保存缩放前的状态
                op.before_state[target_id] = element.to_dict()

                # 应用缩放
                element.size = new_size.copy()
                element.updated_at = datetime.now()
                affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No elements found to resize",
            )

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_rotate(self, op: CanvasOperation) -> OperationResult:
        """执行旋转操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        angle = op.after_state.get("angle", 0)
        affected_ids = []

        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 保存旋转前的状态
                op.before_state[target_id] = element.to_dict()

                # 应用旋转
                element.styles.rotation = (element.styles.rotation + angle) % 360
                element.updated_at = datetime.now()
                affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No elements found to rotate",
            )

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_style(self, op: CanvasOperation) -> OperationResult:
        """执行样式操作"""
        return await self._execute_update(op)

    async def _execute_group(self, op: CanvasOperation) -> OperationResult:
        """执行组合操作"""
        target_ids = op.target_ids
        if len(target_ids) < 2:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="Need at least 2 elements to group",
            )

        # 获取所有目标元素
        elements_to_group = []
        for target_id in target_ids:
            if target_id in self._elements:
                elements_to_group.append(self._elements[target_id])

        if len(elements_to_group) < 2:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="Need at least 2 valid elements to group",
            )

        # 计算组合边界
        min_x = min(e.position["x"] for e in elements_to_group)
        min_y = min(e.position["y"] for e in elements_to_group)
        max_x = max(e.position["x"] + e.size["width"] for e in elements_to_group)
        max_y = max(e.position["y"] + e.size["height"] for e in elements_to_group)

        # 创建组合元素
        group_id = self._generate_id()
        group_element = CanvasElement(
            id=group_id,
            type=ElementType.GROUP.value,
            position={"x": min_x, "y": min_y},
            size={"width": max_x - min_x, "height": max_y - min_y},
            z_index=self._get_next_z_index(),
            metadata=ElementMetadata(child_ids=target_ids),
            created_by=op.creator,
            locked=True,  # 组合创建后自动锁定
        )

        # 保存组合前状态
        op.before_state = {"elements": {e.id: e.to_dict() for e in elements_to_group}}

        # 更新子元素
        for element in elements_to_group:
            element.parent_id = group_id
            element.locked = True  # 锁定子元素，确保组合整体拖动
            element.updated_at = datetime.now()

        # 添加组合元素
        self._elements[group_id] = group_element
        self._update_z_index_map(group_element)

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            element_id=group_id,
            affected_ids=[group_id] + target_ids,
        )

    async def _execute_ungroup(self, op: CanvasOperation) -> OperationResult:
        """执行取消组合操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        affected_ids = []
        group_ids = []

        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                if element.type == ElementType.GROUP.value:
                    # 保存取消组合前的状态
                    op.before_state[target_id] = element.to_dict()

                    # 获取子元素ID
                    child_ids = element.metadata.child_ids or []
                    group_ids.append(target_id)

                    # 清除子元素的parent_id
                    for child_id in child_ids:
                        if child_id in self._elements:
                            self._elements[child_id].parent_id = None
                            self._elements[child_id].updated_at = datetime.now()
                            affected_ids.append(child_id)

                    # 删除组合元素
                    del self._elements[target_id]
                    affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No groups found to ungroup",
            )

        # 重建z索引映射
        self._rebuild_z_index_map()

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_duplicate(self, op: CanvasOperation) -> OperationResult:
        """执行复制操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        offset = op.after_state.get("offset", {"x": 20, "y": 20})
        affected_ids = []
        new_ids_map = {}  # old_id -> new_id

        # 保存复制前的状态
        op.before_state = {}

        for target_id in target_ids:
            if target_id in self._elements:
                original = self._elements[target_id]
                op.before_state[target_id] = original.to_dict()

                # 创建副本
                new_id = self._generate_id()
                duplicate = CanvasElement.from_dict(original.to_dict())
                duplicate.id = new_id
                duplicate.position = {
                    "x": duplicate.position["x"] + offset["x"],
                    "y": duplicate.position["y"] + offset["y"],
                }
                duplicate.z_index = self._get_next_z_index()
                duplicate.created_at = datetime.now()
                duplicate.updated_at = datetime.now()
                duplicate.parent_id = None  # 重置父元素

                # 如果是组合，同时复制子元素
                if duplicate.type == ElementType.GROUP.value:
                    child_ids = duplicate.metadata.child_ids or []
                    new_child_ids = []
                    for child_id in child_ids:
                        if child_id in self._elements:
                            original_child = self._elements[child_id]
                            new_child_id = self._generate_id()
                            child_duplicate = CanvasElement.from_dict(original_child.to_dict())
                            child_duplicate.id = new_child_id
                            child_duplicate.position = {
                                "x": child_duplicate.position["x"] + offset["x"],
                                "y": child_duplicate.position["y"] + offset["y"],
                            }
                            child_duplicate.parent_id = new_id
                            child_duplicate.z_index = self._get_next_z_index()
                            self._elements[new_child_id] = child_duplicate
                            new_child_ids.append(new_child_id)
                            affected_ids.append(new_child_id)
                    duplicate.metadata.child_ids = new_child_ids

                self._elements[new_id] = duplicate
                new_ids_map[target_id] = new_id
                affected_ids.append(new_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No elements found to duplicate",
            )

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_align(self, op: CanvasOperation) -> OperationResult:
        """执行对齐操作"""
        target_ids = op.target_ids
        if len(target_ids) < 2:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="Need at least 2 elements to align",
            )

        align_type = op.after_state.get("align_type", "left")
        affected_ids = []

        # 获取所有目标元素
        elements_to_align = []
        for target_id in target_ids:
            if target_id in self._elements:
                elements_to_align.append(self._elements[target_id])

        if len(elements_to_align) < 2:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="Need at least 2 valid elements to align",
            )

        # 保存对齐前的状态
        op.before_state = {e.id: e.to_dict() for e in elements_to_align}

        # 计算对齐位置
        if align_type == "left":
            min_x = min(e.position["x"] for e in elements_to_align)
            for element in elements_to_align:
                element.position["x"] = min_x
                element.updated_at = datetime.now()
                affected_ids.append(element.id)
        elif align_type == "right":
            max_x = max(e.position["x"] + e.size["width"] for e in elements_to_align)
            for element in elements_to_align:
                element.position["x"] = max_x - element.size["width"]
                element.updated_at = datetime.now()
                affected_ids.append(element.id)
        elif align_type == "top":
            min_y = min(e.position["y"] for e in elements_to_align)
            for element in elements_to_align:
                element.position["y"] = min_y
                element.updated_at = datetime.now()
                affected_ids.append(element.id)
        elif align_type == "bottom":
            max_y = max(e.position["y"] + e.size["height"] for e in elements_to_align)
            for element in elements_to_align:
                element.position["y"] = max_y - element.size["height"]
                element.updated_at = datetime.now()
                affected_ids.append(element.id)
        elif align_type == "center_h":
            center_x = sum(e.position["x"] + e.size["width"] / 2 for e in elements_to_align) / len(elements_to_align)
            for element in elements_to_align:
                element.position["x"] = center_x - element.size["width"] / 2
                element.updated_at = datetime.now()
                affected_ids.append(element.id)
        elif align_type == "center_v":
            center_y = sum(e.position["y"] + e.size["height"] / 2 for e in elements_to_align) / len(elements_to_align)
            for element in elements_to_align:
                element.position["y"] = center_y - element.size["height"] / 2
                element.updated_at = datetime.now()
                affected_ids.append(element.id)

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_text_edit(self, op: CanvasOperation) -> OperationResult:
        """执行文本编辑操作"""
        target_ids = op.target_ids
        if not target_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No target ids specified",
            )

        new_text = op.after_state.get("text", "")
        affected_ids = []

        for target_id in target_ids:
            if target_id in self._elements:
                element = self._elements[target_id]
                # 保存编辑前的状态
                op.before_state[target_id] = element.to_dict()

                # 应用文本编辑
                element.metadata.text_content = new_text
                element.updated_at = datetime.now()
                affected_ids.append(target_id)

        if not affected_ids:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No text elements found to edit",
            )

        # 添加到撤销栈
        self._add_to_undo_stack(op)

        # 触发变更通知
        await self._notify_change(op)

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=affected_ids,
        )

    async def _execute_lasso_select(self, op: CanvasOperation) -> OperationResult:
        """执行自由框选操作"""
        lasso_data = op.after_state.get("lasso")
        if not lasso_data:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="Missing lasso data",
            )

        lasso = LassoSelection.from_dict(lasso_data)
        bounds = lasso.get_bounds()

        # 查找与框选区域相交的元素
        element_ids = []
        for element in self._elements.values():
            if not element.visible or element.locked:
                continue
            if element.intersects_rect(bounds):
                element_ids.append(element.id)

        # 创建选择区域
        selection_id = self._generate_id()
        self._current_selection = SelectionRegion(
            id=selection_id,
            type="lasso",
            bounds=bounds,
            element_ids=element_ids,
            lasso=lasso,
        )

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=element_ids,
        )

    async def _execute_element_select(self, op: CanvasOperation) -> OperationResult:
        """执行元素选择操作"""
        target_ids = op.target_ids
        if not target_ids:
            # 清除选择
            self._current_selection = None
            return OperationResult(
                success=True,
                operation_id=op.id,
                affected_ids=[],
            )

        # 获取选中元素的边界
        selected_elements = []
        for target_id in target_ids:
            if target_id in self._elements:
                selected_elements.append(self._elements[target_id])

        if not selected_elements:
            return OperationResult(
                success=False,
                operation_id=op.id,
                error="No valid elements selected",
            )

        min_x = min(e.position["x"] for e in selected_elements)
        min_y = min(e.position["y"] for e in selected_elements)
        max_x = max(e.position["x"] + e.size["width"] for e in selected_elements)
        max_y = max(e.position["y"] + e.size["height"] for e in selected_elements)

        # 创建选择区域
        selection_id = self._generate_id()
        self._current_selection = SelectionRegion(
            id=selection_id,
            type="element",
            bounds={
                "x": min_x,
                "y": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            },
            element_ids=target_ids,
        )

        return OperationResult(
            success=True,
            operation_id=op.id,
            affected_ids=target_ids,
        )

    def _add_to_undo_stack(self, op: CanvasOperation) -> None:
        """添加操作到撤销栈"""
        self._undo_stack.append(op)
        # 清除重做栈
        self._redo_stack.clear()
        # 限制历史记录数量
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

    async def add_element(self, element: CanvasElement) -> bool:
        """
        添加元素

        Args:
            element: 元素对象

        Returns:
            bool: 是否成功
        """
        op = CanvasOperation(
            id=self._generate_id(),
            type=OperationType.CREATE.value,
            target_ids=[element.id],
            after_state={"element": element.to_dict()},
            creator=element.created_by,
        )
        result = await self.execute_operation(op)
        return result.success

    async def update_element(self, element_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新元素

        Args:
            element_id: 元素ID
            updates: 更新内容

        Returns:
            bool: 是否成功
        """
        op = CanvasOperation(
            id=self._generate_id(),
            type=OperationType.UPDATE.value,
            target_ids=[element_id],
            after_state={"updates": updates},
        )
        result = await self.execute_operation(op)
        return result.success

    async def delete_elements(self, ids: List[str]) -> bool:
        """
        删除元素

        Args:
            ids: 元素ID列表

        Returns:
            bool: 是否成功
        """
        op = CanvasOperation(
            id=self._generate_id(),
            type=OperationType.DELETE.value,
            target_ids=ids,
        )
        result = await self.execute_operation(op)
        return result.success

    def get_element(self, element_id: str) -> Optional[CanvasElement]:
        """
        获取元素

        Args:
            element_id: 元素ID

        Returns:
            CanvasElement 或 None
        """
        return self._elements.get(element_id)

    def get_elements_in_rect(self, rect: Dict[str, float]) -> List[CanvasElement]:
        """
        获取矩形区域内的元素

        Args:
            rect: 矩形区域 {x, y, width, height}

        Returns:
            元素列表
        """
        result = []
        for element in self._elements.values():
            if element.visible and element.intersects_rect(rect):
                result.append(element)
        return result

    def get_element_at_point(self, x: float, y: float) -> Optional[CanvasElement]:
        """
        获取指定点的元素（按z索引倒序，即顶层优先）

        Args:
            x: x坐标
            y: y坐标

        Returns:
            CanvasElement 或 None
        """
        # 按z索引倒序遍历
        for element in sorted(self._elements.values(), key=lambda e: e.z_index, reverse=True):
            if element.visible and not element.locked and element.contains_point(x, y):
                return element
        return None

    def get_snapshot(self) -> CanvasSnapshot:
        """
        获取画板快照

        Returns:
            CanvasSnapshot: 快照对象
        """
        return CanvasSnapshot(
            canvas_id=self.canvas_id,
            name=self.name,
            width=self.width,
            height=self.height,
            background_color=self.background_color,
            elements=list(self._elements.values()),
            operation_history=self._undo_stack.copy(),
            selection=self._current_selection,
            timestamp=datetime.now(),
        )

    async def load_from_snapshot(self, snapshot: CanvasSnapshot) -> bool:
        """
        从快照加载

        Args:
            snapshot: 快照对象

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            try:
                self._elements.clear()
                for element in snapshot.elements:
                    self._elements[element.id] = element

                self._rebuild_z_index_map()
                self._undo_stack = snapshot.operation_history.copy()
                self._redo_stack.clear()
                self._current_selection = snapshot.selection

                await self._notify_change()
                return True
            except Exception:
                return False

    async def undo(self) -> Optional[CanvasOperation]:
        """
        撤销操作

        Returns:
            CanvasOperation 或 None
        """
        if not self.can_undo:
            return None

        async with self._lock:
            op = self._undo_stack.pop()

            # 创建反向操作
            reverse_op = CanvasOperation(
                id=self._generate_id(),
                type=self._get_reverse_operation_type(op.type),
                target_ids=op.target_ids,
                before_state=op.after_state,
                after_state=op.before_state,
                creator=op.creator,
            )

            # 执行反向操作
            await self.execute_operation(reverse_op)

            # 将原操作移到重做栈
            self._redo_stack.append(op)

            return op

    async def redo(self) -> Optional[CanvasOperation]:
        """
        重做操作

        Returns:
            CanvasOperation 或 None
        """
        if not self.can_redo:
            return None

        async with self._lock:
            op = self._redo_stack.pop()

            # 创建重做操作
            redo_op = CanvasOperation(
                id=self._generate_id(),
                type=op.type,
                target_ids=op.target_ids,
                before_state=op.before_state,
                after_state=op.after_state,
                creator=op.creator,
            )

            # 执行重做操作
            await self.execute_operation(redo_op)

            # 将操作移回撤销栈
            self._undo_stack.append(op)

            return op

    def _get_reverse_operation_type(self, op_type: str) -> str:
        """获取反向操作类型"""
        reverse_map = {
            OperationType.CREATE.value: OperationType.DELETE.value,
            OperationType.DELETE.value: OperationType.CREATE.value,
            OperationType.UPDATE.value: OperationType.UPDATE.value,
            OperationType.MOVE.value: OperationType.MOVE.value,
            OperationType.RESIZE.value: OperationType.RESIZE.value,
            OperationType.ROTATE.value: OperationType.ROTATE.value,
            OperationType.STYLE.value: OperationType.STYLE.value,
            OperationType.GROUP.value: OperationType.UNGROUP.value,
            OperationType.UNGROUP.value: OperationType.GROUP.value,
            OperationType.DUPLICATE.value: OperationType.DELETE.value,
            OperationType.ALIGN.value: OperationType.UPDATE.value,
            OperationType.TEXT_EDIT.value: OperationType.TEXT_EDIT.value,
        }
        return reverse_map.get(op_type, op_type)

    def clear_selection(self) -> None:
        """清除选择"""
        self._current_selection = None

    def set_selection(self, element_ids: List[str]) -> None:
        """
        设置选择

        Args:
            element_ids: 元素ID列表
        """
        if not element_ids:
            self.clear_selection()
            return

        # 同步执行元素选择
        selected_elements = []
        for element_id in element_ids:
            if element_id in self._elements:
                selected_elements.append(self._elements[element_id])

        if selected_elements:
            min_x = min(e.position["x"] for e in selected_elements)
            min_y = min(e.position["y"] for e in selected_elements)
            max_x = max(e.position["x"] + e.size["width"] for e in selected_elements)
            max_y = max(e.position["y"] + e.size["height"] for e in selected_elements)

            self._current_selection = SelectionRegion(
                id=self._generate_id(),
                type="element",
                bounds={
                    "x": min_x,
                    "y": min_y,
                    "width": max_x - min_x,
                    "height": max_y - min_y,
                },
                element_ids=element_ids,
            )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "canvas_id": self.canvas_id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "background_color": self.background_color,
            "elements": [e.to_dict() for e in self._elements.values()],
            "selection": self._current_selection.to_dict() if self._current_selection else None,
            "undo_stack_size": len(self._undo_stack),
            "redo_stack_size": len(self._redo_stack),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], canvas_id: str = None) -> "CanvasCore":
        """从字典创建"""
        canvas_id = canvas_id or data.get("canvas_id", "")
        core = cls(
            canvas_id=canvas_id,
            name=data.get("name", "Untitled"),
            width=data.get("width", 1920),
            height=data.get("height", 1080),
            background_color=data.get("background_color", "#ffffff"),
        )

        elements = data.get("elements", [])
        for element_data in elements:
            element = CanvasElement.from_dict(element_data)
            if element:
                core._elements[element.id] = element

        core._rebuild_z_index_map()

        selection = data.get("selection")
        if selection:
            core._current_selection = SelectionRegion.from_dict(selection)

        return core
