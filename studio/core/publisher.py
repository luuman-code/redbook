"""
Publisher - 发布器

参考 plan.md:
- 发布/导出：用户点击发布，可选
  - 模拟发布流程（检查格式、尺寸）
  - 直接通过小红书开放 API（若未来有）发布
  - 导出素材包供手动上传
"""

import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config.studio_config import StudioConfig
from ..models.content_item import ContentItem, ContentType
from ..models.session import Session


@dataclass
class PublishResult:
    """发布结果"""
    success: bool
    method: str  # "api" / "export" / "simulate"
    published_url: Optional[str] = None
    exported_path: Optional[str] = None
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class Publisher:
    """
    发布器

    职责：
    1. 格式校验（检查是否符合小红书规范）
    2. 生成导出包（ZIP）
    3. 调用发布 API（预留）
    4. 模拟发布流程
    """

    # 小红书规范限制
    MAX_TITLE_LENGTH = 20
    MAX_CONTENT_LENGTH = 1000
    MAX_IMAGES = 9
    MAX_IMAGE_SIZE_MB = 5
    MAX_VIDEO_SIZE_MB = 500
    MAX_VIDEO_DURATION = 15  # 秒

    def __init__(self, config: StudioConfig = None):
        """
        初始化 Publisher

        Args:
            config: Studio 配置
        """
        self.config = config or StudioConfig()

    def validate(self, session: Session) -> PublishResult:
        """
        校验发布内容

        Args:
            session: 会话对象

        Returns:
            PublishResult: 校验结果
        """
        errors = []
        warnings = []

        # 1. 检查标题
        title_items = session.get_items_by_type(ContentType.TITLE)
        if title_items:
            title = title_items[0].content
            if len(title) > self.MAX_TITLE_LENGTH:
                errors.append(f"标题过长 ({len(title)}/{self.MAX_TITLE_LENGTH})")
        else:
            errors.append("缺少标题")

        # 2. 检查正文
        text_items = session.get_items_by_type(ContentType.TEXT)
        total_text = sum(len(item.content) for item in text_items)
        if total_text > self.MAX_CONTENT_LENGTH:
            warnings.append(f"正文较长 ({total_text}字符)，建议精简")

        # 3. 检查图片
        image_items = session.get_items_by_type(ContentType.IMAGE)
        if not image_items:
            warnings.append("没有配图，建议添加图片以提升吸引力")
        elif len(image_items) > self.MAX_IMAGES:
            errors.append(f"图片数量超标 ({len(image_items)}/{self.MAX_IMAGES})")

        # 4. 检查图片尺寸
        for img in image_items:
            size_mb = img.metadata.get("size_mb", 0)
            if size_mb > self.MAX_IMAGE_SIZE_MB:
                warnings.append(
                    f"图片 {img.item_id} 大小为 {size_mb}MB，超过 {self.MAX_IMAGE_SIZE_MB}MB 限制"
                )

        # 5. 检查视频
        video_items = session.get_items_by_type(ContentType.VIDEO)
        if video_items:
            video = video_items[0]
            duration = video.metadata.get("duration", 0)
            if duration > self.MAX_VIDEO_DURATION:
                warnings.append(
                    f"视频时长 {duration}s 超过建议时长 {self.MAX_VIDEO_DURATION}s"
                )

            size_mb = video.metadata.get("size_mb", 0)
            if size_mb > self.MAX_VIDEO_SIZE_MB:
                errors.append(
                    f"视频大小 {size_mb}MB 超过 {self.MAX_VIDEO_SIZE_MB}MB 限制"
                )

        # 6. 检查标签
        hashtag_items = session.get_items_by_type(ContentType.HASHTAG)
        if len(hashtag_items) < 3:
            warnings.append("话题标签少于 3 个，建议添加更多以增加曝光")

        success = len(errors) == 0
        method = "simulate"

        return PublishResult(
            success=success,
            method=method,
            errors=errors,
            warnings=warnings,
        )

    def export_package(self, session: Session) -> bytes:
        """
        导出素材包

        Args:
            session: 会话对象

        Returns:
            bytes: ZIP 文件内容
        """
        buffer = BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. 写入笔记内容 (content.json)
            content_data = self._build_content_json(session)
            zf.writestr("content.json", json.dumps(content_data, ensure_ascii=False, indent=2))

            # 2. 写入纯文本版本 (content.txt)
            text_content = self._build_text_content(session)
            zf.writestr("content.txt", text_content)

            # 3. 写入图片
            for item in session.get_items_by_type(ContentType.IMAGE):
                if item.content and item.content.startswith("data:"):
                    # base64 图片
                    import base64
                    img_data = base64.b64decode(item.content.split(",")[1])
                    ext = item.metadata.get("format", "jpg")
                    zf.writestr(f"images/{item.item_id}.{ext}", img_data)
                elif item.content and item.content.startswith("http"):
                    # URL 图片，记录 URL
                    with open(f"images_urls.txt", "a") as f:
                        f.write(f"{item.item_id}: {item.content}\n")

            # 4. 写入视频
            for item in session.get_items_by_type(ContentType.VIDEO):
                if item.content:
                    if item.content.startswith("data:"):
                        import base64
                        video_data = base64.b64decode(item.content.split(",")[1])
                        ext = item.metadata.get("format", "mp4")
                        zf.writestr(f"video/{item.item_id}.{ext}", video_data)
                    elif item.content.startswith("http"):
                        with open("video_urls.txt", "a") as f:
                            f.write(f"{item.item_id}: {item.content}\n")

            # 5. 写入音频
            for item in session.get_items_by_type(ContentType.AUDIO):
                if item.content and item.content.startswith("data:"):
                    import base64
                    audio_data = base64.b64decode(item.content.split(",")[1])
                    ext = item.metadata.get("format", "mp3")
                    zf.writestr(f"audio/{item.item_id}.{ext}", audio_data)

            # 6. 写入 metadata.json
            metadata = {
                "session_id": session.session_id,
                "version": session.current_version,
                "created_at": session.created_at.isoformat(),
                "exported_at": datetime.now().isoformat(),
                "brief": session.brief.to_dict() if hasattr(session.brief, "to_dict") else session.brief,
            }
            zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

        buffer.seek(0)
        return buffer.getvalue()

    def _build_content_json(self, session: Session) -> Dict[str, Any]:
        """构建小红书内容 JSON"""
        # 收集所有文本内容
        title = ""
        headline = ""
        paragraphs = []
        hashtags = []
        cta = ""

        for item in session.items:
            if item.item_type == ContentType.TITLE and item.content:
                title = item.content
            elif item.item_type == ContentType.HEADLINE and item.content:
                headline = item.content
            elif item.item_type == ContentType.TEXT and item.content:
                paragraphs.append(item.content)
            elif item.item_type == ContentType.HASHTAG and item.content:
                hashtags.append(item.content)
            elif item.item_type == ContentType.CALL_TO_ACTION and item.content:
                cta = item.content

        # 收集图片 URL
        images = []
        for item in session.get_items_by_type(ContentType.IMAGE):
            if item.content:
                images.append({
                    "id": item.item_id,
                    "url": item.content if item.content.startswith("http") else None,
                    "description": item.metadata.get("description", ""),
                })

        # 收集视频信息
        videos = []
        for item in session.get_items_by_type(ContentType.VIDEO):
            if item.content:
                videos.append({
                    "id": item.item_id,
                    "url": item.content if item.content.startswith("http") else None,
                    "duration": item.metadata.get("duration", 0),
                })

        # 收集音频信息
        audios = []
        for item in session.get_items_by_type(ContentType.AUDIO):
            if item.content:
                audios.append({
                    "id": item.item_id,
                    "url": item.content if item.content.startswith("http") else None,
                })

        return {
            "title": title or headline,
            "headline": headline,
            "paragraphs": paragraphs,
            "hashtags": hashtags,
            "call_to_action": cta,
            "images": images,
            "videos": videos,
            "audios": audios,
            "version": session.current_version,
        }

    def _build_text_content(self, session: Session) -> str:
        """构建纯文本内容"""
        lines = []

        # 标题
        for item in session.items:
            if item.item_type == ContentType.TITLE and item.content:
                lines.append(f"【标题】{item.content}")
                lines.append("")
            elif item.item_type == ContentType.HEADLINE and item.content:
                lines.append(f"【副标题】{item.content}")
                lines.append("")
            elif item.item_type == ContentType.TEXT and item.content:
                lines.append(item.content)
                lines.append("")
            elif item.item_type == ContentType.HASHTAG and item.content:
                lines.append(item.content)
            elif item.item_type == ContentType.CALL_TO_ACTION and item.content:
                lines.append("")
                lines.append(item.content)

        return "\n".join(lines)

    async def publish_via_api(
        self,
        session: Session,
        api_credentials: Dict[str, Any] = None,
    ) -> PublishResult:
        """
        通过 API 发布（预留）

        Args:
            session: 会话对象
            api_credentials: API 凭证

        Returns:
            PublishResult: 发布结果
        """
        # 校验
        validation = self.validate(session)
        if not validation.success:
            return validation

        if not self.config.xiaohongshu_api_enabled:
            return PublishResult(
                success=False,
                method="api",
                errors=["小红书 API 发布功能未启用"],
            )

        # TODO: 实现真实 API 发布
        return PublishResult(
            success=False,
            method="api",
            errors=["API 发布功能开发中"],
        )

    async def simulate_publish(self, session: Session) -> PublishResult:
        """
        模拟发布流程

        Args:
            session: 会话对象

        Returns:
            PublishResult: 模拟结果
        """
        validation = self.validate(session)

        if validation.errors:
            return PublishResult(
                success=False,
                method="simulate",
                errors=validation.errors,
                warnings=validation.warnings,
            )

        return PublishResult(
            success=True,
            method="simulate",
            warnings=[
                "模拟发布成功，实际发布前请确保内容无误",
                f"导出的素材包可从会话详情页下载",
            ],
        )
