"""
Critic - 审核反馈 Agent

参考 plan.md:
- 审核与迭代 Agent (Critic)
- 内置小红书内容规范检查（敏感词、夸大词、违禁词）
- 美学评分（图文匹配度、标题吸引力）
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config.studio_config import StudioConfig
from ..models.brief import Brief
from ..models.content_item import ContentItem, ContentType
from ..models.content_plan import ContentPlan
from ..debug_logger import get_logger, get_workflow_logger

# 获取日志记录器
logger = get_logger("critic")

# 导入 agent 模块的请求类
from agent.models.llm_gateway import LLMRequest


@dataclass
class CritiqueResult:
    """审核结果"""
    passed: bool
    score: float  # 0.0 - 1.0
    issues: List[Dict[str, Any]]  # [{"type": "sensitive_word", "severity": "high/medium/low", "item_id": "...", "message": "..."}]
    suggestions: List[str]  # 改进建议
    overall_comment: str  # 总体评价


@dataclass
class UserFeedback:
    """用户反馈"""
    feedback_id: str
    user_input: str
    parsed_intent: Dict[str, Any] = None
    target_item_ids: List[str] = None  # 要修改的内容项 ID


class Critic:
    """
    审核反馈 Agent

    职责：
    1. 内容合规检查（敏感词、违禁词、夸大词）
    2. 质量评分（标题吸引力、图文匹配度）
    3. 解析用户反馈意图
    4. 生成修改建议
    """

    # 敏感词/违禁词模式（简化版，实际应接入词库）
    SENSITIVE_PATTERNS = [
        r"最[一第一]/.{0,2}?(好|棒|佳)",
        r"100%/分[百之]比",
        r"保证.*?(治愈|根除|完全)",
        r"[质]量.*?(问题|差|不行)",
        r"用了.*?(死|毁|烂)",
    ]

    def __init__(self, llm_gateway=None, config: StudioConfig = None):
        """
        初始化 Critic

        Args:
            llm_gateway: LLM 网关实例（用于 AI 评分）
            config: Studio 配置
        """
        self.llm_gateway = llm_gateway
        self.config = config or StudioConfig()

    async def critique(
        self,
        brief: Brief,
        plan: ContentPlan,
        items: List[ContentItem],
    ) -> CritiqueResult:
        """
        审核内容

        Args:
            brief: Brief 对象
            plan: ContentPlan 对象
            items: 内容项列表

        Returns:
            CritiqueResult: 审核结果
        """
        wf_logger = get_workflow_logger("critic.critique")
        wf_logger.start("critique")
        logger.debug(f"Critiquing {len(items)} items...")

        issues = []
        suggestions = []

        # 1. 合规检查
        logger.debug("Checking compliance...")
        wf_logger.start("_check_compliance")
        compliance_issues = self._check_compliance(items)
        wf_logger.end("_check_compliance", success=True, message=f"issues={len(compliance_issues)}")
        logger.debug(f"Compliance issues found: {len(compliance_issues)}")
        issues.extend(compliance_issues)

        # 2. 质量评分
        logger.debug("Scoring quality...")
        wf_logger.start("_score_quality")
        quality_score = await self._score_quality(brief, plan, items)
        wf_logger.end("_score_quality", success=True, message=f"score={quality_score:.2f}")
        logger.debug(f"Quality score: {quality_score:.2f}")

        # 3. 生成建议
        if issues:
            suggestions = self._generate_suggestions(issues, items)

        # 4. 总体评价
        passed = len([i for i in issues if i.get("severity") == "high"]) == 0
        overall_comment = self._generate_comment(passed, quality_score, issues)

        logger.info(f"Critique completed: passed={passed}, score={quality_score:.2f}, issues={len(issues)}")
        wf_logger.end("critique", success=True, message=f"passed={passed}, score={quality_score:.2f}")

        return CritiqueResult(
            passed=passed,
            score=quality_score,
            issues=issues,
            suggestions=suggestions,
            overall_comment=overall_comment,
        )

    def _check_compliance(self, items: List[ContentItem]) -> List[Dict[str, Any]]:
        """检查内容合规"""
        issues = []

        for item in items:
            if item.item_type not in [ContentType.TEXT, ContentType.HEADLINE, ContentType.TITLE]:
                continue

            content = item.content

            # 检查违禁词
            for pattern in self.SENSITIVE_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    issues.append({
                        "type": "sensitive_word",
                        "severity": "high",
                        "item_id": item.item_id,
                        "matched_pattern": pattern,
                        "matched_text": str(matches),
                        "message": f"检测到疑似违禁/夸大词: {matches}",
                    })

            # 检查特殊字符
            if re.search(r"[^\u4e00-\u9fa5a-zA-Z0-9\s,.!?~，。！？、]", content):
                issues.append({
                    "type": "special_characters",
                    "severity": "low",
                    "item_id": item.item_id,
                    "message": "包含特殊字符，建议清理",
                })

        # 检查配置的违禁词
        if self.config.prohibited_words:
            for item in items:
                for word in self.config.prohibited_words:
                    if word in item.content:
                        issues.append({
                            "type": "prohibited_word",
                            "severity": "high",
                            "item_id": item.item_id,
                            "word": word,
                            "message": f"包含违禁词: {word}",
                        })

        return issues

    async def check_image_text_alignment(
        self,
        brief: Brief,
        items: List[ContentItem],
    ) -> List[Dict[str, Any]]:
        """检查文案与图片的一致性"""
        issues = []

        # 收集文本和图片
        text_items = [item for item in items if item.item_type in [
            ContentType.TEXT, ContentType.TITLE, ContentType.HEADLINE
        ]]
        image_items = [item for item in items if item.item_type == ContentType.IMAGE]

        if not text_items or not image_items:
            return issues

        all_text = "\n".join([item.content for item in text_items if item.content])
        image_urls = [img.content for img in image_items if img.content]

        if not self.llm_gateway:
            return issues

        prompt = f"""分析以下小红书文案和图片之间的匹配度：

