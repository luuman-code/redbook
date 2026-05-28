"""
Canvas Exporter - 画板导出器

支持将画板导出为图片、视频、PDF等格式
"""

import io
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from .canvas_core import Canvas, CanvasElement


class ExportFormat(str, Enum):
    """导出格式枚举"""
    # Image formats
    PNG = "png"
    JPG = "jpg"
    WEBP = "webp"
    # Video formats
    MP4 = "mp4"
    WEBM = "webm"
    # Document formats
    PDF = "pdf"


class ImageExportOptions(BaseModel):
    """图片导出选项"""
    format: str = Field(default="png", description="导出格式: png, jpg, webp")
    quality: int = Field(default=95, ge=1, le=100, description="图片质量 (1-100)")
    width: Optional[int] = Field(default=None, ge=1, description="输出宽度")
    height: Optional[int] = Field(default=None, ge=1, description="输出高度")
    background_color: Optional[str] = Field(default=None, description="背景颜色 (hex)")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = ["png", "jpg", "webp"]
        if v.lower() not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return v.lower()


class VideoExportOptions(BaseModel):
    """视频导出选项"""
    format: str = Field(default="mp4", description="导出格式: mp4, webm")
    fps: int = Field(default=30, ge=1, le=120, description="帧率")
    width: int = Field(default=1920, ge=1, description="输出宽度")
    height: int = Field(default=1080, ge=1, description="输出高度")
    bitrate: int = Field(default=5000, ge=100, description="比特率 (kbps)")
    duration: Optional[float] = Field(default=None, ge=0, description="视频时长 (秒)")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = ["mp4", "webm"]
        if v.lower() not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return v.lower()


class PDFExportOptions(BaseModel):
    """PDF导出选项"""
    page_width: float = Field(default=210.0, ge=1, description="页面宽度 (mm)")
    page_height: float = Field(default=297.0, ge=1, description="页面高度 (mm)")
    margin: float = Field(default=10.0, ge=0, description="页边距 (mm)")
    background_color: Optional[str] = Field(default="#FFFFFF", description="背景颜色")


