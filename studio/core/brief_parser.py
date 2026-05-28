"""
BriefParser - 需求解析器

将用户模糊需求转化为结构化 Brief

参考 plan.md:
- 多模态输入：支持文字描述、图片、短视频、参考文案、产品文档等
- 需求解析 Agent：用 LLM 将用户模糊需求转化为结构化 Brief
"""

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config.studio_config import StudioConfig
from ..models.brief import Brief, ContentGoal, Material
from ..debug_logger import get_logger, get_workflow_logger

# 获取日志记录器
logger = get_logger("brief_parser")

# 导入 agent 模块的请求类
from agent.models.llm_gateway import LLMRequest
from agent.models.vision_gateway import VisionRequest


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    brief: Optional[Brief] = None
    error: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class BriefParser:
    """
    Brief 解析器

    职责：
    1. 接收用户原始输入（文字+素材）
    2. 调用 Vision 模型分析参考图片
    3. 调用 LLM 生成结构化 Brief
    """

    def __init__(self, llm_gateway, vision_gateway=None, config: StudioConfig = None):
        """
        初始化 BriefParser

        Args:
            llm_gateway: LLM 网关实例（Phase 2）
            vision_gateway: Vision 网关实例（可选）
            config: Studio 配置
        """
        self.llm_gateway = llm_gateway
        self.vision_gateway = vision_gateway
        self.config = config or StudioConfig()

    async def parse(
        self,
        user_input: str,
        materials: List[Dict[str, Any]] = None,
        user_context: Dict[str, Any] = None,
    ) -> ParseResult:
        """
        解析用户需求

        Args:
            user_input: 用户原始输入
            materials: 用户上传的素材列表 [{"type": "image", "url": "...", "content": "base64..."}]
            user_context: 用户上下文信息

        Returns:
            ParseResult: 包含解析后的 Brief 或错误信息
        """
        wf_logger = get_workflow_logger("brief_parser.parse")
        wf_logger.start("parse")
        logger.debug(f"Parsing user input: {user_input[:80]}...")

        materials = materials or []
        user_context = user_context or {}

        try:
            # Step 1: 识别模板图片
            template_image_url = None
            extracted_info = {}  # 不再调用 vision_gateway，直接设为空
            analyzed_materials = []  # 不再分析参考图片，直接设为空

            # 获取模板分析结果（来自 analyze_template 工具）
            template_analysis = user_context.get('template_analysis', [])

            # 识别模板图片：检查用户输入中是否包含"模板"关键词，或者是否有模板分析结果
            has_template_intent = template_analysis or any(keyword in user_input for keyword in ["模板", "template", "套用", "按照这个图", "模仿", "类似"])
            if materials and has_template_intent:
                for mat in materials:
                    # 确保 mat 是字典类型
                    if not isinstance(mat, dict):
                        continue
                    if mat.get("type") == "image" and (mat.get("url") or mat.get("content")):
                        # 优先使用 url，如果 url 不存在则使用 content (base64)
                        content = mat.get("content")
                        url = mat.get("url")

                        # 优先使用 url（已上传到服务器的情况）
                        if url:
                            template_image_url = url
                            logger.debug(f"识别到模板图片 (url): {template_image_url[:50]}...")
                            break
                        # 回退到 content (base64)
                        elif content:
                            # 验证 content 是否是有效的 base64 图片数据（而不是从图片提取的文本内容）
                            # 有效的 base64 图片数据应该是：data:image/...;base64,... 格式，或者纯 base64 字符串
                            is_valid_image_content = False
                            if content.startswith("data:image/"):
                                is_valid_image_content = True
                            else:
                                # 检查是否是纯 base64 字符串（没有 data: 前缀）
                                base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
                                if '\n' not in content and '\r' not in content:
                                    non_base64_count = sum(1 for c in content if c not in base64_chars)
                                    if len(content) > 100 and non_base64_count / len(content) < 0.05:
                                        is_valid_image_content = True

                            if is_valid_image_content:
                                template_image_url = content
                                logger.debug(f"识别到模板图片 (base64 content): {template_image_url[:50]}...")
                                break

            # Step 2: 构建 LLM prompt
            prompt = self._build_parse_prompt(user_input, extracted_info, user_context, template_analysis)
            logger.debug(f"Parse prompt built, length: {len(prompt)}")

            # Step 3: 调用 LLM 解析（使用多模态模型，直接理解模板图片）
            logger.debug("Invoking LLM for brief parsing...")
            wf_logger.start("llm.invoke")

            # 如果有模板图片，使用多模态格式传递
            if template_image_url:
                # 多模态格式：图片 + 文本
                llm_request = LLMRequest(
                    messages=[{
                        "role": "user",
                        "content": [
                            {"image": template_image_url},
                            {"text": prompt}
                        ]
                    }],
                    temperature=0.7,
                    max_tokens=2000,
                )
                logger.debug(f"Using multimodal format with template image")
            else:
                llm_request = LLMRequest(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=2000,
                )
            llm_response = await self.llm_gateway.invoke(llm_request)
            logger.debug(f"LLM response: success={llm_response.success}, latency={llm_response.latency_ms:.2f}ms")
            wf_logger.end("llm.invoke", success=llm_response.success)

            if not llm_response.success:
                logger.warning(f"LLM parsing failed: {llm_response.error}")
                wf_logger.end("parse", success=False, message=llm_response.error)
                return ParseResult(
                    success=False,
                    error=f"LLM 解析失败: {llm_response.error}"
                )

            # Step 4: 解析 LLM 输出为 Brief 结构
            brief_data = self._parse_llm_output(llm_response.data.get("content", ""))
            logger.debug(f"Parsed brief data: goal={brief_data.get('goal')}, style={brief_data.get('style')}")

            # Step 5: 构建 Brief 对象
            brief = Brief(
                id=str(uuid.uuid4()),
                goal=ContentGoal(brief_data.get("goal", "plant")),
                style=brief_data.get("style", "活泼"),
                keywords=brief_data.get("keywords", []),
                must_include=brief_data.get("must_include", []),
                image_style=brief_data.get("image_style", "摄影实拍"),
                need_video=brief_data.get("need_video", False),
                need_voiceover=brief_data.get("need_voiceover", False),
                need_text=brief_data.get("need_text", True),
                need_images=brief_data.get("need_images", True),
                need_bgm=brief_data.get("need_bgm", False),
                bgm_preference=brief_data.get("bgm_preference", "轻快"),
                target_audience=brief_data.get("target_audience", ""),
                reference_materials=self._build_materials(analyzed_materials),
                raw_input=user_input,
                extracted_product_info=extracted_info,
                template_image_url=template_image_url,
                template_analysis=template_analysis,
            )

            # Step 6: 验证 Brief
            warnings = self._validate_brief(brief)
            if warnings:
                logger.debug(f"Brief validation warnings: {warnings}")
                wf_logger.end("parse", success=True, message=f"warnings={len(warnings)}")
                return ParseResult(success=True, brief=brief, warnings=warnings)

            logger.info(f"Brief parsed successfully: goal={brief.goal.value}, style={brief.style}")
            wf_logger.end("parse", success=True, message=f"goal={brief.goal.value}")

            return ParseResult(success=True, brief=brief)

        except Exception as e:
            logger.error(f"parse exception: {e}", exc_info=True)
            wf_logger.error("parse", e)
            return ParseResult(success=False, error=f"解析异常: {str(e)}")

    async def _analyze_image(self, material: Dict[str, Any]) -> Dict[str, Any]:
        """分析参考图片，提取产品信息"""
        try:
            image_content = material.get("content") or material.get("url", "")
            prompt = "请分析这张图片，提取：1. 产品外观描述（颜色、形状、Logo）2. 使用场景 3. 风格特点"

            response = await self.vision_gateway.invoke(
                VisionRequest(images=[image_content], prompt=prompt)
            )

            if response.success:
                # 从响应中提取图片分析结果
                images = response.data.get("images", [])
                if images and len(images) > 0:
                    visual_description = images[0].get("revised_prompt", "")
                else:
                    visual_description = ""
                return {
                    "product_info": {
                        "visual_description": visual_description,
                    }
                }
        except Exception:
            pass

        return {"product_info": {}}

    def _build_parse_prompt(
        self,
        user_input: str,
        extracted_info: Dict[str, Any],
        user_context: Dict[str, Any],
        template_analysis: List[Dict[str, Any]] = None,
    ) -> str:
        """构建解析 prompt"""
        template_analysis = template_analysis or []

        prompt = f"""你是一个专业的小红书内容策划助手。请分析用户的以下需求，生成结构化的内容简报。

用户需求：
{user_input}

"""

        if extracted_info:
            prompt += f"""
参考图片分析结果：
{extracted_info.get('visual_description', '')}

"""

        # 如果有模板分析，添加模板信息到 prompt
        if template_analysis:
            prompt += """
【重要】用户提供了文案模板参考！请在生成内容时参考模板的风格和结构：

"""
            for i, ta in enumerate(template_analysis):
                analysis_text = ta.get('analysis', '')
                prompt += f"""
模板 {i+1} 分析结果：
{analysis_text}

"""

            prompt += """请在生成内容简报时，充分考虑模板的风格特点：
- 标题格式尽量与模板保持一致（如 emoji 使用、疑问句式等）
- 正文的分段方式和长度参考模板
- 语气和表达风格与模板相似
- 标签使用方式参考模板

"""

        prompt += """
请以 JSON 格式输出内容简报，包含以下字段：
{
    "goal": "内容目标，取值：plant(种草)/tutorial(教程)/review(测评)/lifestyle(生活分享)/product(产品展示)",
    "style": "内容风格，如：活泼/专业/治愈/清新",
    "keywords": ["关键词1", "关键词2"],
    "must_include": ["必须包含的元素1", "必须包含的元素2"],
    "image_style": "配图风格，如：摄影实拍/插画/3D",
    "need_video": false,
    "need_voiceover": false,
    "need_text": true,
    "need_images": false,
    "need_bgm": false,
    "bgm_preference": "BGM 风格偏好",
    "target_audience": "目标受众描述"
}

【重要】默认值规则：
- need_text: 默认 true，文案是小红书内容的基本形式
- need_images: 默认 false，只有用户提到"配图"、"图片"时才设为 true
- need_video: 默认 false，只有用户明确提到"视频"、"短视频"时才设为 true
- need_voiceover: 默认 false，只有用户明确提到"配音"、"配音解说"时才设为 true
- need_bgm: 默认 false，只有用户明确提到"背景音乐"、"BGM"时才设为 true

只输出 JSON，不要有其他文字。
"""
        return prompt

    def _parse_llm_output(self, content: str) -> Dict[str, Any]:
        """解析 LLM 输出为字典"""
        import json
        import re

        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 如果解析失败，返回默认值
        return {
            "goal": "plant",
            "style": "活泼",
            "keywords": [],
            "must_include": [],
            "image_style": "摄影实拍",
            "need_video": False,
            "need_voiceover": False,
            "need_text": True,
            "need_images": True,
            "need_bgm": False,
            "bgm_preference": "轻快",
            "target_audience": "",
        }

    def _build_materials(self, analyzed_materials: List[Dict[str, Any]]) -> List[Material]:
        """构建 Material 对象列表"""
        materials = []
        for i, mat in enumerate(analyzed_materials):
            material = Material(
                material_id=f"mat_{uuid.uuid4().hex[:8]}",
                material_type=mat.get("type", "unknown"),
                url=mat.get("url"),
                content=mat.get("content"),
                description=mat.get("analysis", {}).get("product_info", {}).get("visual_description"),
            )
            materials.append(material)
        return materials

    def _validate_brief(self, brief: Brief) -> List[str]:
        """验证 Brief，返回警告列表"""
        warnings = []

        if not brief.keywords:
            warnings.append("未提取到关键词，可能影响内容相关性")

        if brief.need_video and not brief.need_voiceover:
            warnings.append("视频内容建议添加配音以提升吸引力")

        if brief.style == "专业" and brief.need_video:
            warnings.append("专业风格视频可能需要更正式的配音风格")

        return warnings
