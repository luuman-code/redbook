"""
工具定义 - 小红书 Agent 工具集

每个工具都遵循 mini_agent.tools.base.Tool 接口：
- name: str - 工具名称
- description: str - 工具描述
- parameters: dict - JSON Schema 格式的参数定义
- execute(): 异步方法，返回 ToolResult
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mini_agent.tools.base import Tool, ToolResult

from ..core.orchestrator import Orchestrator
from ..models.session import Session, SessionStatus

logger = logging.getLogger(__name__)


class ToolResult:
    """工具执行结果"""
    def __init__(self, success: bool, content: str = "", error: str = ""):
        self.success = success
        self.content = content
        self.error = error


class AnalyzeTemplateTool(Tool):
    """分析文案模板工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "analyze_template"

    @property
    def description(self) -> str:
        return """分析文案模板图片，提取文案结构、风格特点和格式特征。

当用户上传了文案模板图片（即使是隐含的意图），使用此工具分析模板特点。

【重要】此工具会自动获取用户当前上传的图片素材，不需要传入任何参数！

此工具会：
1. 自动使用视觉模型分析用户上传的模板图片
2. 提取文案结构（标题格式、分段方式、标签使用等）
3. 分析风格特点（活泼/专业/治愈等）
4. 返回结构化的模板分析结果，供后续创作参考"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self,
        materials: List[Dict[str, Any]] = None,
    ) -> ToolResult:
        try:
            # 总是尝试从 orchestrator._agent._current_materials 获取图片
            agent_instance = getattr(self.orchestrator, '_agent', None)
            if agent_instance is not None:
                agent_materials = getattr(agent_instance, '_current_materials', None)
                if agent_materials and len(agent_materials) > 0:
                    materials = agent_materials

            if not materials:
                return ToolResult(success=False, error="没有提供模板图片")

            # 使用 orchestrator 的 llm_gateway (多模态模型) 分析图片
            llm_gateway = getattr(self.orchestrator, 'llm_gateway', None)
            if not llm_gateway:
                return ToolResult(success=False, error="LLM 服务不可用")

            logger.info(f"[AnalyzeTemplateTool] 开始分析图片")
            template_analysis = []
            for mat in materials:
                if mat.get("type") == "image":
                    image_content = mat.get("content") or mat.get("url", "")

                    # 构建多模态消息
                    prompt = """请详细分析这张小红书文案图片，提取以下信息：

1. **文案结构**：
   - 标题格式（emoji开头/疑问句/感叹句等）
   - 正文分段方式（每段长度、段落数量）
   - 标签使用（#话题 格式、位置）

2. **风格特点**：
   - 整体语气（活泼/专业/治愈/搞笑等）
   - emoji使用频率和风格
   - 排版特点（空行、特殊符号等）

3. **格式特征**：
   - 每段大约多少字
   - 是否有特殊排版（引用、列表等）
   - 图片数量和位置