class ExportResult(BaseModel):
    """导出结果"""
    success: bool = Field(..., description="是否成功")
    data: Optional[bytes] = Field(default=None, description="导出数据")
    format: str = Field(..., description="导出格式")
    size: int = Field(default=0, description="文件大小 (bytes)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    error: Optional[str] = Field(default=None, description="错误信息")


class CanvasExporter:
    """
    画板导出器

    支持将画板内容导出为多种格式：
    - 图片: PNG, JPG, WEBP
    - 视频: MP4, WEBM (动画效果)
    - PDF: 文档格式
    """

    EXPORT_FORMATS: Dict[str, List[str]] = {
        "image": ["png", "jpg", "webp"],
        "video": ["mp4", "webm"],
        "pdf": ["pdf"],
    }

    def __init__(self) -> None:
        """初始化导出器"""
        self._supported_image_formats = set(self.EXPORT_FORMATS["image"])
        self._supported_video_formats = set(self.EXPORT_FORMATS["video"])
        self._supported_pdf_formats = set(self.EXPORT_FORMATS["pdf"])

    def is_format_supported(self, format: str) -> bool:
        """
        检查格式是否支持

        Args:
            format: 格式名称

        Returns:
            是否支持
        """
        format_lower = format.lower()
        return (
            format_lower in self._supported_image_formats
            or format_lower in self._supported_video_formats
            or format_lower in self._supported_pdf_formats
        )

    def get_format_type(self, format: str) -> Optional[str]:
        """
        获取格式类型

        Args:
            format: 格式名称

        Returns:
            格式类型: image, video, pdf 或 None
        """
        format_lower = format.lower()
        if format_lower in self._supported_image_formats:
            return "image"
        if format_lower in self._supported_video_formats:
            return "video"
        if format_lower in self._supported_pdf_formats:
            return "pdf"
        return None

    async def export_as_image(
        self,
        canvas: "Canvas",
        format: str = "png",
        options: Optional[ImageExportOptions] = None,
    ) -> ExportResult:
        """
        导出为图片

        Args:
            canvas: 画布对象
            format: 导出格式 (png, jpg, webp)
            options: 导出选项

        Returns:
            ExportResult: 包含导出数据的結果
        """
        try:
            # Validate format
            format_lower = format.lower()
            if format_lower not in self._supported_image_formats:
                return ExportResult(
                    success=False,
                    format=format,
                    error=f"Unsupported image format: {format}. Supported: {self._supported_image_formats}",
                )

            # Use default options if not provided
            if options is None:
                options = ImageExportOptions(format=format_lower)
            else:
                options.format = format_lower

            # Get canvas elements and render to image
            # Note: Actual rendering would use canvas.to_image() method
            image_data = await self._render_canvas_to_image(canvas, options)

            return ExportResult(
                success=True,
                data=image_data,
                format=format_lower,
                size=len(image_data),
                metadata={
                    "width": options.width,
                    "height": options.height,
                    "quality": options.quality,
                },
            )

        except Exception as e:
            return ExportResult(
                success=False,
                format=format,
                error=f"Image export failed: {str(e)}",
            )

    async def export_as_video(
        self,
        canvas: "Canvas",
        fps: int = 30,
        options: Optional[VideoExportOptions] = None,
    ) -> ExportResult:
        """
        导出为视频（动画效果）

        Args:
            canvas: 画布对象
            fps: 帧率 (默认 30)
            options: 导出选项

        Returns:
            ExportResult: 包含导出数据的結果
        """
        try:
            # Determine format
            if options is None:
                options = VideoExportOptions(fps=fps)
            else:
                options.fps = fps

            format_lower = options.format.lower()
            if format_lower not in self._supported_video_formats:
                return ExportResult(
                    success=False,
                    format=options.format,
                    error=f"Unsupported video format: {options.format}. Supported: {self._supported_video_formats}",
                )

            # Render canvas animation to video
            # Note: Actual rendering would use canvas.to_video() method
            video_data = await self._render_canvas_to_video(canvas, options)

            return ExportResult(
                success=True,
                data=video_data,
                format=format_lower,
                size=len(video_data),
                metadata={
                    "fps": options.fps,
                    "width": options.width,
                    "height": options.height,
                    "bitrate": options.bitrate,
                },
            )

        except Exception as e:
            return ExportResult(
                success=False,
                format=options.format if options else "mp4",
                error=f"Video export failed: {str(e)}",
            )

    async def export_as_pdf(
        self,
        canvas: "Canvas",
        options: Optional[PDFExportOptions] = None,
    ) -> ExportResult:
        """
        导出为PDF

        Args:
            canvas: 画布对象
            options: 导出选项

        Returns:
            ExportResult: 包含导出数据的結果
        """
        try:
            # Use default options if not provided
            if options is None:
                options = PDFExportOptions()

            # Render canvas to PDF
            # Note: Actual rendering would use canvas.to_pdf() method
            pdf_data = await self._render_canvas_to_pdf(canvas, options)

            return ExportResult(
                success=True,
                data=pdf_data,
                format="pdf",
                size=len(pdf_data),
                metadata={
                    "page_width": options.page_width,
                    "page_height": options.page_height,
                    "margin": options.margin,
                },
            )

        except Exception as e:
            return ExportResult(
                success=False,
                format="pdf",
                error=f"PDF export failed: {str(e)}",
            )

    async def export(
        self,
        canvas: "Canvas",
        format: str,
        options: Optional[Union[ImageExportOptions, VideoExportOptions, PDFExportOptions]] = None,
    ) -> ExportResult:
        """
        通用导出接口

        Args:
            canvas: 画布对象
            format: 导出格式
            options: 导出选项

        Returns:
            ExportResult: 包含导出数据的結果
        """
        format_type = self.get_format_type(format)

        if format_type == "image":
            return await self.export_as_image(
                canvas,
                format=format,
                options=options if isinstance(options, ImageExportOptions) else None,
            )
        elif format_type == "video":
            if isinstance(options, VideoExportOptions):
                return await self.export_as_video(canvas, options=options)
            return await self.export_as_video(canvas)
        elif format_type == "pdf":
            return await self.export_as_pdf(
                canvas,
                options=options if isinstance(options, PDFExportOptions) else None,
            )
        else:
            return ExportResult(
                success=False,
                format=format,
                error=f"Unsupported format: {format}",
            )

    # Internal rendering methods - these would integrate with actual canvas rendering

    async def _render_canvas_to_image(
        self,
        canvas: "Canvas",
        options: ImageExportOptions,
    ) -> bytes:
        """
        将画布渲染为图片

        Args:
            canvas: 画布对象
            options: 图片导出选项

        Returns:
            图片数据 (bytes)
        """
        # 获取画布元素
        elements = canvas.elements if hasattr(canvas, "elements") else []

        # 计算画布尺寸
        width = options.width or self._calculate_canvas_width(elements)
        height = options.height or self._calculate_canvas_height(elements)

        # 创建画布缓冲区
        buffer = io.BytesIO()

        # TODO: 集成实际渲染库 (如 Pillow, cairosvg 等)
        # 这里为占位实现，返回空数据
        # 实际实现需要:
        # 1. 创建 Image 对象
        # 2. 渲染每个元素
        # 3. 应用样式和变换
        # 4. 保存为指定格式

        # Placeholder: 创建空白图片
        from PIL import Image as PILImage

        img = PILImage.new("RGB", (width or 800, height or 600), options.background_color or "white")

        # 保存到缓冲区
        img.save(buffer, format=options.format.upper(), quality=options.quality)
        buffer.seek(0)

        return buffer.getvalue()

    async def _render_canvas_to_video(
        self,
        canvas: "Canvas",
        options: VideoExportOptions,
    ) -> bytes:
        """
        将画布动画渲染为视频

        Args:
            canvas: 画布对象
            options: 视频导出选项

        Returns:
            视频数据 (bytes)
        """
        # 获取动画帧
        frames = await self._extract_animation_frames(canvas)

        if not frames:
            # 如果没有动画，返回静态图片
            static_options = ImageExportOptions(
                format="png",
                width=options.width,
                height=options.height,
            )
            return await self._render_canvas_to_image(canvas, static_options)

        # TODO: 集成视频编码库 (如 opencv, moviepy 等)
        # 实际实现需要:
        # 1. 逐帧渲染画布状态
        # 2. 编码为视频流
        # 3. 添加音频轨道 (如果有)
        # 4. 输出为指定格式

        # Placeholder: 返回空数据
        return b""

    async def _render_canvas_to_pdf(
        self,
        canvas: "Canvas",
        options: PDFExportOptions,
    ) -> bytes:
        """
        将画布渲染为PDF

        Args:
            canvas: 画布对象
            options: PDF导出选项

        Returns:
            PDF数据 (bytes)
        """
        # 获取画布元素
        elements = canvas.elements if hasattr(canvas, "elements") else []

        # TODO: 集成PDF库 (如 reportlab, fpdf 等)
        # 实际实现需要:
        # 1. 创建PDF文档
        # 2. 设置页面大小
        # 3. 渲染每个元素到PDF页面
        # 4. 处理分页

        # Placeholder: 使用 reportlab 生成简单PDF
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas

        buffer = io.BytesIO()
        page_width = options.page_width * 2.83465  # mm to points
        page_height = options.page_height * 2.83465

        pdf = pdf_canvas.Canvas(buffer, pagesize=(page_width, page_height))

        # 设置背景色
        if options.background_color:
            pdf.setFillColor(options.background_color)
            pdf.rect(0, 0, page_width, page_height, fill=True)

        # 渲染元素 (简化实现)
        self._render_elements_to_pdf(pdf, elements, options)

        pdf.save()
        buffer.seek(0)

        return buffer.getvalue()

    def _render_elements_to_pdf(
        self,
        pdf: Any,
        elements: List["CanvasElement"],
        options: PDFExportOptions,
    ) -> None:
        """
        将元素渲染到PDF

        Args:
            pdf: reportlab canvas 对象
            elements: 画布元素列表
            options: PDF导出选项
        """
        margin = options.margin * 2.83465  # mm to points
        page_width = options.page_width * 2.83465
        page_height = options.page_height * 2.83465
        content_width = page_width - 2 * margin
        content_height = page_height - 2 * margin

        y_position = page_height - margin

        for element in elements:
            # 获取元素属性
            elem_type = getattr(element, "type", "unknown")
            content = getattr(element, "content", "")
            style = getattr(element, "style", {})

            # 计算字体大小
            font_size = style.get("fontSize", 12)

            # 渲染文本元素
            if elem_type == "text" and content:
                pdf.setFont("Helvetica", font_size)
                pdf.setFillColor(style.get("color", "black"))

                # 处理多行文本
                lines = content.split("\n")
                for line in lines:
                    if y_position < margin + font_size:
                        break  # 超出页面，跳过
                    pdf.drawString(margin, y_position, line[:50])  # 限制每行50字符
                    y_position -= font_size * 1.5

    async def _extract_animation_frames(self, canvas: "Canvas") -> List[Any]:
        """
        提取动画帧

        Args:
            canvas: 画布对象

        Returns:
            动画帧列表
        """
        # 检查是否有动画数据
        if not hasattr(canvas, "animations") or not canvas.animations:
            return []

        # TODO: 实际实现动画帧提取
        # 这需要:
        # 1. 解析动画时间线
        # 2. 在每个时间点渲染画布状态
        # 3. 返回帧数据列表

        return []

    def _calculate_canvas_width(self, elements: List["CanvasElement"]) -> int:
        """计算画布宽度"""
        if not elements:
            return 800  # 默认宽度

        max_x = 0
        for element in elements:
            x = getattr(element, "x", 0)
            width = getattr(element, "width", 0)
            max_x = max(max_x, x + width)

        return max(800, int(max_x * 1.1))  # 留 10% 边距

    def _calculate_canvas_height(self, elements: List["CanvasElement"]) -> int:
        """计算画布高度"""
        if not elements:
            return 600  # 默认高度

        max_y = 0
        for element in elements:
            y = getattr(element, "y", 0)
            height = getattr(element, "height", 0)
            max_y = max(max_y, y + height)

        return max(600, int(max_y * 1.1))  # 留 10% 边距


# Convenience function for quick exports
async def export_canvas(
    canvas: "Canvas",
    format: str,
    **kwargs: Any,
) -> ExportResult:
    """
    便捷导出函数

    Args:
        canvas: 画布对象
        format: 导出格式
        **kwargs: 额外参数传递给导出器

    Returns:
        ExportResult: 导出结果
    """
    exporter = CanvasExporter()
    return await exporter.export(canvas, format, **kwargs)
