"""
ImageSkill - 图像生成 Skill

调用 Phase 2 的 ImageGenerationGateway 生成配图
"""

import time
from typing import List

from .base_skill import BaseSkill, SkillContext, SkillResult
from ..models.content_item import ContentItem, ContentType


class ImageSkill(BaseSkill):
    """
    图像生成 Skill

    封装 ImageGeneration 网关调用，提供配图生成能力
    """

    SKILL_TYPE = "image"
    gateway_type = "image_generation"

    async def execute(
        self,
        context: SkillContext,
        style: str = "摄影实拍",
        elements: List[str] = None,
        size: str = "1024x1024",
        **kwargs,
    ) -> SkillResult:
        """
        执行图像生成

        Args:
            context: Skill 上下文
            style: 图像风格
            elements: 画面元素列表
            size: 图像尺寸

        Returns:
            SkillResult
        """
        start_time = time.time()
        elements = elements or []

        # 验证上下文
        error = self.validate_context(context)
        if error:
            return self.create_error_result(error)

        # 构建 prompt
        prompt = self._build_prompt(
            context=context,
            style=style,
            elements=elements,
        )

        # 调用图像网关
        try:
            image_request = self._create_image_request(
                prompt=prompt,
                size=size,
            )
            response = await self.gateway.invoke(image_request)

            if not response.success:
                return self.create_error_result(f"图像生成失败: {response.error}")

            # 解析响应
            images = response.data.get("images", [])
            items = []

            for i, img_data in enumerate(images):
                item = ContentItem(
                    item_id=f"img_{int(time.time() * 1000)}_{i}",
                    item_type=ContentType.IMAGE,
                    content=img_data.get("url", ""),
                    metadata={
                        "b64_json": img_data.get("b64_json"),
                        "revised_prompt": img_data.get("revised_prompt"),
                        "model_used": response.model_used,
                    },
                    status=ContentType.IMAGE,
                    generation_prompt=prompt,
                )
                item.status = "completed"
                items.append(item)

            return self.create_success_result(
                items=items,
                metadata={
                    "model_used": response.model_used,
                    "count": len(images),
                    "latency_ms": response.latency_ms,
                },
            )

        except Exception as e:
            return self.create_error_result(f"ImageSkill 执行异常: {str(e)}")

    def _build_prompt(
        self,
        context: SkillContext,
        style: str,
        elements: List[str],
    ) -> str:
        """构建图像生成 prompt"""
        metadata = context.metadata

        prompt_parts = [f"生成小红书风格的{style}图片"]

        # 元素
        if elements:
            prompt_parts.append(f"画面元素: {', '.join(elements)}")

        # 产品信息
        if metadata.get("product_description"):
            prompt_parts.append(f"产品外观: {metadata['product_description']}")

        # 关键词
        if metadata.get("keywords"):
            prompt_parts.append(f"关键词: {', '.join(metadata['keywords'])}")

        prompt_parts.append("要求：画面精美，符合小红书美学风格")

        return "\n".join(prompt_parts)

    def _create_image_request(self, prompt: str, size: str):
        """创建图像生成请求对象"""
        class ImageRequest:
            def __init__(self):
                self.prompt = prompt
                self.size = size
                self.quality = "standard"
                self.n = 1
                self.response_format = "url"
                self.kwargs = {}

        return ImageRequest()