请用 JSON 格式返回分析结果。"""

                    # 构建多模态消息 (DashScope 格式)
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"image": image_content},
                                {"text": prompt}
                            ]
                        }
                    ]

                    try:
                        # 调用 LLM 多模态接口
                        from agent.models.llm_gateway import LLMRequest
                        request = LLMRequest(messages=messages, tools=None)
                        response = await llm_gateway.invoke(request)

                        if response.success:
                            content = response.data.get("content", "") if response.data else ""
                            template_analysis.append({
                                "url": mat.get("url", ""),
                                "analysis": content,
                            })
                        else:
                            logger.warning(f"[AnalyzeTemplateTool] LLM API 调用失败: {response.error}")
                    except Exception as e:
                        logger.warning(f"[AnalyzeTemplateTool] LLM 调用异常: {e}")

            logger.info(f"[AnalyzeTemplateTool] 分析完成，共 {len(template_analysis)} 个模板")
            if not template_analysis:
                return ToolResult(success=False, error="没有找到可分析的模板图片")

            # 保存分析结果到 agent 上下文，供后续 create_session 使用
            if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                self.orchestrator._agent._current_template_analysis = template_analysis
                logger.debug(f"保存模板分析结果到 agent 上下文")

            return ToolResult(
                success=True,
                content=json.dumps({
                    "template_count": len(template_analysis),
                    "template_analysis": template_analysis,
                    "message": "模板分析完成，可以继续创建会话"
                }, ensure_ascii=False),
            )
        except Exception as e:
            logger.error(f"AnalyzeTemplateTool exception: {e}", exc_info=True)
            return ToolResult(success=False, error=f"模板分析异常: {str(e)}")


class CreateSessionTool(Tool):
    """创建会话工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "create_session"

    @property
    def description(self) -> str:
        return """创建新的创作会话。

当用户提供新的内容需求或想要开始新的创作任务时使用此工具。

输入：
- user_input: 用户的原始需求描述，如"我想推广我的蓝牙耳机"
- materials: 可选的素材列表，如参考图片、产品图片等

此工具会自动：
1. 解析用户需求，提取内容目标、风格、关键词等
2. 如果有模板图片，会分析并套用模板风格生成内容
3. 生成包含文案结构、配图方案的内容方案
4. 创建会话并保存到存储中"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "user_input": {
                    "type": "string",
                    "description": "用户的原始需求描述",
                },
                "materials": {
                    "type": "array",
                    "description": "素材列表，每个素材包含 type/url/content",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["image", "video", "text"]},
                            "url": {"type": "string"},
                            "content": {"type": "string"},
                        }
                    }
                },
            },
            "required": ["user_input"],
        }

    async def execute(
        self,
        user_input: str,
        materials: Optional[List[Dict]] = None,
    ) -> ToolResult:
        try:
            # 检查是否有现有会话，如果有则复用其 session_id
            existing_session_id = None
            if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                current_session = getattr(self.orchestrator._agent, '_current_session', None)
                if current_session is not None:
                    existing_session_id = current_session.session_id

            # 如果没有传入 materials，尝试从 agent 上下文获取
            final_materials = materials if materials else []
            if not final_materials and hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                agent_materials = getattr(self.orchestrator._agent, '_current_materials', None)
                if agent_materials:
                    final_materials = agent_materials
                    logger.debug(f"Using materials from agent context: {len(final_materials)} items")
        
            # 检查是否有模板分析结果（由 Agent 调用 analyze_template 工具生成）
            template_analysis = None
            if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                template_analysis = getattr(self.orchestrator._agent, '_current_template_analysis', None)
                if template_analysis:
                    logger.debug(f"Found template analysis: {len(template_analysis)} items")
                    # 清除模板分析，避免下次复用
                    self.orchestrator._agent._current_template_analysis = None

            # 准备额外参数
            extra_kwargs = {}
            if template_analysis:
                extra_kwargs['template_analysis'] = template_analysis

            result = await self.orchestrator.create_session(
                user_input=user_input,
                materials=final_materials,
                session_id=existing_session_id,
                **extra_kwargs,
            )

            if result.success and result.session:
                session = result.session
                # 更新 agent._current_session 指向新创建的 session（包含 current_plan）
                # 这样后续 agent.chat() 返回时可以正确传递 plan 信息
                if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                    self.orchestrator._agent._current_session = session
                    logger.debug(f"Updated agent._current_session to new session with current_plan")
                # 获取完整的 plan 数据结构（与前端 UI 模式一致）
                plan_data = session.current_plan.to_dict() if hasattr(session.current_plan, 'to_dict') else dict(session.current_plan)
                # 调试日志
                print(f"[CreateSessionTool] session_id={session.session_id}, plan.title={plan_data.get('title')}, plan.sections_count={len(plan_data.get('text_sections', []))}")
                # 序列化的 plan_data 用于工具返回
                plan_data_json = json.dumps(plan_data, ensure_ascii=False)
                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "session_id": session.session_id,
                        "status": session.status.value,
                        "brief_summary": {
                            "goal": session.brief.goal.value if hasattr(session.brief.goal, 'value') else str(session.brief.goal),
                            "style": session.brief.style,
                            "keywords": session.brief.keywords,
                        },
                        "plan_data": plan_data,  # 完整方案数据，与前端 UI 模式一致
                        "plan_data_json": plan_data_json,  # 序列化的纯字符串格式，方便 LLM 保留
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=f"创建会话失败: {result.error}")
        except Exception as e:
            return ToolResult(success=False, error=f"创建会话异常: {str(e)}")


class GenerateContentTool(Tool):
    """生成内容工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "generate_content"

    @property
    def description(self) -> str:
        return """执行内容生成。

根据已确认的内容方案，生成实际的文案、配图、视频、音频等内容。

【重要】如果用户上传了文案模板图片，此工具会：
1. 首先生成新的文案内容
2. 然后自动将新文案替换到模板图片上
3. 生成一张包含新文案的最终成品图

输入：
- session_id: 会话 ID（必须使用 create_session 工具创建）

前置条件：会话状态必须为 CONFIRMED"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID",
                },
            },
            "required": ["session_id"],
        }

    async def execute(self, session_id: str) -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            if session.status != SessionStatus.CONFIRMED:
                return ToolResult(
                    success=False,
                    error=f"状态错误：当前状态为 {session.status.value}，需要 CONFIRMED",
                )

            result = await self.orchestrator.generate(session)

            if result.success:
                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "items_count": len(session.items),
                        "status": session.status.value,
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=f"生成失败: {result.error}")
        except Exception as e:
            return ToolResult(success=False, error=f"生成异常: {str(e)}")


class ReviewContentTool(Tool):
    """审核内容工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "review_content"

    @property
    def description(self) -> str:
        return """审核生成的内容。

检查内容是否符合规范，评估质量，并提供改进建议。

输入：
- session_id: 会话 ID"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID",
                },
            },
            "required": ["session_id"],
        }

    async def execute(self, session_id: str) -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            result = await self.orchestrator.review(session)

            if result.success:
                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "passed": True,
                        "status": session.status.value,
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=f"审核失败: {result.error}")
        except Exception as e:
            return ToolResult(success=False, error=f"审核异常: {str(e)}")


class IterateContentTool(Tool):
    """迭代修改工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "iterate_content"

    @property
    def description(self) -> str:
        return """根据用户反馈迭代修改内容。

当用户对生成的内容提出修改意见时，使用此工具执行修改。

输入：
- session_id: 会话 ID
- user_feedback: 用户的修改意见，如"标题不够吸引人，换一个更有趣的"

此工具会：
1. 解析用户反馈，确定修改目标
2. 只修改受影响的内容项，保留其他部分

返回：
- iteration_count: 迭代轮次
- status: 会话状态
- current_version: 当前版本号
- brief_summary: Brief 需求摘要（goal, style）
- plan_summary: 方案摘要（title, sections_count）
- modified_items: 修改的内容项列表
- plan_data: 完整的方案数据

【重要】此工具返回结果已包含所有会话状态信息，**不需要再调用 get_session** 来确认会话状态。

【重要】此工具**只修改文本内容，不会生成新的模板预览图**！
修改文本后，必须调用 `generate_template` 工具（使用会话中存储的模板图片）来生成新的预览图。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "会话 ID"},
                "user_feedback": {"type": "string", "description": "用户的修改反馈"},
                "template_image_url": {"type": "string", "description": "模板图片 URL（可选）"},
                "backup_template_image_url": {
                    "type": "string",
                    "description": "模板图片 URL 的后备值（由系统自动注入）",
                },
                "title": {"type": "string", "description": "标题（可选）"},
                "backup_title": {
                    "type": "string",
                    "description": "标题的后备值（由系统自动注入）",
                },
                "text_sections": {
                    "type": "array",
                    "description": "文案内容（可选）",
                },
                "backup_text_sections": {
                    "type": "array",
                    "description": "文案内容的后备值（由系统自动注入）",
                },
            },
            "required": ["session_id", "user_feedback"],
        }

    async def execute(
        self,
        session_id: str,
        user_feedback: str,
        template_image_url: Optional[str] = None,
        backup_template_image_url: Optional[str] = None,
        title: Optional[str] = None,
        backup_title: Optional[str] = None,
        text_sections: Optional[List[dict]] = None,
        backup_text_sections: Optional[List[dict]] = None,
    ) -> ToolResult:
        try:
            # 双重赋值：先用传入参数，再用 backup 参数覆盖（保证正确）
            if backup_template_image_url is not None:
                template_image_url = backup_template_image_url

            if backup_title is not None:
                title = backup_title

            if backup_text_sections is not None:
                text_sections = backup_text_sections

            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            result = await self.orchestrator.iterate(session, user_feedback)

            if result.success:
                # 收集修改后的内容项信息
                modified_items_data = []
                for item in result.modified_items:
                    modified_items_data.append({
                        "item_id": item.item_id,
                        "content_type": item.content_type.value if hasattr(item.content_type, 'value') else str(item.content_type),
                        "title": getattr(item, 'title', ''),
                        "content": getattr(item, 'content', ''),
                    })

                # 获取当前方案数据
                plan_data = None
                if session.current_plan and hasattr(session.current_plan, 'to_dict'):
                    plan_data = session.current_plan.to_dict()
                    # 【重要】同步更新 session.current_plan.text_sections 中对应 item 的 content
                    # 这样 generate_template_preview 就能使用修改后的内容
                    if hasattr(session.current_plan, 'text_sections') and result.modified_items:
                        for item in result.modified_items:
                            for section in session.current_plan.text_sections:
                                if section.section_id == item.item_id or (hasattr(section, 'item_id') and getattr(section, 'item_id', None) == item.item_id):
                                    section.content = item.content
                                    break
                    # 同步更新 text_sections 中对应 item 的 content（用于返回给 Agent）
                    if "text_sections" in plan_data and result.modified_items:
                        section_map = {s.get("section_id") or s.get("item_id"): s for s in plan_data.get("text_sections", [])}
                        for item in result.modified_items:
                            section = section_map.get(item.item_id)
                            if section:
                                section["content"] = item.content
                    # 同时更新 items 列表
                    plan_data["items"] = modified_items_data
                elif session.current_plan:
                    plan_data = dict(session.current_plan)
                    plan_data["items"] = modified_items_data
                else:
                    plan_data = {"items": modified_items_data}

                # 【重要】如果会话有模板图片，生成新的预览图
                preview_image_url = None
                preview_title = None
                preview_text_sections = None
                if session.brief and hasattr(session.brief, 'template_image_url') and session.brief.template_image_url:
                    try:
                        # 使用 session 中的模板图片生成预览
                        preview_result = await self.orchestrator.generate_template_preview(session, store)
                        if preview_result.get("success"):
                            preview_image_url = preview_result.get("preview_image_url")
                            preview_title = preview_result.get("title", "")
                            preview_text_sections = preview_result.get("text_sections", [])
                            # 将预览图 URL 保存到 session metadata
                            if preview_image_url:
                                session.metadata = session.metadata or {}
                                session.metadata['preview_image_url'] = preview_image_url
                                session.metadata['preview_title'] = preview_title
                                session.metadata['preview_text_sections'] = preview_text_sections
                                await store.save(session)
                    except Exception as e:
                        logger.warning(f"[IterateContent] 生成预览图失败: {e}")

                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "iteration_count": result.iteration_count,
                        "status": session.status.value,
                        "current_version": session.current_version,
                        "brief_summary": {
                            "goal": session.brief.goal.value if hasattr(session.brief.goal, 'value') else str(session.brief.goal),
                            "style": session.brief.style,
                        },
                        "plan_summary": {
                            "title": session.current_plan.title if session.current_plan else "",
                            "sections_count": len(session.current_plan.text_sections) if session.current_plan else 0,
                        },
                        "modified_items": modified_items_data,
                        "plan_data": plan_data,
                        "preview_image_url": preview_image_url,  # 新增预览图 URL
                        "preview_title": preview_title,
                        "preview_text_sections": preview_text_sections,
                        "message": f"已完成第 {result.iteration_count} 轮迭代，修改了 {len(result.modified_items)} 项内容",
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=f"迭代失败: {result.error}")
        except Exception as e:
            return ToolResult(success=False, error=f"迭代异常: {str(e)}")


class RegeneratePlansTool(Tool):
    """根据用户反馈重新生成方案工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "regenerate_plans"

    @property
    def description(self) -> str:
        return """根据用户反馈重新生成多个完整方案。

当用户对当前方案有较大修改需求时（如风格不对、结构不满意、配图不合适），
使用此工具重新生成方案，而不是修改单个内容项。

此工具会：
1. 结合原始 Brief 和用户反馈生成新的方案
2. 生成 3 个不同风格的备选方案
3. 每个方案包含：标题、正文结构、配图计划

输入：
- session_id: 会话 ID
- user_feedback: 用户的修改需求，如"换成更年轻化有趣的风格"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID",
                },
                "user_feedback": {
                    "type": "string",
                    "description": "用户的修改需求/反馈",
                },
            },
            "required": ["session_id", "user_feedback"],
        }

    async def execute(self, session_id: str, user_feedback: str) -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            # 调用 orchestrator 的 regenerate_plans 方法
            result = await self.orchestrator.regenerate_plans(session, user_feedback)

            if result.success:
                # 返回多个方案（完整结构，与前端 UI 模式一致）
                plans_data = result.plans  # 已经是完整的 to_dict() 数据

                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "status": session.status.value,
                        "message": f"已根据你的反馈重新生成 {len(plans_data)} 个方案",
                        "plans": plans_data,
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=f"生成方案失败: {result.error}")
        except Exception as e:
            return ToolResult(success=False, error=f"生成方案异常: {str(e)}")


class PublishContentTool(Tool):
    """发布内容工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "publish_content"

    @property
    def description(self) -> str:
        return """发布内容或导出素材包。

在内容审核通过后，执行发布流程。

输入：
- session_id: 会话 ID
- method: 发布方式 (simulate/export/api)

前置条件：内容必须通过审核"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID",
                },
                "method": {
                    "type": "string",
                    "enum": ["simulate", "export", "api"],
                    "description": "发布方式",
                    "default": "simulate",
                },
            },
            "required": ["session_id"],
        }

    async def execute(self, session_id: str, method: str = "simulate") -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            result = await self.orchestrator.publish(session)

            if result.success:
                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "success": True,
                        "method": method,
                        "status": session.status.value,
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=f"发布失败: {result.error}")
        except Exception as e:
            return ToolResult(success=False, error=f"发布异常: {str(e)}")


class GetSessionTool(Tool):
    """获取会话状态工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "get_session"

    @property
    def description(self) -> str:
        return """获取会话的当前状态和内容。

输入：
- session_id: 会话 ID

返回：
- 会话 ID 和状态
- Brief 需求摘要
- 内容方案摘要
- 已生成的内容项列表"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID",
                },
            },
            "required": ["session_id"],
        }

    async def execute(self, session_id: str) -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            items_summary = []
            for item in session.items:
                items_summary.append({
                    "item_id": item.item_id,
                    "type": item.item_type.value if hasattr(item.item_type, 'value') else str(item.item_type),
                    "content_preview": item.content[:100] + "..." if item.content and len(item.content) > 100 else item.content,
                })

            return ToolResult(
                success=True,
                content=json.dumps({
                    "session_id": session.session_id,
                    "status": session.status.value,
                    "current_version": session.current_version,
                    "brief_summary": {
                        "goal": session.brief.goal.value if hasattr(session.brief.goal, 'value') else str(session.brief.goal),
                        "style": session.brief.style,
                    },
                    "plan_summary": {
                        "title": session.current_plan.title,
                        "sections_count": len(session.current_plan.text_sections),
                    },
                    "items": items_summary,
                }, ensure_ascii=False),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"获取会话异常: {str(e)}")


class ModifyPlanTool(Tool):
    """统一方案工具：解析需求+生成方案+修改方案"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "modify_plan"

    @property
    def description(self) -> str:
        return """统一的内容方案工具，支持解析需求生成方案和修改现有方案。

【场景1】新需求 - 创建会话并生成方案：
当用户提供新的内容需求或想要开始新的创作任务时使用。
输入：user_input（用户需求描述）、materials（可选的素材列表）

【场景2】修改需求 - 根据反馈修改方案：
当用户对当前方案有具体修改需求时（如"标题更活泼一点"、"风格改成治愈系"）。
输入：session_id、user_feedback（修改需求）

此工具会自动：
1. 解析用户需求，提取内容目标、风格、关键词等
2. 如果有模板图片，会分析并套用模板风格
3. 生成包含文案结构、配图方案的内容方案
4. 如有修改需求，基于原方案调整生成新方案
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID（修改方案时必填，新需求可不填）",
                },
                "user_input": {
                    "type": "string",
                    "description": "用户的原始需求描述，如'我想推广我的蓝牙耳机'（新需求时必填）",
                },
                "user_feedback": {
                    "type": "string",
                    "description": "用户的修改需求，如'把标题改得更活泼'（修改方案时使用）",
                },
                "materials": {
                    "type": "array",
                    "description": "素材列表，如参考图片、产品图片等（新需求时使用）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["image", "video", "text"]},
                            "url": {"type": "string"},
                            "content": {"type": "string"},
                        }
                    }
                },
            },
        }

    async def execute(
        self,
        session_id: str = None,
        user_input: str = None,
        user_feedback: str = None,
        materials: List[Dict] = None,
    ) -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()

            # 如果没有传入 session_id，尝试从 agent 上下文获取当前会话
            if not session_id:
                agent_session = getattr(self.orchestrator, '_agent', None) and getattr(self.orchestrator._agent, '_current_session', None)
                if agent_session:
                    session_id = agent_session.session_id
                    logger.debug(f"Using session_id from agent context: {session_id}")

            # 如果没有传入 materials，从 agent 上下文获取
            if not materials:
                agent_materials = getattr(self.orchestrator, '_agent', None) and getattr(self.orchestrator._agent, '_current_materials', None)
                if agent_materials:
                    materials = agent_materials
                    logger.debug(f"Using materials from agent context: {len(materials)} items")

            # 场景1：新需求 - 解析需求并生成方案
            if user_input and not user_feedback:
                # 检查是否有模板分析结果（由 Agent 调用 analyze_template 工具生成）
                template_analysis = None
                if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                    template_analysis = getattr(self.orchestrator._agent, '_current_template_analysis', None)
                    if template_analysis:
                        # 清除模板分析，避免下次复用
                        self.orchestrator._agent._current_template_analysis = None

                # 准备额外参数
                extra_kwargs = {}
                if template_analysis:
                    extra_kwargs['template_analysis'] = template_analysis

                # 使用 orchestrator 创建会话和生成方案
                result = await self.orchestrator.create_session(
                    user_input=user_input,
                    materials=materials or [],
                    session_id=session_id,
                    auto_generate=False,
                    **extra_kwargs,
                )

                if result.success and result.session:
                    session = result.session
                    # 安全地获取 plan_data，处理 current_plan 是 dict 或 ContentPlan 的情况
                    if session.current_plan is None:
                        plan_data = None
                    elif isinstance(session.current_plan, dict):
                        plan_data = session.current_plan
                    elif hasattr(session.current_plan, "to_dict"):
                        plan_data = session.current_plan.to_dict()
                    else:
                        plan_data = dict(session.current_plan)

                    # 获取 template_image_url
                    template_image_url = None
                    if session.brief and hasattr(session.brief, 'template_image_url'):
                        template_image_url = session.brief.template_image_url
                    elif session.brief and isinstance(session.brief, dict):
                        template_image_url = session.brief.get('template_image_url')

                    return ToolResult(
                        success=True,
                        content=json.dumps({
                            "session_id": session.session_id,
                            "status": session.status.value,
                            "message": "已根据你的需求生成方案",
                            "plan_data": plan_data,
                            "template_image_url": template_image_url,
                        }, ensure_ascii=False),
                    )
                else:
                    return ToolResult(success=False, error=f"生成方案失败: {result.error}")

            # 场景2：修改需求 - 根据反馈修改方案
            elif session_id and user_feedback:
                session = await store.get(session_id)
                if not session:
                    return ToolResult(success=False, error="会话不存在")

                # 调用 orchestrator 的 modify_plan 方法
                result = await self.orchestrator.modify_plan(session, user_feedback)

                if result.success and result.session:
                    # 更新 session 的 current_plan
                    updated_session = result.session
                    if updated_session.current_plan:
                        plan_data = updated_session.current_plan.to_dict() if hasattr(updated_session.current_plan, "to_dict") else updated_session.current_plan
                    else:
                        plan_data = None

                    return ToolResult(
                        success=True,
                        content=json.dumps({
                            "session_id": updated_session.session_id,
                            "status": updated_session.status.value,
                            "message": "已根据你的反馈修改方案",
                            "plan_data": plan_data,
                        }, ensure_ascii=False),
                    )
                else:
                    return ToolResult(success=False, error=f"修改方案失败: {result.error}")

            else:
                return ToolResult(success=False, error="参数错误：需要提供 user_input（新需求）或 session_id+user_feedback（修改方案）")

        except Exception as e:
            return ToolResult(success=False, error=f"方案处理异常: {str(e)}")


class GenerateTemplatePreviewTool(Tool):
    """生成文案模板预览工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "generate_template_preview"

    @property
    def description(self) -> str:
        return """生成文案模板预览图。

当用户想查看文案渲染到模板图片上的效果时使用此工具。

此工具会：
1. 检查当前会话是否有文案模板图片
2. 根据当前方案生成文案内容
3. 将文案渲染到模板图片上
4. 返回预览图供用户查看

输入：
- session_id: 会话 ID

注意：只有在有文案模板图片时才能生成预览。
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 ID",
                },
            },
            "required": ["session_id"],
        }

    async def execute(
        self,
        session_id: str,
    ) -> ToolResult:
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()
            session = await store.get(session_id)

            if not session:
                return ToolResult(success=False, error="会话不存在")

            # 调用 orchestrator 的 generate_template_preview 方法
            result = await self.orchestrator.generate_template_preview(session, session_store=store)

            if result.get("success"):
                return ToolResult(
                    success=True,
                    content=json.dumps({
                        "message": "已生成文案模板预览",
                        "preview_image_url": result.get("preview_image_url"),
                        "title": result.get("title", ""),
                        "text_sections": result.get("text_sections", []),
                    }, ensure_ascii=False),
                )
            else:
                return ToolResult(success=False, error=result.get("error", "生成预览失败"))
        except Exception as e:
            return ToolResult(success=False, error=f"生成预览异常: {str(e)}")


class GenerateTemplateTool(Tool):
    """
    整合的文案模板预览生成工具

    当用户想要生成文案模板预览时，调用此工具。
    """

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "generate_template"

    @property
    def description(self) -> str:
        return """生成文案模板预览图。

