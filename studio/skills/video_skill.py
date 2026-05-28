"""
VideoSkill - 视频生成 Skill

调用 Phase 2 的 VideoGateway 生成视频
"""

import time
from typing import List

from .base_skill import BaseSkill, SkillContext, SkillResult
from ..models.content_item import ContentItem, ContentType


class VideoSkill(BaseSkill):
    """
    视频生成 Skill

    封装 Video 网关调用，提供视频生成能力
    视频生成是异步的，需要轮询
    """

    SKILL_TYPE = "video"
    gateway_type = "video"

    async def execute(
        self,
        context: SkillContext,
        duration: int = 15,
        resolution: str = "1080p",
        **kwargs,
    ) -> SkillResult:
        """
        执行视频生成

        Args:
            context: Skill 上下文
            duration: 视频时长（秒）
            resolution: 视频分辨率

        Returns:
            SkillResult
        """
        start_time = time.time()

        # 验证上下文
        error = self.validate_context(context)
        if error:
            return self.create_error_result(error)

        # 构建 prompt
        prompt = self._build_prompt(context, duration)

        # 调用视频网关
        try:
            video_request = self._create_video_request(
                prompt=prompt,
                duration=duration,
                resolution=resolution,
            )
            response = await self.gateway.invoke(video_request)

            if not response.success:
                return self.create_error_result(f"视频生成失败: {response.error}")

            # 创建 ContentItem
            item = ContentItem(
                item_id=f"vid_{int(time.time() * 1000)}",
                item_type=ContentType.VIDEO,
                content=response.data.get("video_url", ""),
                metadata={
                    "task_id": response.data.get("task_id"),
                    "duration": duration,
                    "resolution": resolution,
                    "model_used": response.model_used,
                },
                status=ContentType.VIDEO,
                generation_prompt=prompt,
            )
            item.status = "completed"

            return self.create_success_result(
                items=[item],
                metadata={
                    "model_used": response.model_used,
                    "task_id": response.data.get("task_id"),
                    "latency_ms": response.latency_ms,
                },
            )

        except Exception as e:
            return self.create_error_result(f"VideoSkill 执行异常: {str(e)}")

    def _build_prompt(self, context: SkillContext, duration: int) -> str:
        """构建视频生成 prompt"""
        metadata = context.metadata

        prompt_parts = [
            f"生成一段 {duration} 秒的小红书风格短视频",
        ]

        # 场景描述
        if metadata.get("scenes"):
            scenes = metadata["scenes"]
            prompt_parts.append("场景：")
            for scene in scenes:
                prompt_parts.append(f"- {scene.get('description', scene.get('visual_prompt', ''))}")

        # 风格
        if metadata.get("style"):
            prompt_parts.append(f"风格: {metadata['style']}")

        # 旁白
        if metadata.get("voiceover"):
            prompt_parts.append(f"旁白: {metadata['voiceover']}")

        return "\n".join(prompt_parts)

    def _create_video_request(self, prompt: str, duration: int, resolution: str):
        """创建视频生成请求对象"""
        class VideoRequest:
            def __init__(self):
                self.prompt = prompt
                self.duration = duration
                self.resolution = resolution
                self.aspect_ratio = "16:9"
                self.kwargs = {}

        return VideoRequest()
