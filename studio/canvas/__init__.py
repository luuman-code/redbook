"""
Canvas 画板模块

提供画板核心功能：状态管理、操作引擎、持久化存储、框选提取、拖拽文件处理
"""

from .canvas_core import (
    CanvasCore,
    CanvasElement,
    CanvasOperation,
    CanvasSnapshot,
    ElementMetadata,
    ElementStyles,
    ElementType,
    LassoSelection,
    OperationResult,
    OperationType,
    SelectionRegion,
    ExtractedContent,
)
from .canvas_storage import CanvasStorage, CanvasSummary
from .selection_extractor import SelectionExtractor
from .drag_file_handler import DragFileHandler

__all__ = [
    # Core
    "CanvasCore",
    "CanvasElement",
    "CanvasOperation",
    "CanvasSnapshot",
    "ElementMetadata",
    "ElementStyles",
    "ElementType",
    "LassoSelection",
    "OperationResult",
    "OperationType",
    "SelectionRegion",
    "ExtractedContent",
    # Storage
    "CanvasStorage",
    "CanvasSummary",
    # Extractors
    "SelectionExtractor",
    # Handlers
    "DragFileHandler",
]