【重要前提】此工具**必须要有用户上传的模板图片**才能调用！

如果用户没有上传模板图片，**不要调用此工具**，而是提醒用户上传模板图片。

如果用户上传了模板图片，调用此工具，它会自动完成：
1. 根据用户需求生成文案内容
2. 将文案渲染到模板图片上
3. 返回预览图供用户查看

【重要】调用次数限制：
- **每个用户请求最多调用一次**
- 生成预览后必须将结果展示给用户
- 等待用户明确反馈后才能决定是否再次调用
- **禁止 Agent 自行判断并反复调用此工具**

输入：
- user_input: 用户的原始需求描述
- materials: 【必须】包含用户上传的模板图片（type="image"）

【重要】materials 参数的获取方式：
- **图片 URL 在用户消息的多模态内容中**，格式如：`{"image": "https://..."}`
- 从用户消息中提取图片 URL，构建 materials：`[{"type": "image", "url": "图片URL"}]`
- **不要从对话历史中搜索图片 URL**，只使用用户当前消息中的图片
- **不要自己编造图片 URL**

materials 参数说明：
- materials 是一个数组，每个元素是一个素材对象
- 对于图片素材，type="image"
- **优先传递 url 字段**（格式如：`{"type": "image", "url": "https://..."}`）
- 或者传递 **content 字段**（原始图片的 base64 数据，格式：`data:image/png;base64,...`）
- 注意：不要传递图片的分析结果、OCR 文本或任何非原始图片数据！