文案内容：
{all_text[:800]}

图片URL：
{', '.join(image_urls)}

请检查：
1. 文案中描述的产品特征（颜色、形状、材质等）是否与图片一致
2. 文案中提到的数量是否与图片数量匹配
3. 风格描述是否与实际图片风格匹配

请以 JSON 格式输出：
{{
    "aligned": true/false,
    "issues": [
        {{
            "severity": "high/medium/low",
            "description": "问题描述",
            "suggestion": "修改建议"
        }}
    ]
}}

只输出 JSON。
"""

        try:
            llm_request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
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
                    if not data.get("aligned", True):
                        for issue in data.get("issues", []):
                            issues.append({
                                "type": "image_text_mismatch",
                                "severity": issue.get("severity", "medium"),
                                "message": issue.get("description", ""),
                                "suggestion": issue.get("suggestion", ""),
                            })
        except Exception:
            pass

        return issues

    async def _score_quality(
        self,
        brief: Brief,
        plan: ContentPlan,
        items: List[ContentItem],
    ) -> float:
        """
        AI 质量评分

        Returns:
            float: 质量分数 0.0 - 1.0
        """
        if not self.llm_gateway:
            return 0.7  # 默认分数

        # 收集所有文本内容
        text_items = [item for item in items if item.item_type in [ContentType.TEXT, ContentType.TITLE, ContentType.HEADLINE]]
        all_text = "\n".join([item.content for item in text_items if item.content])

        prompt = f"""请为以下小红书文案评分（0-10分），考虑：
1. 标题吸引力（是否引发好奇心）
2. 内容质量（是否有趣、有价值）
3. 关键词覆盖（是否包含关键卖点）
4. 小红书风格（是否适合平台调性）

文案内容：
{all_text[:1000]}

风格要求: {brief.style}
关键词: {', '.join(brief.keywords)}

请以 JSON 格式输出：
{{
    "title_score": 标题分数(0-10),
    "content_score": 内容分数(0-10),
    "keyword_score": 关键词分数(0-10),
    "overall_score": 综合分数(0-10),
    "reasoning": "评分理由"
}}

只输出 JSON。
"""

        try:
            llm_request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
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
                    # 转换为 0-1 分数
                    return data.get("overall_score", 7) / 10.0

        except Exception:
            pass

        return 0.7  # 默认分数

    def _generate_suggestions(
        self,
        issues: List[Dict[str, Any]],
        items: List[ContentItem],
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []

        high_severity = [i for i in issues if i.get("severity") == "high"]
        if high_severity:
            suggestions.append("存在高严重性问题，建议优先处理")

        for issue in high_severity:
            if issue.get("type") == "sensitive_word":
                suggestions.append(f"文案「{issue.get('item_id')}」包含疑似夸大词，请修改")
            elif issue.get("type") == "prohibited_word":
                suggestions.append(f"文案「{issue.get('item_id')}」包含违禁词「{issue.get('word')}」，必须修改")

        medium_severity = [i for i in issues if i.get("severity") == "medium"]
        if medium_severity:
            suggestions.append(f"存在 {len(medium_severity)} 个中等问题，建议适当优化")

        return suggestions

    def _generate_comment(
        self,
        passed: bool,
        score: float,
        issues: List[Dict[str, Any]],
    ) -> str:
        """生成总体评价"""
        if not passed:
            high_count = len([i for i in issues if i.get("severity") == "high"])
            return f"内容未通过审核，存在 {high_count} 个高严重性问题，需要修改后才能发布。"

        if score >= 0.8:
            return "内容质量优秀，符合小红书风格，可以发布。"
        elif score >= 0.6:
            return "内容质量良好，有少量优化空间。"
        else:
            return "内容质量一般，建议根据反馈优化后发布。"

    async def parse_feedback(
        self,
        user_input: str,
        items: List[ContentItem],
    ) -> UserFeedback:
        """
        解析用户反馈

        Args:
            user_input: 用户原始反馈
            items: 当前内容项列表

        Returns:
            UserFeedback: 结构化的用户反馈
        """
        if not self.llm_gateway:
            # 简单解析
            return UserFeedback(
                feedback_id=f"fb_{len(items)}",
                user_input=user_input,
                parsed_intent={"type": "general", "description": user_input},
                target_item_ids=[],
            )

        # 构建 item 列表供 LLM 参考
        item_list = "\n".join([
            f"- {item.item_id}: [{item.item_type.value}] {item.content[:50]}..."
            for item in items if item.content
        ])

        prompt = f"""分析用户反馈，识别要修改的内容项。

