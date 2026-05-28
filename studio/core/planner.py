"""
Planner - 内容规划器

根据 Brief 生成内容方案

参考 plan.md:
- 方案规划 Agent (Planner)：接到 Brief 后输出一份内容实施方案
"""

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..models.brief import Brief
from ..models.content_plan import (
    AudioPlan,
    ContentPlan,
    ImagePlan,
    TextSection,
    VideoPlan,
)
from ..debug_logger import get_logger, get_workflow_logger

# 获取日志记录器
logger = get_logger("planner")

# 导入 agent 模块的请求类
from agent.models.llm_gateway import LLMRequest


@dataclass
class PlanResult:
    """规划结果"""
    success: bool
    plan: Optional[ContentPlan] = None
    error: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


from dataclasses import dataclass


class Planner:
    """
    内容规划器

    职责：
    1. 接收 Brief
    2. 生成文案结构（标题、正文段落、话题标签等）
    3. 生成配图方案
    4. 生成视频/音频方案（如需要）
    5. 估算创作时间和资源需求
    """

    def __init__(self, llm_gateway, config=None):
        """
        初始化 Planner

        Args:
            llm_gateway: LLM 网关实例
            config: Studio 配置
        """
        self.llm_gateway = llm_gateway
        self.config = config

    async def plan(self, brief: Brief) -> PlanResult:
        """
        根据 Brief 生成内容方案

        Args:
            brief: Brief 对象

        Returns:
            PlanResult: 包含内容方案或错误信息
        """
        wf_logger = get_workflow_logger("planner.plan")
        wf_logger.start("plan")
        logger.debug(f"Planning content for brief: goal={brief.goal.value}, style={brief.style}")

        try:
            # Step 1: 生成文案结构（仅当需要文案时）
            text_plan = None
            if brief.need_text:
                logger.debug("Generating text plan...")
                wf_logger.start("_generate_text_plan")
                text_plan = await self._generate_text_plan(brief)
                wf_logger.end("_generate_text_plan", success=True, message=f"sections={len(text_plan.get('sections', [])) if text_plan else 0}")

            # Step 2: 生成配图方案（仅当需要配图时）
            image_plan = None
            if brief.need_images:
                logger.debug("Generating image plan...")
                wf_logger.start("_generate_image_plan")
                image_plan = await self._generate_image_plan(brief)
                wf_logger.end("_generate_image_plan", success=True, message=f"count={image_plan.count if image_plan else 0}")

            # Step 3: 生成视频/音频方案（如需要）
            video_plan = None
            audio_plan = None

            if brief.need_video:
                logger.debug("Generating video plan...")
                wf_logger.start("_generate_video_plan")
                video_plan = await self._generate_video_plan(brief)
                wf_logger.end("_generate_video_plan", success=True)

            if brief.need_voiceover:
                logger.debug("Generating audio plan...")
                wf_logger.start("_generate_audio_plan")
                audio_plan = await self._generate_audio_plan(brief, text_plan)
                wf_logger.end("_generate_audio_plan", success=True)

            # Step 4: 构建完整方案
            plan = ContentPlan(
                plan_id=str(uuid.uuid4()),
                brief_id=brief.id,
                title=text_plan.get("suggested_title", "") if text_plan else "",
                text_sections=self._build_text_sections(text_plan) if text_plan else [],
                image_plan=image_plan,
                video_plan=video_plan,
                audio_plan=audio_plan,
                estimated_duration=self._estimate_duration(brief, text_plan, image_plan, video_plan),
                version=1,
            )

            # Step 5: 验证方案
            warnings = self._validate_plan(plan, brief)
            logger.info(f"Plan generated successfully: plan_id={plan.plan_id}, title={plan.title[:30] if plan.title else 'N/A'}...")
            wf_logger.end("plan", success=True, message=f"plan_id={plan.plan_id}")

            return PlanResult(success=True, plan=plan, warnings=warnings)

        except Exception as e:
            logger.error(f"plan exception: {e}", exc_info=True)
            wf_logger.error("plan", e)
            return PlanResult(success=False, error=f"规划异常: {str(e)}")

    async def _generate_text_plan(self, brief: Brief) -> Dict[str, Any]:
        """生成文案结构计划"""
        # 如果有模板分析，将其融入到 prompt 中
        template_context = ""
        if brief.template_analysis:
            template_context = """
【重要】用户提供了文案模板参考！在生成内容时必须遵循模板的风格和结构：

"""
            for i, ta in enumerate(brief.template_analysis):
                analysis_text = ta.get('analysis', '')
                template_context += f"""
模板 {i+1} 分析结果：
{analysis_text}

"""

        prompt = f"""你是一个专业的小红书文案策划。请根据以下 Brief 生成内容方案。
{template_context}
Brief:
- 内容目标: {brief.goal.value}
- 风格: {brief.style}
- 关键词: {', '.join(brief.keywords)}
- 必须包含: {', '.join(brief.must_include)}
- 目标受众: {brief.target_audience}

请生成以下 JSON 结构：
{{
    "suggested_title": "建议标题（吸引眼球）",
    "sections": [
        {{
            "type": "headline/title/paragraph/hashtag/call_to_action",
            "content_words": 目标字数,
            "priority": 优先级(1-3),
            "is_optional": 是否可选
        }}
    ],
    "estimated_read_time": "预估阅读时间",
    "engagement_tips": "提升互动性的建议"
}}

要求：
- 标题要吸引眼球，引发好奇心
- 正文字数控制在 300-500 字
- 包含 3-5 个话题标签
- 互动引导语激发评论
"""

        # 如果有模板，强调遵循模板风格
        if brief.template_analysis:
            prompt += """
【重点】生成的文案结构必须遵循模板风格：
- 标题格式与模板保持一致
- 分段方式和长度参考模板
- 语气和表达风格与模板相似
"""

        prompt += "\n只输出 JSON。"
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1500,
        )
        response = await self.llm_gateway.invoke(llm_request)

        if response.success:
            import json
            import re

            content = response.data.get("content", "")
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())

        # 默认文案结构
        return {
            "suggested_title": "",
            "sections": [
                {"type": "headline", "content_words": 20, "priority": 1, "is_optional": False},
                {"type": "paragraph", "content_words": 400, "priority": 1, "is_optional": False},
                {"type": "hashtag", "content_words": 10, "priority": 2, "is_optional": False},
                {"type": "call_to_action", "content_words": 30, "priority": 3, "is_optional": True},
            ],
        }

    async def _generate_image_plan(self, brief: Brief) -> ImagePlan:
        """生成配图方案"""
        # 用户原始需求描述（无素材时用于推断配图方向）
        user_description = brief.raw_input or ""

        prompt = f"""根据以下 Brief 生成配图方案。

用户需求描述：
{user_description}

Brief:
- 产品/内容风格: {brief.image_style}
- 必须包含的元素: {', '.join(brief.must_include) if brief.must_include else '无特定要求'}
- 参考素材描述: {brief.extracted_product_info.get('visual_description', '无参考素材')}

请根据"用户需求描述"推断应该生成什么样的配图，并生成 JSON：
{{
    "style": "配图风格描述",
    "elements": ["画面元素1", "画面元素2"],
    "count": 配图数量(建议3-6张),
    "aspect_ratio": "宽高比(1:1/4:3/16:9)",
    "color_scheme": "色调偏好",
    "reference_image_ids": []
}}

只输出 JSON。
"""
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800,
        )
        response = await self.llm_gateway.invoke(llm_request)

        if response.success:
            import json
            import re

            content = response.data.get("content", "")
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                data = json.loads(json_match.group())
                return ImagePlan(
                    style=data.get("style", brief.image_style),
                    elements=data.get("elements", []),
                    count=data.get("count", 4),
                    aspect_ratio=data.get("aspect_ratio", "1:1"),
                    color_scheme=data.get("color_scheme"),
                    reference_image_ids=data.get("reference_image_ids", []),
                )

        # 默认配图方案
        return ImagePlan(
            style=brief.image_style,
            elements=brief.must_include[:3] if brief.must_include else ["产品图"],
            count=4,
            aspect_ratio="1:1",
        )

    async def _generate_video_plan(self, brief: Brief) -> Optional[VideoPlan]:
        """生成视频方案"""
        # 用户原始需求描述（无素材时用于推断视频内容）
        user_description = brief.raw_input or ""

        # 根据参考素材类型确定视频模型
        # video-edit: 有视频素材，i2v: 有图片素材，t2v: 只有文字
        video_model_type = "t2v"  # 默认文生视频
        has_video_material = False
        has_image_material = False

        if brief.reference_materials:
            for mat in brief.reference_materials:
                if mat.material_type == "video":
                    has_video_material = True
                    break
                elif mat.material_type == "image":
                    has_image_material = True

        if has_video_material:
            video_model_type = "video-edit"
        elif has_image_material:
            video_model_type = "i2v"  # 图生视频

        prompt = f"""根据以下 Brief 生成视频脚本方案。

用户需求描述：
{user_description}

Brief:
- 内容目标: {brief.goal.value}
- 风格: {brief.style}
- 必须包含的元素: {', '.join(brief.must_include) if brief.must_include else '无特定要求'}
- 可用素材: {"有视频素材" if has_video_material else "无视频素材"}，{"有图片素材" if has_image_material else "无图片素材"}

请根据"用户需求描述"推断应该生成什么样的视频内容。

重要：只输出纯JSON，不要包含任何其他文字、markdown标记或解释。
JSON格式：
{{"duration":30,"scenes":[{{"scene_id":"场景1","description":"描述","duration":15,"visual_prompt":"画面描述"}}],"voiceover":"旁白","voice_type":"声音类型","style":"风格"}}
"""
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,
        )
        response = await self.llm_gateway.invoke(llm_request)

        if response.success:
            import json
            import re

            content = response.data.get("content", "")
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return VideoPlan(
                        duration=data.get("duration", 15),
                        scenes=data.get("scenes", []),
                        voiceover=data.get("voiceover", ""),
                        voice_type=data.get("voice_type", "温柔女声"),
                        style=data.get("style", "生活记录"),
                        bgm_style=brief.bgm_preference if brief.need_bgm else False,
                        model_type=video_model_type,
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Video plan JSON parse failed: {e}, using fallback")

        # Fallback: 根据 brief 信息构建默认视频方案
        return VideoPlan(
            duration=15,
            scenes=[
                {
                    "scene_id": "scene_1",
                    "description": f"展示 {brief.must_include[0] if brief.must_include else brief.goal.value}",
                    "duration": 15,
                    "visual_prompt": f"小红书风格短视频，画面展示{brief.must_include[0] if brief.must_include else '相关内容'}，风格{brief.style}"
                }
            ] if brief.must_include else [],
            voiceover="介绍内容和特点",
            voice_type="温柔女声",
            style=brief.style or "生活记录",
            bgm_style=brief.bgm_preference if brief.need_bgm else False,
            model_type=video_model_type,
        )

    async def _generate_audio_plan(self, brief: Brief, text_plan: Optional[Dict[str, Any]]) -> AudioPlan:
        """生成音频方案"""
        # 提取正文作为 TTS 文本
        tts_text = ""
        if text_plan:
            for section in text_plan.get("sections", []):
                if section.get("type") == "paragraph":
                    tts_text += section.get("content", "")[:500]  # 限制长度
                    break

        # 如果没有正文文本，根据用户需求生成一段配音文本
        if not tts_text:
            tts_text = f"今天给大家分享{', '.join(brief.must_include[:2]) if brief.must_include else brief.goal.value}，{brief.style}风格介绍"

        return AudioPlan(
            tts_text=tts_text,
            voice="alloy",
            speed=1.0,
            bgm_style=brief.bgm_preference if brief.need_bgm else None,
        )

    def _build_text_sections(self, text_plan: Dict[str, Any]) -> List[TextSection]:
        """构建 TextSection 列表"""
        sections = []
        section_types = text_plan.get("sections", [])

        type_mapping = {
            "headline": "headline",
            "title": "title",
            "paragraph": "text",
            "hashtag": "hashtag",
            "call_to_action": "cta",  # ContentType.CALL_TO_ACTION = "cta"
        }

        for i, sec in enumerate(section_types):
            sec_type = type_mapping.get(sec.get("type", "text"), "text")
            section = TextSection(
                section_id=f"sec_{uuid.uuid4().hex[:8]}",
                section_type=sec_type,
                content="",  # 待生成
                content_words=sec.get("content_words"),
                priority=sec.get("priority", 1),
                is_optional=sec.get("is_optional", False),
            )
            sections.append(section)

        return sections

    def _estimate_duration(
        self,
        brief: Brief,
        text_plan: Dict[str, Any],
        image_plan: ImagePlan,
        video_plan: Optional[VideoPlan],
    ) -> int:
        """估算创作时间（分钟）"""
        duration = 30  # 基础时间

        # 文案时间
        if text_plan:
            duration += len(text_plan.get("sections", [])) * 5

        # 配图时间
        if image_plan:
            duration += image_plan.count * 3

        # 视频时间
        if video_plan:
            duration += video_plan.duration // 10 + 5

        # 语音时间
        if brief.need_voiceover:
            duration += 5

        return duration

    def _validate_plan(self, plan: ContentPlan, brief: Brief) -> List[str]:
        """验证方案，返回警告列表"""
        warnings = []

        if not plan.title:
            warnings.append("标题为空，建议手动补充")

        if plan.image_plan and plan.image_plan.count > 9:
            warnings.append("配图数量过多，可能影响加载速度")

        if brief.need_video and not plan.video_plan:
            warnings.append("需要视频但未生成视频方案")

        if brief.need_voiceover and not plan.audio_plan:
            warnings.append("需要配音但未生成音频方案")

        return warnings

    async def generate_plans(
        self,
        brief: Brief,
        plan_count: int = 3,
        style_variations: List[str] = None,
    ) -> List[PlanResult]:
        """
        根据 Brief 生成多个备选方案

        Args:
            brief: Brief 对象
            plan_count: 生成的方案数量，默认 3 个
            style_variations: 风格变体列表，如 ["种草", "教程", "测评"]

        Returns:
            List[PlanResult]: 包含多个方案的列表
        """
        wf_logger = get_workflow_logger("planner.generate_plans")
        wf_logger.start("generate_plans")
        logger.info(f"Generating {plan_count} plans for brief: goal={brief.goal.value}")

        results = []

        # 如果没有指定风格变体，使用默认变体
        if not style_variations:
            style_variations = [
                "种草风格 - 真实分享推荐",
                "教程风格 - 步骤详解指南",
                "测评风格 - 专业对比分析",
            ]

        # 限制方案数量
        plan_count = min(plan_count, len(style_variations))

        try:
            for i in range(plan_count):
                logger.debug(f"Generating plan {i + 1}/{plan_count} with style: {style_variations[i]}")
                wf_logger.start(f"plan_{i}")

                # 为每个方案构建特殊的 prompt
                text_plan = None
                if brief.need_text:
                    text_plan = await self._generate_text_plan_with_style(brief, style_variations[i])

                image_plan = None
                if brief.need_images:
                    image_plan = await self._generate_image_plan(brief)

                video_plan = None
                audio_plan = None

                if brief.need_video:
                    video_plan = await self._generate_video_plan(brief)
                if brief.need_voiceover:
                    audio_plan = await self._generate_audio_plan(brief, text_plan)

                plan = ContentPlan(
                    plan_id=str(uuid.uuid4()),
                    brief_id=brief.id,
                    title=text_plan.get("suggested_title", "") if text_plan else "",
                    text_sections=self._build_text_sections(text_plan) if text_plan else [],
                    image_plan=image_plan,
                    video_plan=video_plan,
                    audio_plan=audio_plan,
                    estimated_duration=self._estimate_duration(brief, text_plan, image_plan, video_plan),
                    version=1,
                )

                warnings = self._validate_plan(plan, brief)
                results.append(PlanResult(success=True, plan=plan, warnings=warnings))

                wf_logger.end(f"plan_{i}", success=True, message=f"plan_id={plan.plan_id}")

            logger.info(f"Generated {len(results)} plans successfully")
            wf_logger.end("generate_plans", success=True, message=f"count={len(results)}")

        except Exception as e:
            logger.error(f"generate_plans exception: {e}", exc_info=True)
            wf_logger.error("generate_plans", e)
            results.append(PlanResult(success=False, error=f"生成方案异常: {str(e)}"))

        return results

    async def _generate_text_plan_with_style(
        self,
        brief: Brief,
        style_variation: str,
    ) -> Dict[str, Any]:
        """根据指定风格生成文案结构计划"""
        prompt = f"""你是一个专业的小红书文案策划。请根据以下 Brief 生成内容方案。

Brief:
- 内容目标: {brief.goal.value}
- 风格: {brief.style}
- 关键词: {', '.join(brief.keywords)}
- 必须包含: {', '.join(brief.must_include)}
- 目标受众: {brief.target_audience}

风格要求: {style_variation}

请生成以下 JSON 结构：
{{
    "suggested_title": "建议标题（吸引眼球，符合{style_variation}风格）",
    "sections": [
        {{
            "type": "headline/title/paragraph/hashtag/call_to_action",
            "content_words": 目标字数,
            "priority": 优先级(1-3),
            "is_optional": 是否可选
        }}
    ],
    "estimated_read_time": "预估阅读时间",
    "engagement_tips": "提升互动性的建议"
}}

要求：
- 标题要吸引眼球，符合{style_variation}
- 正文字数控制在 300-500 字
- 包含 3-5 个话题标签
- 互动引导语激发评论
- 整体风格: {style_variation}

只输出 JSON。
"""
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1500,
        )
        response = await self.llm_gateway.invoke(llm_request)

        if response.success:
            import json
            import re

            content = response.data.get("content", "")
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())

        # 默认文案结构
        return {
            "suggested_title": "",
            "sections": [
                {"type": "headline", "content_words": 20, "priority": 1, "is_optional": False},
                {"type": "paragraph", "content_words": 400, "priority": 1, "is_optional": False},
                {"type": "hashtag", "content_words": 10, "priority": 2, "is_optional": False},
                {"type": "call_to_action", "content_words": 30, "priority": 3, "is_optional": True},
            ],
        }

    async def modify_plan(
        self,
        brief: Brief,
        user_feedback: str,
    ) -> PlanResult:
        """
        根据用户反馈修改 Brief 并生成新方案

        Args:
            brief: 原始 Brief 对象
            user_feedback: 用户修改需求

        Returns:
            PlanResult: 包含修改后的新方案
        """
        wf_logger = get_workflow_logger("planner.modify_plan")
        wf_logger.start("modify_plan")
        logger.info(f"Modifying plan for brief: goal={brief.goal.value}, feedback: {user_feedback[:50]}...")

        try:
            # Step 1: 根据用户反馈修改 Brief
            modified_brief = await self._modify_brief_from_feedback(brief, user_feedback)

            # Step 2: 生成新方案
            new_plan_result = await self.plan(modified_brief)

            logger.info(f"Plan modified successfully: new_title={new_plan_result.plan.title[:30] if new_plan_result.plan.title else 'N/A'}...")
            wf_logger.end("modify_plan", success=True)

            return new_plan_result

        except Exception as e:
            logger.error(f"modify_plan exception: {e}", exc_info=True)
            wf_logger.error("modify_plan", e)
            return PlanResult(success=False, error=f"修改方案异常: {str(e)}")

    async def _modify_brief_from_feedback(
        self,
        brief: Brief,
        user_feedback: str,
    ) -> Brief:
        """根据用户反馈修改 Brief"""
        prompt = f"""你是一个专业的小红书内容策划助手。请根据用户的反馈修改 Brief。

原始 Brief:
- 内容目标: {brief.goal.value}
- 风格: {brief.style}
- 关键词: {', '.join(brief.keywords)}
- 必须包含: {', '.join(brief.must_include)}
- 目标受众: {brief.target_audience}

用户反馈：{user_feedback}

请分析用户反馈，判断是否需要修改以下字段：
- goal: 内容目标类型（plant/tutorial/review/lifestyle/product）
- style: 风格（活泼/专业/治愈/清新等）
- keywords: 关键词（添加或修改）
- must_include: 必须包含的元素
- target_audience: 目标受众

请以 JSON 格式输出修改后的 Brief（只输出 JSON，不要有其他文字）：
{{
    "goal": "修改后的目标，不变则保持原值",
    "style": "修改后的风格，不变则保持原值",
    "keywords": ["修改后的关键词列表"],
    "must_include": ["修改后的必须包含元素列表"],
    "target_audience": "修改后的目标受众描述"
}}

注意：只输出 JSON。
"""
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        response = await self.llm_gateway.invoke(llm_request)

        if response.success:
            import json
            import re

            content = response.data.get("content", "")
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                data = json.loads(json_match.group())

                # 创建修改后的 Brief 副本
                from ..models.brief import ContentGoal
                modified_brief = Brief(
                    id=brief.id,
                    goal=ContentGoal(data.get("goal", brief.goal.value)),
                    style=data.get("style", brief.style),
                    keywords=data.get("keywords", brief.keywords),
                    must_include=data.get("must_include", brief.must_include),
                    image_style=brief.image_style,
                    need_video=brief.need_video,
                    need_voiceover=brief.need_voiceover,
                    need_text=brief.need_text,
                    need_images=brief.need_images,
                    need_bgm=brief.need_bgm,
                    bgm_preference=brief.bgm_preference,
                    target_audience=data.get("target_audience", brief.target_audience),
                    reference_materials=brief.reference_materials,
                    raw_input=brief.raw_input,
                    extracted_product_info=brief.extracted_product_info,
                    template_image_url=brief.template_image_url,
                    template_analysis=brief.template_analysis,
                )
                return modified_brief

        # 如果解析失败，返回原始 Brief
        return brief