返回：
- preview_image_url: 预览图URL
- title: 生成的标题
- text_sections: 文案内容结构
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "user_input": {
                    "type": "string",
                    "description": "用户的原始需求描述",
                },
                "materials": {
                    "type": "array",
                    "description": "【必须】包含用户上传的模板图片，type='image'。content 字段必须是原始图片的 base64 数据（data:image/...;base64,...格式），而不是图片分析结果",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["image", "video", "text"]},
                            "url": {"type": "string", "description": "图片 URL（可选）"},
                            "content": {"type": "string", "description": "【重要】必须是原始图片的 base64 数据，格式：data:image/png;base64,... 或 data:image/jpeg;base64,...。不要传递图片分析结果或 OCR 文本！"},
                        }
                    }
                },
                "backup_preview_image_url": {
                    "type": "string",
                    "description": "预览图 URL 的后备值（由系统自动注入）",
                },
            },
            "required": ["user_input", "materials"],
        }

    def _is_valid_image_material(self, mat: Dict[str, Any]) -> bool:
        """
        验证素材是否为有效的图片素材（包含有效的 base64 数据或 URL）

        注意：用户上传的原始图片一定是 data:image/...;base64,... 格式
        不接受纯 base64 字符串，因为那可能是 vision 模型返回的文本描述

        Returns:
            True 如果是有效的图片素材
        """
        if not isinstance(mat, dict):
            return False
        if mat.get("type") != "image":
            return False

        content = mat.get("content")
        url = mat.get("url")

        # 有 URL 就是有效的
        if url:
            return True

        # 检查 content 是否为有效的 base64 图片数据
        # 用户上传的原始图片必须是 data:image/...;base64,... 格式
        if content and isinstance(content, str):
            if content.startswith("data:image/"):
                # 进一步验证：长度应该足够大（真正的 base64 图片数据通常 > 1KB）
                if len(content) > 1000:
                    return True
        return False

    async def execute(
        self,
        user_input: str,
        materials: List[Dict[str, Any]] = None,
        backup_preview_image_url: Optional[str] = None,
    ) -> ToolResult:
        """
        执行文案模板预览生成
        """
        try:
            from ..storage.session_store import get_session_store
            store = get_session_store()

            # 获取当前会话（如果存在）
            current_session_id = None
            if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                agent_session = getattr(self.orchestrator._agent, '_current_session', None)
                if agent_session:
                    current_session_id = agent_session.session_id

            # =============================================================
            # 始终优先使用 _current_materials（用户当前上传的最新素材）
            # 而不是信任 LLM 传递的 materials 参数（可能包含过期或错误的 URL）
            # =============================================================
            final_materials = None

            # 优先从 _current_materials 获取（用户当前上传的最新素材）
            if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                agent_materials = getattr(self.orchestrator._agent, '_current_materials', None)
                if agent_materials and len(agent_materials) > 0:
                    final_materials = agent_materials
                    logger.info(f"[GenerateTemplate] 使用 _current_materials 获取素材: {len(final_materials)} 个")
                else:
                    logger.warning(f"[GenerateTemplate] _current_materials 为空，尝试使用传入的 materials")
                    final_materials = materials if materials else []

            # 如果 _current_materials 也没有，使用传入的 materials
            if not final_materials:
                final_materials = materials if materials else []

            # 如果仍然没有有效素材，返回错误
            if not final_materials or len(final_materials) == 0:
                return ToolResult(success=False, error="没有提供素材图片，请上传模板图片后再试")

            # 识别模板图片URL（优先使用 url）
            template_image_url = None
            if final_materials:
                for mat in final_materials:
                    if self._is_valid_image_material(mat):
                        url = mat.get("url")
                        content = mat.get("content")

                        # 优先使用 url（已上传到服务器的情况）
                        if url:
                            template_image_url = url
                            logger.info(f"[GenerateTemplate] 识别到模板图片 (url): {url[:80]}...")
                            break
                        # 回退到 content (base64)
                        elif content:
                            template_image_url = content
                            logger.info(f"[GenerateTemplate] 识别到模板图片 (base64 content), length={len(content)}")
                            break

            # 双重赋值：先用传入参数，再用 backup 参数覆盖（保证正确）
            if backup_preview_image_url is not None:
                preview_image_url = backup_preview_image_url

            # 创建或更新会话（使用后备后的 final_materials）
            result = await self.orchestrator.create_session(
                user_input=user_input,
                materials=final_materials,
                session_id=current_session_id,
                auto_generate=False,
            )

            if not result.success or not result.session:
                return ToolResult(success=False, error=f"创建会话失败: {result.error}")

            session = result.session

            # 更新 agent 的当前会话
            if hasattr(self.orchestrator, '_agent') and self.orchestrator._agent is not None:
                self.orchestrator._agent._current_session = session

            # Step 2: 检查并保存模板图片URL到 session.brief
            # 如果 session.brief 没有 template_image_url，但我们在 materials 中识别到了，就保存它
            if template_image_url and session.brief:
                brief_has_template = hasattr(session.brief, 'template_image_url') and bool(session.brief.template_image_url)
                if not brief_has_template:
                    session.brief.template_image_url = template_image_url
                    await store.save(session)
                    logger.info(f"[GenerateTemplate] Updated session.brief.template_image_url")

            # Step 3: 生成文案模板预览
            logger.info(f"[GenerateTemplate] Generating template preview for session: {session.session_id}")
            preview_result = await self.orchestrator.generate_template_preview(
                session,
                session_store=store,
            )

            if not preview_result.get("success"):
                return ToolResult(
                    success=False,
                    error=preview_result.get("error", "生成预览失败")
                )

            # 获取方案数据
            plan_data = None
            if session.current_plan:
                if hasattr(session.current_plan, 'to_dict'):
                    plan_data = session.current_plan.to_dict()
                else:
                    plan_data = dict(session.current_plan)

            # 返回完整结果
            return ToolResult(
                success=True,
                content=json.dumps({
                    "session_id": session.session_id,
                    "message": "已生成文案模板预览",
                    "preview_image_url": preview_result.get("preview_image_url"),
                    "title": preview_result.get("title", ""),
                    "text_sections": preview_result.get("text_sections", []),
                    "plan_data": plan_data,
                    "template_image_url": session.brief.template_image_url if session.brief else None,
                }, ensure_ascii=False),
            )

        except Exception as e:
            logger.error(f"GenerateTemplateTool exception: {e}", exc_info=True)
            return ToolResult(success=False, error=f"生成异常: {str(e)}")