用户反馈：{user_input}

当前内容项：
{item_list}

请以 JSON 格式输出：
{{
    "feedback_id": "唯一ID",
    "intent_type": "modify_title/modify_text/modify_image/modify_all/general",
    "target_item_ids": ["要修改的item_id列表"],
    "modification_request": "具体的修改要求",
    "priority": "high/medium/low"
}}

只输出 JSON。
"""

        try:
            llm_request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
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
                    return UserFeedback(
                        feedback_id=data.get("feedback_id", f"fb_{len(items)}"),
                        user_input=user_input,
                        parsed_intent={
                            "type": data.get("intent_type", "general"),
                            "request": data.get("modification_request", user_input),
                            "priority": data.get("priority", "medium"),
                        },
                        target_item_ids=data.get("target_item_ids", []),
                    )

        except Exception:
            pass

        return UserFeedback(
            feedback_id=f"fb_{len(items)}",
            user_input=user_input,
            parsed_intent={"type": "general", "description": user_input},
            target_item_ids=[],
        )

    async def ask_clarification(
        self,
        feedback: str,
        items: List[ContentItem],
    ) -> Dict[str, Any]:
        """
        当反馈模糊时，主动向用户询问澄清

        Args:
            feedback: 用户反馈文本
            items: 当前内容项列表

        Returns:
            Dict containing:
                - needs_clarification: bool
                - questions: List[str] 澄清问题列表
                - suggested_actions: List[str] 建议操作列表
        """
        logger.debug(f"ask_clarification called with feedback: {feedback[:50]}...")

        # 模糊反馈的触发条件
        vague_patterns = [
            "不够吸引人",
            "改改",
            "再改改",
            "再来",
            "重新",
            "随便",
        ]

        needs_clarification = any(pattern in feedback for pattern in vague_patterns)

        if not needs_clarification:
            return {
                "needs_clarification": False,
                "questions": [],
                "suggested_actions": [],
            }

        # 生成澄清问题和建议操作
        questions = []
        suggested_actions = []

        # 根据反馈内容生成具体问题
        if "不够吸引人" in feedback:
            questions.extend([
                "您希望标题更有冲击力还是更有趣味性？",
                "您希望文案风格更接地气还是更专业？",
            ])
            suggested_actions.extend(["更活泼", "更专业", "更有冲击力", "更有悬念感"])

        if "改改" in feedback or "再改改" in feedback:
            questions.append("您希望改成什么风格？")
            if "标题" in feedback:
                questions.append("您希望标题体现什么卖点？")
                suggested_actions.extend(["突出价格优势", "突出使用体验", "突出产品特色"])
            elif "图" in feedback or "图片" in feedback:
                questions.append("您希望图片呈现什么风格？")
                suggested_actions.extend(["小清新风格", "高级感", "生活化场景"])
            else:
                suggested_actions.extend(["更简洁", "更详细", "更口语化", "更书面化"])

        if "再来" in feedback:
            questions.append("您希望再次生成什么样的内容？")
            suggested_actions.extend(["更大胆", "更保守", "更新颖", "更常规"])

        if "重新" in feedback:
            questions.append("您希望重新生成哪些部分？")
            suggested_actions.extend(["保留框架只改内容", "完全重新生成", "保留核心卖点"])

        if "随便" in feedback:
            questions.append("您有偏好的风格吗？比如种草/测评/教程类？")
            suggested_actions.extend(["种草风格", "测评风格", "教程风格", "故事风格"])

        # 去重并限制问题数量
        questions = list(dict.fromkeys(questions))[:3]

        logger.info(f"Clarification needed: {len(questions)} questions generated")

        return {
            "needs_clarification": True,
            "questions": questions,
            "suggested_actions": suggested_actions,
        }
