"""
AudioSkill - 音频生成 Skill

调用 Phase 2 的 TTSGateway 生成语音
"""

import time
from typing import List

from .base_skill import BaseSkill, SkillContext, SkillResult
from ..models.content_item import ContentItem, ContentType


class AudioSkill(BaseSkill):
    """
    音频生成 Skill

    封装 TTS 网关调用，提供语音合成能力
    """

    SKILL_TYPE = "audio"
    gateway_type = "tts"

    async def execute(
        self,
        context: SkillContext,
        text: str = "",
        voice: str = "alloy",
        speed: float = 1.0,
        **kwargs,
    ) -> SkillResult:
        """
        执行音频生成

        Args:
            context: Skill 上下文
            text: 要转换的文本
            voice: 音色
            speed: 语速

        Returns:
            SkillResult
        """
        start_time = time.time()

        # 验证上下文
        error = self.validate_context(context)
        if error:
            return self.create_error_result(error)

        # 如果没有提供文本，尝试从之前的内容中获取
        if not text:
            text = context.get_previous_content("text")
            if text:
                text = text[:500]  # 限制长度

        if not text:
            return self.create_error_result("没有可转换的文本内容")

        # 调用 TTS 网关
        try:
            tts_request = self._create_tts_request(
                text=text,
                voice=voice,
                speed=speed,
            )
            response = await self.gateway.invoke(tts_request)

            if not response.success:
                return self.create_error_result(f"语音合成失败: {response.error}")

            # 创建 ContentItem
            item = ContentItem(
                item_id=f"aud_{int(time.time() * 1000)}",
                item_type=ContentType.AUDIO,
                content=f"data:audio/{response.data.get('format', 'mp3')};base64,...",
                metadata={
                    "format": response.data.get("format", "mp3"),
                    "voice": voice,
                    "speed": speed,
                    "audio_data": response.data.get("audio"),
                    "model_used": response.model_used,
                },
                status=ContentType.AUDIO,
                generation_prompt=text,
            )
            item.status = "completed"

            return self.create_success_result(
                items=[item],
                metadata={
                    "model_used": response.model_used,
                    "format": response.data.get("format"),
                    "latency_ms": response.latency_ms,
                },
            )

        except Exception as e:
            return self.create_error_result(f"AudioSkill 执行异常: {str(e)}")

    def _create_tts_request(self, text: str, voice: str, speed: float):
        """创建 TTS 请求对象"""
        class TTSRequest:
            def __init__(self):
                self.input = text
                self.voice = voice
                self.speed = speed
                self.response_format = "mp3"
                self.kwargs = {}

        return TTSRequest()
