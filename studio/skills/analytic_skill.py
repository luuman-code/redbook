"""
AnalyticSkill - 分析 Skill

调用 Phase 2 的 VisionGateway 分析图像
"""

import time
from typing import List, Dict, Any

from .base_skill import BaseSkill, SkillContext, SkillResult
from ..models.content_item import ContentItem, ContentType


class AnalyticSkill(BaseSkill):
    """
    分析 Skill

    封装 Vision 网关调用，提供图像分析和素材理解能力
    """

    SKILL_TYPE = "analytic"
    gateway_type = "vision"

    async def execute(
        self,
        context: SkillContext,
        image_url: str = "",
        image_content: str = "",
        analysis_type: str = "general",
        **kwargs,
    ) -> SkillResult:
        """
        执行图像分析

        Args:
            context: Skill 上下文
            image_url: 图像 URL
            image_content: base64 编码的图像内容
            analysis_type: 分析类型 (general/product/style)

        Returns:
            SkillResult
        """
        start_time = time.time()

        # 验证上下文
        error = self.validate_context(context)
        if error:
            return self.create_error_result(error)

        # 验证图像输入
        if not image_url and not image_content:
            return self.create_error_result("没有提供图像")

        # 确定分析 prompt
        prompt = self._build_prompt(analysis_type)

        # 调用 Vision 网关
        try:
            image = image_content or image_url
            vision_request = self._create_vision_request(
                image=image,
                prompt=prompt,
            )
            response = await self.gateway.invoke(vision_request)

            if not response.success:
                return self.create_error_result(f"图像分析失败: {response.error}")

            # 创建 ContentItem（用于存储分析结果）
            item = ContentItem(
                item_id=f"analysis_{int(time.time() * 1000)}",
                item_type=ContentType.COMPOSITE,  # 分析结果是特殊类型
                content=response.data.get("content", ""),
                metadata={
                    "analysis_type": analysis_type,
                    "model_used": response.model_used,
                    "image_url": image_url,
                },
                status=ContentType.COMPOSITE,
                generation_prompt=prompt,
            )
            item.status = "completed"

            # 解析分析结果并更新上下文
            analysis_result = self._parse_analysis(response.data.get("content", ""), analysis_type)

            return self.create_success_result(
                items=[item],
                metadata={
                    "model_used": response.model_used,
                    "analysis_result": analysis_result,
                    "latency_ms": response.latency_ms,
                },
            )

        except Exception as e:
            return self.create_error_result(f"AnalyticSkill 执行异常: {str(e)}")

    def _build_prompt(self, analysis_type: str) -> str:
        """构建分析 prompt"""
        prompts = {
            "general": "请详细描述这张图片的内容，包括主体、背景、风格等。",
            "product": """请分析这张产品图片，提取：
1. 产品外观描述（颜色、形状、Logo位置）
2. 产品使用场景
3. 包装规格（如果可见）
4. 品牌调性""",
            "style": """请分析这张图片的风格特点：
1. 整体色调
2. 构图方式
3. 视觉风格（日系/欧美/小清新等）
4. 适用的配图场景""",
        }
        return prompts.get(analysis_type, prompts["general"])

    def _create_vision_request(self, image: str, prompt: str):
        """创建 Vision 请求对象"""
        class VisionRequest:
            def __init__(self):
                self.image = image
                self.prompt = prompt
                self.kwargs = {}

        return VisionRequest()

    def _parse_analysis(self, content: str, analysis_type: str) -> Dict[str, Any]:
        """解析分析结果"""
        # 简单的结构化提取，实际可以更复杂
        result = {
            "raw_analysis": content,
        }

        if analysis_type == "product":
            # 提取产品信息
            lines = content.split("\n")
            for line in lines:
                if "颜色" in line or "外观" in line:
                    result["appearance"] = line
                elif "场景" in line:
                    result["scene"] = line
                elif "包装" in line:
                    result["package"] = line

        return result