class GetToolResultTool(Tool):
    """获取历史工具结果工具"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "get_tool_result"

    @property
    def description(self) -> str:
        return """**get_tool_result** - 回滚工具，用于恢复到之前的版本

当用户想要以下操作时使用：
- "用上一版的图片"
- "回滚到 V1 版本"
- "恢复之前的标题"
- "用上上次的预览图"

返回：指定版本的数据，包含 preview_image_url、title、text_sections 等字段。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "工具名称（可选），如 generate_template。不填则获取最近任何工具的结果。",
                },
                "index": {
                    "type": "integer",
                    "description": "版本索引（默认0）。0=V1最原始版本，1=V2，2=V3，以此类推。数字越大版本越新。例如：用户说「用V3版本的图片」，则 index=2。",
                    "default": 0,
                },
                "field": {
                    "type": "string",
                    "description": "要获取的字段名（可选）。例如：preview_image_url, title, text_sections, plan_data。",
                },
                "history": {
                    "type": "boolean",
                    "description": "是否返回历史记录列表（可选，默认false）。",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        tool_name: Optional[str] = None,
        index: int = 0,
        field: Optional[str] = None,
        history: bool = False,
    ) -> ToolResult:
        try:
            agent = getattr(self.orchestrator, '_agent', None)
            if not agent:
                return ToolResult(success=False, error="Agent 未初始化")

            store = getattr(agent, '_tool_result_store', None)
            if not store:
                return ToolResult(success=False, error="工具结果存储器未初始化")

            if history:
                records = store.get_history(tool_name, limit=10)
                return ToolResult(
                    success=True,
                    content=json.dumps({"history": records}, ensure_ascii=False),
                )

            record = store.get_latest(tool_name, index)
            if not record:
                return ToolResult(success=False, error=f"未找到工具结果: {tool_name}")

            if field:
                value = store.get_field(tool_name, field, index)
                result_json = {
                    "field": field,
                    "value": value,
                    "tool_name": record.tool_name,
                }
                return ToolResult(
                    success=True,
                    content=json.dumps(result_json, ensure_ascii=False),
                )

            return ToolResult(
                success=True,
                content=json.dumps({
                    "tool_name": record.tool_name,
                    "result_data": record.result_data,
                    "success": record.success,
                    "timestamp": record.timestamp.isoformat(),
                }, ensure_ascii=False),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"获取工具结果异常: {str(e)}")


# 工具定义列表（用于注册到 Agent）
TOOL_DEFINITIONS = [
    # 保留必要的工具
    GenerateContentTool,
    ReviewContentTool,
    IterateContentTool,
    RegeneratePlansTool,
    PublishContentTool,
    GetSessionTool,
    # 统一的方案工具（替代 create_session + generate_template）
    ModifyPlanTool,
]
