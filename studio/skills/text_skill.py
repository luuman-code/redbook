"""
TextSkill - 文本生成 Skill

调用 Phase 2 的 LLMGateway 生成文案
"""

import time
from typing import List

from .base_skill import BaseSkill, SkillContext, SkillResult
from ..models.content_item import ContentItem, ContentType


class TextSkill(BaseSkill):
    """
    文本生成 Skill

    封装 LLM 网关调用，提供文案生成能力
    """

    SKILL_TYPE = "text"
    gateway_type = "llm"

    async def execute(
        self,
        context: SkillContext,
        section_type: str = "text",
        content_words: int = 300,
        style_hint: str = "",
        **kwargs,
    ) -> SkillResult:
        """
        执行文案生成

        Args:
            context: Skill 上下文
            section_type: 文案类型 (title/headline/text/hashtag/call_to_action)
            content_words: 目标字数
            style_hint: 风格提示

        Returns:
            SkillResult
        """
        start_time = time.time()

        # 验证上下文
        error = self.validate_context(context)
        if error:
            return self.create_error_result(error)

        # 获取之前的同类内容（用于保持风格一致）
        previous_content = context.get_previous_content(section_type)

        # 构建 prompt
        prompt = self._build_prompt(
            context=context,
            section_type=section_type,
            content_words=content_words,
            style_hint=style_hint,
            previous_content=previous_content,
        )

        # 调用 LLM 网关
        try:
            llm_request = self._create_llm_request(prompt, content_words)
            response = await self.gateway.invoke(llm_request)

            if not response.success:
                return self.create_error_result(f"LLM 调用失败: {response.error}")

            # 解析响应
            content = self._parse_response(response.data.get("content", ""))

            # 创建 ContentItem
            item = ContentItem(
                item_id=f"text_{section_type}_{int(time.time() * 1000)}",
                item_type=ContentType(section_type),
                content=content,
                status=response.success,
                generation_prompt=prompt,
            )

            if not response.success:
                item.status = "failed"
                item.error_message = response.error

            return self.create_success_result(
                items=[item],
                metadata={
                    "model_used": response.model_used,
                    "latency_ms": response.latency_ms,
                },
            )

        except Exception as e:
            return self.create_error_result(f"TextSkill 执行异常: {str(e)}")

    def _build_prompt(
        self,
        context: SkillContext,
        section_type: str,
        content_words: int,
        style_hint: str,
        previous_content: str = None,
    ) -> str:
        """构建生成 prompt"""
        metadata = context.metadata

        prompt_parts = []

        # 上下文信息
        if style_hint:
            prompt_parts.append(f"风格要求: {style_hint}")

        if metadata.get("keywords"):
            prompt_parts.append(f"关键词: {', '.join(metadata['keywords'])}")

        if metadata.get("must_include"):
            prompt_parts.append(f"必须包含: {', '.join(metadata['must_include'])}")

        # 类型特定要求
        if section_type == "title":
            prompt_parts.append("生成一个吸引人的小红书标题（20字以内）")
        elif section_type == "headline":
            prompt_parts.append("生成一个引人注目的开头（50字以内）")
        elif section_type == "text":
            prompt_parts.append(f"生成正文内容（约{content_words}字）")
        elif section_type == "hashtag":
            prompt_parts.append("生成 3-5 个相关话题标签，以 # 开头")
        elif section_type == "call_to_action":
            prompt_parts.append("生成互动引导语，激发用户评论和分享")

        # 之前的内容（保持一致）
        if previous_content:
            prompt_parts.append(f"\n参考之前的风格：\n{previous_content[:200]}")

        prompt_parts.append("\n只输出文案内容，不要有其他说明。")

        return "\n".join(prompt_parts)

    def _create_llm_request(self, prompt: str, max_tokens: int):
        """创建 LLM 请求对象"""
        # 使用简单的字典模拟请求对象
        class LLMRequest:
            def __init__(self):
                self.messages = [{"role": "user", "content": prompt}]
                self.temperature = 0.8
                self.max_tokens = max_tokens
                self.kwargs = {}

        return LLMRequest()

    def _parse_response(self, content: str) -> str:
        """解析 LLM 响应"""
        # 去除可能的 markdown 格式
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        return content.strip()
