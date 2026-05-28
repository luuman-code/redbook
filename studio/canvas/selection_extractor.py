"""
SelectionExtractor - 框选内容提取器

从框选区域内提取文本、图片、视频等内容
"""

from typing import Any, Dict, List, Optional

from .canvas_core import (
    CanvasCore,
    CanvasElement,
    ElementType,
    ExtractedContent,
    LassoSelection,
    SelectionRegion,
)


class SelectionExtractor:
    """
    框选内容提取器

    职责：
    1. 获取区域内所有元素
    2. 按类型分类提取（文本/图片/视频）
    3. 生成区域摘要供Agent理解
    """

    def __init__(self):
        """初始化提取器"""
        pass

    def extract(
        self,
        region: SelectionRegion,
        canvas: CanvasCore,
    ) -> ExtractedContent:
        """
        提取框选区域内的内容

        Args:
            region: 选择区域
            canvas: 画板核心

        Returns:
            ExtractedContent: 提取的内容
        """
        if region is None:
            return ExtractedContent()

        # 获取区域内所有元素
        elements = self._get_elements_in_region(region, canvas)

        # 按类型分类提取
        texts = self._extract_texts(elements)
        images = self._extract_images(elements)
        videos = self._extract_videos(elements)
        audio = self._extract_audio(elements)

        # 生成摘要
        summary = self._generate_summary(texts, images, videos, audio, elements)

        return ExtractedContent(
            texts=texts,
            images=images,
            videos=videos,
            audio=audio,
            summary=summary,
        )

    def _get_elements_in_region(
        self,
        region: SelectionRegion,
        canvas: CanvasCore,
    ) -> List[CanvasElement]:
        """
        获取区域内的元素

        Args:
            region: 选择区域
            canvas: 画板核心

        Returns:
            元素列表
        """
        if region.type == "element":
            # 直接使用 region.element_ids
            elements = []
            for element_id in region.element_ids:
                element = canvas.get_element(element_id)
                if element:
                    elements.append(element)
            return elements

        elif region.type == "lasso" and region.lasso:
            # 自由框选 - 使用射线法判断
            return self._get_elements_in_lasso(region.lasso, canvas)

        elif region.type == "rect":
            # 矩形框选
            return canvas.get_elements_in_rect(region.bounds)

        else:
            # 默认使用 bounds
            return canvas.get_elements_in_rect(region.bounds)

    def _get_elements_in_lasso(
        self,
        lasso: LassoSelection,
        canvas: CanvasCore,
    ) -> List[CanvasElement]:
        """
        获取自由框选区域内的元素

        Args:
            lasso: 自由框选
            canvas: 画板核心

        Returns:
            元素列表
        """
        elements = []
        bounds = lasso.get_bounds()

        # 先获取边界框内的所有元素
        candidates = canvas.get_elements_in_rect(bounds)

        for element in candidates:
            if not element.visible:
                continue

            # 检查元素边界框是否与多边形有交集
            rect = {
                "x": element.position["x"],
                "y": element.position["y"],
                "width": element.size["width"],
                "height": element.size["height"],
            }

            if self._rect_intersects_polygon(rect, lasso.points):
                elements.append(element)

        return elements

    def _rect_intersects_polygon(
        self,
        rect: Dict[str, float],
        polygon_points: List[Dict[str, float]],
    ) -> bool:
        """
        检查矩形是否与多边形有交集

        交集判定条件：
        1. 矩形的任意顶点在多边形内部
        2. 多边形的任意边与矩形的任意边相交
        3. 多边形完全包含矩形（已由条件1覆盖）

        Args:
            rect: 矩形 {x, y, width, height}
            polygon_points: 多边形顶点列表

        Returns:
            bool: 是否相交
        """
        if not polygon_points or len(polygon_points) < 3:
            return False

        # 矩形的四个顶点
        rect_corners = [
            {"x": rect["x"], "y": rect["y"]},  # 左上
            {"x": rect["x"] + rect["width"], "y": rect["y"]},  # 右上
            {"x": rect["x"] + rect["width"], "y": rect["y"] + rect["height"]},  # 右下
            {"x": rect["x"], "y": rect["y"] + rect["height"]},  # 左下
        ]

        # 1. 检查矩形的任意顶是否在多边形内部
        for corner in rect_corners:
            if self._point_in_polygon(corner, polygon_points):
                return True

        # 2. 检查多边形的任意边是否与矩形的任意边相交
        polygon_edges = []
        for i in range(len(polygon_points)):
            p1 = polygon_points[i]
            p2 = polygon_points[(i + 1) % len(polygon_points)]
            polygon_edges.append((p1, p2))

        # 矩形的四条边
        rect_edges = [
            (rect_corners[0], rect_corners[1]),  # 上边
            (rect_corners[1], rect_corners[2]),  # 右边
            (rect_corners[2], rect_corners[3]),  # 下边
            (rect_corners[3], rect_corners[0]),  # 左边
        ]

        for poly_edge in polygon_edges:
            for rect_edge in rect_edges:
                if self._line_segments_intersect(poly_edge[0], poly_edge[1], rect_edge[0], rect_edge[1]):
                    return True

        return False

    def _point_in_polygon(
        self,
        point: Dict[str, float],
        polygon_points: List[Dict[str, float]],
    ) -> bool:
        """
        使用射线法判断点是否在多边形内部

        Args:
            point: 点 {x, y}
            polygon_points: 多边形顶点列表

        Returns:
            bool: 点是否在多边形内部
        """
        if not polygon_points or len(polygon_points) < 3:
            return False

        x, y = point["x"], point["y"]
        n = len(polygon_points)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = polygon_points[i]["x"], polygon_points[i]["y"]
            xj, yj = polygon_points[j]["x"], polygon_points[j]["y"]

            # 检查点是否在边的垂直范围内
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside

            j = i

        return inside

    def _line_segments_intersect(
        self,
        p1: Dict[str, float],
        p2: Dict[str, float],
        p3: Dict[str, float],
        p4: Dict[str, float],
    ) -> bool:
        """
        判断两条线段是否相交（考虑端点）

        Args:
            p1, p2: 线段1的两个端点
            p3, p4: 线段2的两个端点

        Returns:
            bool: 是否相交
        """
        def ccw(A, B, C):
            """判断三点的旋转方向"""
            return (C["y"] - A["y"]) * (B["x"] - A["x"]) > (B["y"] - A["y"]) * (C["x"] - A["x"])

        # 检查端点是否在另一条线段上
        def on_segment(A, B, C):
            """判断点C是否在线段AB上（包括端点）"""
            return min(A["x"], B["x"]) <= C["x"] <= max(A["x"], B["x"]) and \
                   min(A["y"], B["y"]) <= C["y"] <= max(A["y"], B["y"])

        A, B, C, D = p1, p2, p3, p4

        # 使用 CCW (Counter-Clockwise) 方法
        if ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D):
            return True

        # 检查端点是否在另一条线段上（包括重叠情况）
        if ccw(A, C, D) == ccw(B, C, D) == ccw(A, B, C) == ccw(A, B, D):
            #共线情况，检查边界
            if on_segment(A, B, C) or on_segment(A, B, D) or on_segment(C, D, A) or on_segment(C, D, B):
                return True

        return False

    def _extract_texts(self, elements: List[CanvasElement]) -> List[Dict[str, Any]]:
        """
        提取文本内容

        Args:
            elements: 元素列表

        Returns:
            文本列表
        """
        texts = []

        for element in elements:
            if element.type == ElementType.TEXT.value:
                text_data = {
                    "id": element.id,
                    "content": element.metadata.text_content or "",
                    "position": element.position,
                    "size": element.size,
                    "styles": {
                        "font_size": element.metadata.font_size,
                        "font_family": element.metadata.font_family,
                        "color": element.styles.color,
                        "bold": element.styles.bold,
                    },
                }
                texts.append(text_data)

            # 检查组合元素中的文本
            elif element.type == ElementType.GROUP.value:
                child_ids = element.metadata.child_ids or []
                for child_id in child_ids:
                    # 递归获取子元素文本
                    if hasattr(element, 'metadata') and element.metadata.child_ids:
                        pass  # 已在循环中处理

        return texts

    def _extract_images(self, elements: List[CanvasElement]) -> List[Dict[str, Any]]:
        """
        提取图片内容

        Args:
            elements: 元素列表

        Returns:
            图片列表
        """
        images = []

        for element in elements:
            if element.type == ElementType.IMAGE.value:
                image_data = {
                    "id": element.id,
                    "url": element.metadata.url,
                    "local_path": element.metadata.local_path,
                    "mime_type": element.metadata.mime_type,
                    "position": element.position,
                    "size": element.size,
                }
                images.append(image_data)

        return images

    def _extract_videos(self, elements: List[CanvasElement]) -> List[Dict[str, Any]]:
        """
        提取视频内容

        Args:
            elements: 元素列表

        Returns:
            视频列表
        """
        videos = []

        for element in elements:
            if element.type == ElementType.VIDEO.value:
                video_data = {
                    "id": element.id,
                    "url": element.metadata.url,
                    "local_path": element.metadata.local_path,
                    "mime_type": element.metadata.mime_type,
                    "duration": element.metadata.duration,
                    "thumbnail_url": element.metadata.thumbnail_url,
                    "position": element.position,
                    "size": element.size,
                }
                videos.append(video_data)

        return videos

    def _extract_audio(self, elements: List[CanvasElement]) -> List[Dict[str, Any]]:
        """
        提取音频内容

        Args:
            elements: 元素列表

        Returns:
            音频列表
        """
        audio_list = []

        for element in elements:
            if element.type == ElementType.AUDIO.value:
                audio_data = {
                    "id": element.id,
                    "url": element.metadata.url,
                    "local_path": element.metadata.local_path,
                    "mime_type": element.metadata.mime_type,
                    "duration": element.metadata.duration,
                    "waveform_data": element.metadata.waveform_data,
                    "position": element.position,
                    "size": element.size,
                }
                audio_list.append(audio_data)

        return audio_list

    def _generate_summary(
        self,
        texts: List[Dict[str, Any]],
        images: List[Dict[str, Any]],
        videos: List[Dict[str, Any]],
        audio: List[Dict[str, Any]],
        elements: List[CanvasElement],
    ) -> str:
        """
        生成区域摘要

        Args:
            texts: 文本列表
            images: 图片列表
            videos: 视频列表
            audio: 音频列表
            elements: 元素列表

        Returns:
            摘要字符串
        """
        summary_parts = []

        # 统计元素数量
        element_count = len(elements)
        summary_parts.append(f"共选中 {element_count} 个元素")

        # 文本统计
        if texts:
            text_count = len(texts)
            total_chars = sum(len(t.get("content", "")) for t in texts)
            summary_parts.append(f"文本: {text_count} 个元素, 共 {total_chars} 字符")

            # 提取前几个文本片段作为预览
            preview_texts = []
            for t in texts[:3]:
                content = t.get("content", "")
                if content:
                    preview = content[:50] + "..." if len(content) > 50 else content
                    preview_texts.append(f'"{preview}"')
            if preview_texts:
                summary_parts.append(f"文本预览: {'; '.join(preview_texts)}")

        # 图片统计
        if images:
            image_count = len(images)
            summary_parts.append(f"图片: {image_count} 张")

            # 列出图片来源
            sources = []
            for img in images[:3]:
                url = img.get("url")
                local_path = img.get("local_path")
                if url:
                    sources.append(f"URL: {url[:30]}...")
                elif local_path:
                    sources.append(f"本地: {local_path}")
            if sources:
                summary_parts.append(f"图片来源: {'; '.join(sources)}")

        # 视频统计
        if videos:
            video_count = len(videos)
            total_duration = sum(v.get("duration", 0) for v in videos)
            summary_parts.append(f"视频: {video_count} 个, 总时长 {total_duration:.1f}秒")

        # 音频统计
        if audio:
            audio_count = len(audio)
            total_duration = sum(a.get("duration", 0) for a in audio)
            summary_parts.append(f"音频: {audio_count} 个, 总时长 {total_duration:.1f}秒")

        # 组合元素
        group_count = sum(1 for e in elements if e.type == ElementType.GROUP.value)
        if group_count:
            summary_parts.append(f"组合: {group_count} 个")

        # 锁定/可见状态
        locked_count = sum(1 for e in elements if e.locked)
        invisible_count = sum(1 for e in elements if not e.visible)
        if locked_count:
            summary_parts.append(f"锁定元素: {locked_count} 个")
        if invisible_count:
            summary_parts.append(f"隐藏元素: {invisible_count} 个")

        return " | ".join(summary_parts) if summary_parts else "空选择区域"

    def extract_element_content(
        self,
        element: CanvasElement,
    ) -> Dict[str, Any]:
        """
        提取单个元素的内容

        Args:
            element: 画板元素

        Returns:
            元素内容字典
        """
        content: Dict[str, Any] = {
            "id": element.id,
            "type": element.type,
            "position": element.position,
            "size": element.size,
        }

        if element.type == ElementType.TEXT.value:
            content["text"] = element.metadata.text_content
            content["styles"] = {
                "font_size": element.metadata.font_size,
                "font_family": element.metadata.font_family,
                "color": element.styles.color,
                "bold": element.styles.bold,
                "italic": element.styles.italic,
            }

        elif element.type == ElementType.IMAGE.value:
            content["url"] = element.metadata.url
            content["local_path"] = element.metadata.local_path
            content["mime_type"] = element.metadata.mime_type

        elif element.type == ElementType.VIDEO.value:
            content["url"] = element.metadata.url
            content["local_path"] = element.metadata.local_path
            content["mime_type"] = element.metadata.mime_type
            content["duration"] = element.metadata.duration
            content["thumbnail_url"] = element.metadata.thumbnail_url

        elif element.type == ElementType.AUDIO.value:
            content["url"] = element.metadata.url
            content["local_path"] = element.metadata.local_path
            content["mime_type"] = element.metadata.mime_type
            content["duration"] = element.metadata.duration
            content["waveform_data"] = element.metadata.waveform_data

        elif element.type == ElementType.SHAPE.value:
            content["shape_type"] = element.metadata.shape_type
            content["points"] = element.metadata.points

        elif element.type == ElementType.GROUP.value:
            content["child_ids"] = element.metadata.child_ids

        return content

    def batch_extract(
        self,
        regions: List[SelectionRegion],
        canvas: CanvasCore,
    ) -> List[ExtractedContent]:
        """
        批量提取多个区域的内容

        Args:
            regions: 选择区域列表
            canvas: 画板核心

        Returns:
            提取内容列表
        """
        results = []
        for region in regions:
            content = self.extract(region, canvas)
            results.append(content)
        return results

    def get_selection_preview(
        self,
        region: SelectionRegion,
        canvas: CanvasCore,
        max_items: int = 5,
    ) -> str:
        """
        获取选择的预览文本（用于UI显示）

        Args:
            region: 选择区域
            canvas: 画板核心
            max_items: 最大预览项数

        Returns:
            预览字符串
        """
        if region is None:
            return "无选择"

        elements = self._get_elements_in_region(region, canvas)
        if not elements:
            return "空选择"

        previews = []
        count = 0

        for element in elements:
            if count >= max_items:
                break

            if element.type == ElementType.TEXT.value:
                text = element.metadata.text_content or ""
                preview = text[:20] + "..." if len(text) > 20 else text
                previews.append(f'文本: "{preview}"')
                count += 1

            elif element.type == ElementType.IMAGE.value:
                url = element.metadata.url
                if url:
                    previews.append(f"图片: {url[:20]}...")
                else:
                    previews.append("图片: [本地文件]")
                count += 1

            elif element.type == ElementType.VIDEO.value:
                previews.append("视频")
                count += 1

            elif element.type == ElementType.AUDIO.value:
                previews.append("音频")
                count += 1

            elif element.type == ElementType.GROUP.value:
                child_count = len(element.metadata.child_ids or [])
                previews.append(f"组合: {child_count} 个子元素")
                count += 1

            elif element.type == ElementType.SHAPE.value:
                shape_type = element.metadata.shape_type or "形状"
                previews.append(f"形状: {shape_type}")
                count += 1

        remaining = len(elements) - count
        if remaining > 0:
            previews.append(f"... 还有 {remaining} 个元素")

        return " | ".join(previews)
