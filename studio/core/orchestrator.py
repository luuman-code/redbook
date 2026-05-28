"""
Orchestrator - 总控 Agent

参考 plan.md:
- Orchestrator (总调度 Agent)
  - 维护一个任务 DAG，根据方案并行/串行调用各 Agent
  - 收集所有 Agent 输出，进行冲突检测与融合
  - 最终组装成小红书完整的笔记数据结构
"""

import asyncio
import base64
import httpx
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..config.studio_config import StudioConfig
from ..models.brief import Brief, ContentGoal
from ..models.content_item import ContentItem, ContentType, ItemStatus
from ..models.content_plan import ContentPlan
from ..models.session import Session, SessionStatus
from ..models.version import Version
from ..models.message import Message
from ..debug_logger import get_logger, get_workflow_logger, get_conversation_logger
from ..api.websocket_manager import ProgressEvent

from .brief_parser import BriefParser
from .planner import Planner
from .critic import Critic
from .iterator import Iterator
from .publisher import Publisher

# 获取日志记录器
logger = get_logger("orchestrator")

# 导入 agent 模块的请求类
from agent.models.llm_gateway import LLMRequest

# 导入记忆模块
try:
    from memory import MemoryManager
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    MemoryManager = None
from agent.models.image_gateway import ImageGenerationRequest
from agent.models.video_gateway import VideoGenerationRequest
from agent.models.tts_gateway import TTSRequest
from agent.models.vision_gateway import VisionRequest

if TYPE_CHECKING:
    from ..skills.base_skill import BaseSkill


@dataclass
class OrchestratorResult:
    """Orchestrator 结果"""
    success: bool
    session: Optional[Session] = None
    error: Optional[str] = None
    messages: List[str] = None
    plans: List[Dict[str, Any]] = None
    iteration_count: int = 0
    modified_items: List = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.plans is None:
            self.plans = []
        if self.modified_items is None:
            self.modified_items = []


class Orchestrator:
    """
    总控 Orchestrator

    职责：
    1. 协调所有 Agent 的工作流程
    2. 维护任务 DAG
    3. 管理会话状态
    4. 处理用户反馈循环
    """

    def __init__(
        self,
        llm_gateway,
        vision_gateway=None,
        image_gateway=None,
        tts_gateway=None,
        video_gateway=None,
        config: StudioConfig = None,
        memory_manager=None,
        config_service=None,
        websocket_manager=None,
    ):
        """
        初始化 Orchestrator

        Args:
            llm_gateway: LLM 网关
            vision_gateway: Vision 网关
            image_gateway: Image Generation 网关
            tts_gateway: TTS 网关
            video_gateway: Video 网关 (deprecated, use video_gateways instead)
            config: Studio 配置
            memory_manager: 记忆管理器（可选）
            config_service: 配置服务（用于创建视频网关）
        """
        from agent.models.gateway_factory import GatewayFactory

        self.llm_gateway = llm_gateway
        self.vision_gateway = vision_gateway
        self.image_gateway = image_gateway
        self.tts_gateway = tts_gateway
        self.config = config or StudioConfig()
        self._config_service = config_service

        # 初始化多个视频网关（按模型类型）
        self._video_gateways = {}
        if video_gateway:
            # 兼容旧接口：单个 video_gateway 作为默认
            self._video_gateways["default"] = video_gateway
            self._video_gateways["t2v"] = video_gateway
            self._video_gateways["i2v"] = video_gateway
            self._video_gateways["r2v"] = video_gateway
            self._video_gateways["video-edit"] = video_gateway

        # 初始化记忆管理器
        self.memory = memory_manager
        if memory_manager is None and MEMORY_AVAILABLE:
            self.memory = MemoryManager()

        # 初始化 Agent
        self.parser = BriefParser(llm_gateway, vision_gateway, self.config)
        self.planner = Planner(llm_gateway, self.config)
        self.critic = Critic(llm_gateway, self.config)
        self.iterator = Iterator(llm_gateway, self.config)
        self.publisher = Publisher(self.config)

        # 初始化内容存储
        self.content_store = None
        try:
            from ..storage.content_store import ContentStore
            self.content_store = ContentStore(base_dir="data/studio/sessions")
        except Exception as e:
            print(f"ContentStore 初始化失败: {e}")

        # 初始化 WebSocket 管理器（将在 main.py 中注入）
        self._ws_manager = websocket_manager

    async def create_session(
        self,
        user_input: str,
        materials: List[Dict[str, Any]] = None,
        user_context: Dict[str, Any] = None,
        auto_generate: bool = False,
        session_id: Optional[str] = None,
        template_analysis: List[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        创建新会话

        Args:
            user_input: 用户输入
            materials: 素材列表
            user_context: 用户上下文
            auto_generate: 是否自动生成方案（默认 True）
            session_id: 可选，现有会话 ID。如果提供，则复用该会话 ID 而非创建新的
            template_analysis: 可选，模板分析结果（来自 analyze_template 工具）

        Returns:
            OrchestratorResult
        """
        wf_logger = get_workflow_logger("orchestrator.create_session")
        wf_logger.start("create_session")
        logger.info(f"[create_session] START - user_input: {user_input[:80] if user_input else '(empty)'}, auto_generate={auto_generate}")

        try:
            # 如果提供了 session_id，先检查是否已存在
            if session_id:
                from ..storage.session_store import get_session_store
                store = get_session_store()
                existing_session = await store.get(session_id)
                if existing_session:
                    logger.info(f"[create_session] Found existing session: {session_id}")
                    # 如果已有会话且有新的 user_input，需要重新解析生成方案
                    if user_input:
                        # 保存原有的模板图片URL，避免在重新解析时丢失
                        original_template_url = None
                        if existing_session.brief and hasattr(existing_session.brief, 'template_image_url'):
                            original_template_url = existing_session.brief.template_image_url

                        # 构建 user_context，确保 template_analysis 被传递
                        effective_user_context = user_context or {}
                        if template_analysis:
                            effective_user_context['template_analysis'] = template_analysis
                            logger.debug(f"Using template_analysis for existing session: {len(template_analysis)} templates")
                        # 重新解析需求并生成方案
                        parse_result = await self.parser.parse(user_input, materials or [], effective_user_context)
                        if parse_result.success:
                            # 恢复原有的模板图片URL（如果新解析没有设置）
                            if original_template_url and not parse_result.brief.template_image_url:
                                parse_result.brief.template_image_url = original_template_url
                                logger.debug(f"Restored original template_image_url for session: {session_id}")

                            existing_session.brief = parse_result.brief
                            plan_result = await self.planner.plan(parse_result.brief)
                            if plan_result.success:
                                existing_session.current_plan = plan_result.plan
                                await store.save(existing_session)
                                logger.info(f"[create_session] Updated existing session with new plan: {session_id}")
                                return OrchestratorResult(
                                    success=True,
                                    session=existing_session,
                                    messages=["需求解析完成", "方案生成完成"],
                                )
                    elif existing_session.current_plan and not user_input:
                        # 已有方案且没有新输入，直接返回
                        logger.info(f"[create_session] Returning existing session with plan: {session_id}")
                        return OrchestratorResult(
                            success=True,
                            session=existing_session,
                            messages=["会话已恢复"],
                        )

            # 如果 auto_generate=False 且没有 user_input，创建空会话
            if not auto_generate and not user_input:
                logger.info("[create_session] Creating empty session (no user_input)")
                # 创建一个空的 Brief
                brief = Brief(
                    id=str(uuid.uuid4()),
                    goal=ContentGoal.PLANT,
                    style="活泼",
                    keywords=[],
                    must_include=[],
                    image_style="摄影实拍",
                    need_video=False,
                    need_voiceover=False,
                    need_text=True,
                    need_images=True,
                    need_bgm=False,
                    bgm_preference="轻快",
                    target_audience="",
                    reference_materials=[],
                    raw_input="",
                    extracted_product_info={},
                    template_image_url=None,
                )
                plan = None
            else:
                # 1. 解析需求
                logger.debug("Step 1: Parsing brief...")
                wf_logger.start("parser.parse")

                # 如果有模板分析结果，将其添加到 user_context 中
                effective_user_context = user_context or {}
                if template_analysis:
                    effective_user_context['template_analysis'] = template_analysis
                    logger.debug(f"Added template_analysis to context: {len(template_analysis)} templates")

                parse_result = await self.parser.parse(user_input, materials, effective_user_context)
                logger.debug(f"parser.parse result: success={parse_result.success}")
                wf_logger.end("parser.parse", success=parse_result.success)

                if not parse_result.success:
                    logger.warning(f"Brief parsing failed: {parse_result.error}")
                    wf_logger.end("create_session", success=False, message=parse_result.error)
                    return OrchestratorResult(
                        success=False,
                        error=f"需求解析失败: {parse_result.error}",
                    )

                brief = parse_result.brief
                logger.debug(f"Brief parsed: goal={brief.goal.value}, style={brief.style}")

                # 2. 生成方案
                logger.debug("Step 2: Generating plan...")
                wf_logger.start("planner.plan")
                plan_result = await self.planner.plan(brief)
                logger.debug(f"planner.plan result: success={plan_result.success}")
                wf_logger.end("planner.plan", success=plan_result.success)

                if not plan_result.success:
                    logger.warning(f"Plan generation failed: {plan_result.error}")
                    wf_logger.end("create_session", success=False, message=plan_result.error)
                    return OrchestratorResult(
                        success=False,
                        error=f"方案生成失败: {plan_result.error}",
                    )

                plan = plan_result.plan
                logger.debug(f"Plan generated: plan_id={plan.plan_id}, title={plan.title}")

            # 3. 创建会话
            logger.debug("Step 3: Creating session object...")
            # 如果提供了 session_id，复用它；否则生成新的
            final_session_id = session_id if session_id else str(uuid.uuid4())
            session = Session(
                session_id=final_session_id,
                brief=brief,
                current_plan=plan,
                current_version=1,
                items=[],
                status=SessionStatus.PLANNING,
            )
            logger.debug(f"Session created: session_id={session.session_id}")

            messages = []
            if plan:
                # 3.5 添加初始方案消息到聊天（只有有方案时才添加）
                plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
                initial_plan_message = Message(
                    message_id=str(uuid.uuid4()),
                    role="assistant",
                    content="这是为你生成的内容方案，请确认：",
                    timestamp=datetime.now(),
                    metadata={
                        "message_type": "plan",
                        "intent_type": "plan_confirmation",
                        "plan_data": plan_dict,
                    },
                )
                session.messages.append(initial_plan_message)

                # 4. 创建初始版本（只有有方案时才创建）
                initial_version = Version.create_snapshot(
                    session_id=session.session_id,
                    version_number=1,
                    plan=plan,
                    items=[],
                    change_summary="初始版本",
                    created_by="orchestrator",
                )
                session.versions.append(initial_version)
                messages = ["需求解析完成", "方案生成完成"]
            else:
                # 空会话，不生成方案
                session.status = SessionStatus.CREATED
                messages = ["会话创建成功，请在对话框中输入需求"]

            if not auto_generate and user_input:
                # 有输入但跳过生成
                messages = ["需求解析完成", "等待方案生成..."]
            if 'parse_result' in dir() and parse_result is not None and parse_result.warnings:
                messages.extend([f"提示: {w}" for w in parse_result.warnings])
            if plan and plan_result and plan_result.warnings:
                messages.extend([f"建议: {w}" for w in plan_result.warnings])

            # 初始化记忆会话
            if self.memory and self.memory.short_term:
                # 同步记忆会话 ID 与 session 的 session_id
                self.memory.session_id = session.session_id
                self.memory.short_term.session_id = session.session_id
                await self.memory.initialize_session(brief)
                # 保存方案到记忆（只有有方案时才保存）
                if plan:
                    plan_content = plan.to_dict().get("content", str(plan)) if hasattr(plan, "to_dict") else str(plan)
                    await self.memory.add_plan(plan_content)

            logger.info(f"Session created successfully: {session.session_id}")
            wf_logger.end("create_session", success=True, message=f"session_id={session.session_id}")

            # 保存最新创建的会话引用，供 Agent 使用
            self._latest_created_session = session
            logger.info(f"_latest_created_session set to: {session.session_id}")

            return OrchestratorResult(
                success=True,
                session=session,
                messages=messages,
            )

        except Exception as e:
            logger.error(f"create_session exception: {e}", exc_info=True)
            wf_logger.error("create_session", e)
            return OrchestratorResult(
                success=False,
                error=f"创建会话异常: {str(e)}",
            )

    async def generate(self, session: Session) -> OrchestratorResult:
        """
        执行内容生成

        Args:
            session: 会话对象

        Returns:
            OrchestratorResult
        """
        wf_logger = get_workflow_logger("orchestrator.generate")
        wf_logger.start("generate")
        logger.info(f"Starting content generation for session: {session.session_id}")

        # Emit generation_start event
        await self._emit_progress(
            session.session_id,
            ProgressEvent(
                event_type="generation_start",
                message="开始生成内容",
            ),
        )

        try:
            session.update_status(SessionStatus.GENERATING)
            messages = []

            # Calculate total tasks for progress tracking
            total_tasks = 0
            if session.brief.need_text:
                total_tasks += 1  # text generation is one task
            if session.brief.need_images:
                total_tasks += 1  # image generation is one task
            if session.brief.need_video:
                total_tasks += 1
            if session.brief.need_voiceover:
                total_tasks += 1

            # 1. 按需生成文案和配图
            text_items = []
            image_items = []

            logger.debug(f"Generation config: need_text={session.brief.need_text}, need_images={session.brief.need_images}")

            tasks = []
            if session.brief.need_text:
                tasks.append(self._generate_text(session))
            if session.brief.need_images:
                tasks.append(self._generate_images(session))

            if tasks:
                logger.debug(f"Starting {len(tasks)} parallel generation tasks...")
                current_task = 0
                # Emit progress for starting text/image generation
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_progress(
                        current=current_task,
                        total=total_tasks,
                        message="开始生成文案和配图...",
                    ),
                )
                results = await asyncio.gather(*tasks)
                current_task += len(tasks)
                task_index = 0
                if session.brief.need_text:
                    text_items = results[task_index]
                    task_index += 1
                if session.brief.need_images:
                    image_items = results[task_index]

                # Emit progress update
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_progress(
                        current=current_task,
                        total=total_tasks,
                        message=f"文案和配图生成完成",
                    ),
                )

            logger.debug(f"Text items: {len(text_items)}, Image items: {len(image_items)}")

            if session.brief.need_text:
                messages.append(f"文案生成完成 ({len(text_items)} 项)")
            if session.brief.need_images:
                messages.append(f"配图生成完成 ({len(image_items)} 项)")

            # 2. 调用图文冲突检测（仅当两者都生成时）
            alignment_issues = []
            if text_items and image_items:
                logger.debug("Checking image-text alignment...")
                wf_logger.start("critic.check_image_text_alignment")
                alignment_issues = await self.critic.check_image_text_alignment(session.brief, text_items + image_items)
                wf_logger.end("critic.check_image_text_alignment", success=True, message=f"issues={len(alignment_issues)}")
            if alignment_issues:
                messages.append(f"检测到 {len(alignment_issues)} 个图文不一致问题")
                # 保存到 session metadata
                session.metadata["alignment_issues"] = alignment_issues

            # 2.5 如果有模板图片，使用 generate_template_preview 生成最终模板图片
            template_image_items = []
            if session.brief.template_image_url and text_items and self.image_gateway:
                logger.debug("Generating template image with preview...")
                wf_logger.start("generate_template_preview")
                try:
                    # 使用已生成的 text_items，跳过文案生成，直接渲染模板
                    result = await self.generate_template_preview(
                        session,
                        text_items=text_items
                    )
                    if result.get("success") and result.get("preview_image_url"):
                        # 创建 ContentItem 保存结果
                        template_item = ContentItem(
                            item_id=f"template_{uuid.uuid4().hex[:8]}",
                            item_type=ContentType.COMPOSITE,
                            status=ItemStatus.COMPLETED,
                            content=result.get("preview_image_url"),
                            metadata={
                                "model_used": "qwen-image-2.0-pro",
                                "format": "url",
                                "title": result.get("title", ""),
                            }
                        )
                        template_image_items.append(template_item)
                        messages.append("模板套用完成")
                        logger.debug(f"Template generated successfully: {template_item.item_id}")
                    else:
                        error_msg = result.get("error", "生成模板失败")
                        messages.append(f"模板套用失败: {error_msg}")
                        logger.error(f"Template generation failed: {error_msg}")
                except Exception as e:
                    logger.error(f"Template application failed: {e}", exc_info=True)
                    messages.append(f"模板套用失败: {str(e)}")
                wf_logger.end("generate_template_preview", success=bool(template_image_items))

            # 3. 生成视频（如需要）
            video_items = []
            if session.brief.need_video:
                logger.debug("Generating video...")
                wf_logger.start("_generate_video")
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_progress(
                        current=2,
                        total=total_tasks,
                        message="正在生成视频...",
                    ),
                )
                video_items = await self._generate_video(session)
                wf_logger.end("_generate_video", success=True, message=f"items={len(video_items)}")
                messages.append(f"视频生成完成 ({len(video_items)} 项)")

            # 4. 生成音频（如需要）
            audio_items = []
            if session.brief.need_voiceover:
                logger.debug("Generating audio...")
                wf_logger.start("_generate_audio")
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_progress(
                        current=3,
                        total=total_tasks,
                        message="正在生成音频...",
                    ),
                )
                audio_items = await self._generate_audio(session)
                wf_logger.end("_generate_audio", success=True, message=f"items={len(audio_items)}")
                messages.append(f"音频生成完成 ({len(audio_items)} 项)")

            # 5. 更新会话
            session.items = text_items + image_items + template_image_items + video_items + audio_items
            logger.debug(f"Total items generated: {len(session.items)}")
            session.update_status(SessionStatus.REVIEWING)

            # 6. 保存生成内容到记忆
            if self.memory:
                await self.memory.add_generated_content(session.items)

            # 7. 创建版本快照
            new_version = Version.create_snapshot(
                session_id=session.session_id,
                version_number=session.current_version,
                plan=session.current_plan,
                items=session.items,
                change_summary="生成完成",
                created_by="orchestrator",
            )
            session.versions.append(new_version)

            # 8. 保存内容到本地
            if self.content_store:
                await self._save_content_to_local(session, session.current_version)

            # Emit generation_complete event
            await self._emit_progress(
                session.session_id,
                ProgressEvent(
                    event_type="generation_complete",
                    message=f"内容生成完成，共 {len(session.items)} 项",
                ),
            )

            logger.info(f"Content generation completed: {len(session.items)} items")
            wf_logger.end("generate", success=True, message=f"items={len(session.items)}")

            return OrchestratorResult(
                success=True,
                session=session,
                messages=messages,
            )

        except Exception as e:
            logger.error(f"generate exception: {e}", exc_info=True)
            session.update_status(SessionStatus.CREATED)
            wf_logger.error("generate", e)

            # Emit generation_error event
            await self._emit_progress(
                session.session_id,
                ProgressEvent.generation_error(
                    item_id="",
                    error=f"生成异常: {str(e)}",
                ),
            )

            return OrchestratorResult(
                success=False,
                session=session,
                error=f"生成异常: {str(e)}",
            )

    async def _emit_progress(self, session_id: str, event: ProgressEvent) -> None:
        """Emit a progress event to WebSocket clients if available"""
        if self._ws_manager:
            try:
                await self._ws_manager.send_progress(session_id, event)
            except Exception as e:
                logger.warning(f"Failed to emit progress event: {e}")

    async def review(self, session: Session) -> OrchestratorResult:
        """
        审核内容

        Args:
            session: 会话对象

        Returns:
            OrchestratorResult
        """
        try:
            critique = await self.critic.critique(
                session.brief,
                session.current_plan,
                session.items,
            )

            messages = [critique.overall_comment]
            messages.append(f"质量评分: {critique.score:.1f}/10")

            if critique.suggestions:
                messages.extend(critique.suggestions)

            # 保存审核结果到记忆
            if self.memory:
                review_text = f"评分: {critique.score}/10, 结论: {critique.overall_comment}"
                if critique.issues:
                    review_text += f", 问题: {'; '.join(critique.issues)}"
                await self.memory.add_review(review_text, reviewer="critic")

            return OrchestratorResult(
                success=critique.passed,
                session=session,
                messages=messages,
            )

        except Exception as e:
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"审核异常: {str(e)}",
            )

    async def iterate(
        self,
        session: Session,
        user_feedback: str,
    ) -> OrchestratorResult:
        """
        处理用户反馈，迭代修改

        Args:
            session: 会话对象
            user_feedback: 用户反馈

        Returns:
            OrchestratorResult
        """
        try:
            session.update_status(SessionStatus.ITERATING)

            # 0. 保存用户反馈到记忆
            if self.memory:
                await self.memory.add_feedback(user_feedback, feedback_type="revision")

            # 1. 解析用户反馈
            feedback = await self.critic.parse_feedback(user_feedback, session.items)

            # 2. 获取记忆上下文
            memory_context = ""
            if self.memory:
                memory_context = await self.memory.get_context_for_llm()

            # 3. 执行迭代（传入记忆上下文）
            result = await self.iterator.iterate(session, feedback, memory_context=memory_context)

            if not result.success:
                return OrchestratorResult(
                    success=False,
                    session=session,
                    error=result.error,
                )

            # 3. 审核修改后的内容
            critique = await self.critic.critique(
                session.brief,
                session.current_plan,
                session.items,
            )

            messages = [
                f"迭代完成 (第 {result.iteration_count} 轮)",
                f"修改了 {len(result.modified_items)} 项内容",
                critique.overall_comment,
            ]

            # 4. 保存内容到本地
            if self.content_store:
                await self._save_content_to_local(session, session.current_version)

            # 5. 创建版本快照（跟踪迭代历史）
            session.current_version += 1
            new_version = Version.create_snapshot(
                session_id=session.session_id,
                version_number=session.current_version,
                plan=session.current_plan,
                items=session.items,
                change_summary=f"迭代修改 (第 {result.iteration_count} 轮)",
                created_by="iterator",
            )
            session.versions.append(new_version)

            return OrchestratorResult(
                success=critique.passed,
                session=session,
                messages=messages,
                iteration_count=result.iteration_count,
                modified_items=result.modified_items,
            )

        except Exception as e:
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"迭代异常: {str(e)}",
            )

    async def publish(self, session: Session) -> OrchestratorResult:
        """
        发布内容

        Args:
            session: 会话对象

        Returns:
            OrchestratorResult
        """
        try:
            # 1. 最终审核
            critique = await self.critic.critique(
                session.brief,
                session.current_plan,
                session.items,
            )

            if not critique.passed:
                return OrchestratorResult(
                    success=False,
                    session=session,
                    error="内容未通过审核，请先处理问题",
                    messages=critique.issues,
                )

            # 2. 模拟发布
            result = await self.publisher.simulate_publish(session)

            if result.success:
                session.update_status(SessionStatus.PUBLISHED)

                # 3. 从成功内容中学习（保存到长期记忆）
                if self.memory:
                    await self.memory.learn_from_success(
                        content_items=session.items,
                        brief=session.brief,
                        performance_score=0.8
                    )

            return OrchestratorResult(
                success=result.success,
                session=session,
                messages=result.warnings,
            )

        except Exception as e:
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"发布异常: {str(e)}",
            )

    async def confirm_plan(self, session: Session) -> OrchestratorResult:
        """确认方案"""
        try:
            session.update_status(SessionStatus.CONFIRMED)
            return OrchestratorResult(
                success=True,
                session=session,
                messages=["方案已确认，可以开始生成内容"],
            )
        except Exception as e:
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"确认方案异常: {str(e)}",
            )

    async def init_agent(self) -> "XiaohongshuAgent":
        """
        初始化 LLM Agent

        Returns:
            XiaohongshuAgent 实例
        """
        from ..agent.agent import XiaohongshuAgent, LLMGatewayAdapter

        # 创建 LLM Gateway 适配器
        llm_adapter = LLMGatewayAdapter(self.llm_gateway)

        return XiaohongshuAgent(
            llm_client=llm_adapter,
            orchestrator=self,
            max_steps=50,
        )

    async def chat(
        self,
        session: Session,
        user_message: str,
        materials: List[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        处理聊天消息，实现实时交互式需求理解

        Args:
            session: 会话对象
            user_message: 用户发送的消息
            materials: 可选的素材列表

        Returns:
            OrchestratorResult: 包含 AI 回复消息
        """
        wf_logger = get_workflow_logger("orchestrator.chat")
        wf_logger.start("chat")
        logger.info(f"Processing chat message for session: {session.session_id}, message: {user_message[:50]}...")

        # 记录用户消息到对话历史
        conv_logger = get_conversation_logger()
        conv_logger.log_user_message(session.session_id, user_message)

        try:
            # 1. 添加用户消息到会话
            user_msg = Message(
                message_id=str(uuid.uuid4()),
                role="user",
                content=user_message,
                timestamp=datetime.now(),
            )
            session.messages.append(user_msg)

            # 2. 使用 Agent 智能处理用户消息
            return await self.chat_with_agent(session, user_message, materials)

        except Exception as e:
            logger.error(f"chat exception: {e}", exc_info=True)
            wf_logger.error("chat", e)

            # 发送 typing_end 事件（即使出错）
            await self._emit_progress(
                session.session_id,
                ProgressEvent.typing_end(),
            )

            return OrchestratorResult(
                success=False,
                session=session,
                error=f"聊天处理异常: {str(e)}",
            )

    async def chat_with_agent(
        self,
        session: Session,
        user_message: str,
        materials: List[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        使用 XiaohongshuAgent 处理聊天消息

        Args:
            session: 会话对象
            user_message: 用户消息
            materials: 可选的素材列表

        Returns:
            OrchestratorResult
        """
        wf_logger = get_workflow_logger("orchestrator.chat_with_agent")
        wf_logger.start("chat_with_agent")
        logger.info(f"Using Agent to process message for session: {session.session_id}")

        try:
            # 1. 初始化/获取 Agent
            if not hasattr(self, '_agent') or self._agent is None:
                self._agent = await self.init_agent()
                logger.info("Agent initialized successfully")

            # 2. 保存当前会话到 Agent
            self._agent._current_session = session

            # 3. 如果有新素材，保存到 agent 的上下文中
            if materials:
                self._agent._current_materials = materials
                logger.info(f"[chat_with_agent] Set _current_materials: {len(materials)} items")

            # 4. 发送 typing_start 事件
            await self._emit_progress(
                session.session_id,
                ProgressEvent.typing_start(),
            )

            # 4. 调用 Agent 处理消息
            result = await self._agent.chat(session, user_message)

            # 5. 发送 typing_end 事件
            await self._emit_progress(
                session.session_id,
                ProgressEvent.typing_end(),
            )

            # 6. 处理 Agent 返回结果
            if result["success"]:
                messages = result.get("messages", [])
                response_content = messages[0] if messages else ""

                # 从 result 中获取 plan_data（如果有）
                plan_data = result.get("plan_data")

                # 如果 result 中没有 plan_data，尝试从 result["session"].current_plan 获取
                # 注意：必须使用 result["session"] 而不是传入的 session 变量，因为 Agent 可能创建了新 session
                agent_session = result.get("session")
                if not plan_data and agent_session and agent_session.current_plan:
                    if hasattr(agent_session.current_plan, 'to_dict'):
                        plan_data = agent_session.current_plan.to_dict()
                    else:
                        plan_data = dict(agent_session.current_plan)
                    logger.info(f"[chat_with_agent] plan_data from agent_session.current_plan: title={plan_data.get('title') if plan_data else 'N/A'}")
                elif not plan_data:
                    logger.warning(f"[chat_with_agent] No plan_data available - agent_session.current_plan is None")

                message_type = "text"
                metadata = {}

                # 如果有 plan_data，设置正确的 message_type
                if plan_data:
                    message_type = "plan"
                    metadata = {
                        "message_type": "plan",
                        "plan_data": plan_data,
                    }
                else:
                    metadata = {"message_type": "agent"}

                # 创建 AI 回复消息（注意：不再追加到 session.messages，由 agent.chat 统一管理）
                assistant_msg = Message(
                    message_id=str(uuid.uuid4()),
                    role="assistant",
                    content=response_content,
                    timestamp=datetime.now(),
                    metadata=metadata,
                )

                # 记录助手回复到对话历史
                conv_logger = get_conversation_logger()
                actual_session_id = agent_session.session_id if agent_session else session.session_id
                conv_logger.log_assistant_message(actual_session_id, response_content)

                # 7. 发送 chat_message 事件
                await self._emit_progress(
                    actual_session_id,
                    ProgressEvent.chat_message(assistant_msg),
                )

                wf_logger.end("chat_with_agent", success=True)
                # 返回完整消息对象，而不是字符串
                # 注意：必须返回 agent_session（包含 Agent 创建的新 session 和 plan），而不是传入的旧 session
                return OrchestratorResult(
                    success=True,
                    session=agent_session if agent_session else session,
                    messages=[assistant_msg.to_dict()],  # 返回消息对象
                )
            else:
                wf_logger.end("chat_with_agent", success=False, error="Agent 处理失败")
                return OrchestratorResult(
                    success=False,
                    session=session,
                    error="Agent 处理失败",
                )

        except Exception as e:
            logger.error(f"chat_with_agent exception: {e}", exc_info=True)
            wf_logger.error("chat_with_agent", e)

            # 发送 typing_end 事件（即使出错）
            try:
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.typing_end(),
                )
            except:
                pass

            return OrchestratorResult(
                success=False,
                session=session,
                error=f"Agent 处理异常: {str(e)}",
            )

    async def chat_with_agent_only(
        self,
        user_message: str,
        materials: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        直接使用 Agent 处理用户消息，无需预先创建会话

        Agent 会自动调用 create_session 工具来创建会话并生成方案。

        Args:
            user_message: 用户消息
            materials: 素材列表

        Returns:
            Dict containing:
            - success: bool
            - session: Session - 创建的会话
            - messages: List[str] - AI 回复消息
            - plan_data: Dict - 完整方案数据（与前端 UI 一致）
        """
        wf_logger = get_workflow_logger("orchestrator.chat_with_agent_only")
        wf_logger.start("chat_with_agent_only")
        logger.info(f"Agent processing message without pre-created session: {user_message[:50]}...")

        # 记录用户消息到对话历史（使用临时 session_id）
        conv_logger = get_conversation_logger()
        conv_logger.log_user_message(temp_session_id, user_message)

        try:
            # 1. 初始化/获取 Agent
            if not hasattr(self, '_agent') or self._agent is None:
                self._agent = await self.init_agent()
                logger.info("Agent initialized successfully")

            # 2. 创建一个临时会话，让 Agent 可以工作
            # Agent 的 tools 会创建真正的会话
            temp_session_id = str(uuid.uuid4())
            temp_brief = Brief(
                id=temp_session_id,
                goal=ContentGoal.LIFESTYLE,
                style="活泼",
                keywords=[],
                must_include=[],
                image_style="摄影实拍",
                need_video=False,
                need_voiceover=False,
                need_text=True,
                need_images=True,
                need_bgm=False,
                target_audience="",
                reference_materials=[],
                raw_input=user_message,
                extracted_product_info={},
            )
            temp_plan = ContentPlan(
                plan_id=temp_session_id,
                brief_id=temp_session_id,
                title="",
                text_sections=[],
            )
            temp_session = Session(
                session_id=temp_session_id,
                brief=temp_brief,
                current_plan=temp_plan,
                current_version=1,
                items=[],
                status=SessionStatus.CREATED,
            )

            # 3.1 创建初始版本 V1（空版本，用于版本标签显示）
            from ..models.version import Version
            initial_version = Version.create_snapshot(
                session_id=temp_session.session_id,
                version_number=1,
                plan=temp_plan,
                items=[],
                change_summary="初始版本",
                created_by="system",
            )
            temp_session.versions.append(initial_version)

            # 3. 保存临时会话到 Agent
            self._agent._current_session = temp_session

            # 3.5 设置素材到 agent 上下文
            if materials:
                self._agent._current_materials = materials
                logger.debug(f"Set _current_materials: {len(materials)} items")
            else:
                existing_materials = getattr(self._agent, '_current_materials', [])
                logger.debug(f"No new materials, keeping existing: {len(existing_materials)} items")

            # 4. 发送 typing_start 事件
            await self._emit_progress(
                temp_session_id,
                ProgressEvent.typing_start(),
            )

            # 5. 调用 Agent 处理消息
            result = await self._agent.chat(temp_session, user_message)

            # 6. 发送 typing_end 事件
            await self._emit_progress(
                temp_session_id,
                ProgressEvent.typing_end(),
            )

            # 7. 从 Agent 返回结果中提取信息
            if result["success"]:
                messages = result.get("messages", [])

                # 优先从 _latest_created_session 获取 plan_data
                # 因为 Agent 调用 create_session 工具后，新会话会被保存到这里
                latest_session = getattr(self, '_latest_created_session', None)
                logger.info(f"latest_session after Agent call: {latest_session}, session_id={latest_session.session_id if latest_session else None}")

                plan_data = None
                session = None

                # 直接从 store 获取最新创建的 session，因为 _latest_created_session 可能还没更新
                if latest_session and latest_session.session_id:
                    from ..storage.session_store import get_session_store
                    store = get_session_store()
                    fresh_session = await store.get(latest_session.session_id)
                    if fresh_session and fresh_session.current_plan:
                        session = fresh_session
                        if hasattr(fresh_session.current_plan, 'to_dict'):
                            plan_data = fresh_session.current_plan.to_dict()
                        else:
                            plan_data = dict(fresh_session.current_plan)
                        logger.info(f"plan_data from store (via latest_session): session_id={fresh_session.session_id}, title={plan_data.get('title')}, sections_count={len(plan_data.get('text_sections', []))}")

                # 如果还是空的，尝试其他方式
                if plan_data is None:
                    if latest_session and latest_session.current_plan and latest_session.current_plan.text_sections:
                        session = latest_session
                        if hasattr(latest_session.current_plan, 'to_dict'):
                            plan_data = latest_session.current_plan.to_dict()
                        else:
                            plan_data = dict(latest_session.current_plan)
                        logger.info(f"plan_data from latest_session.current_plan: title={plan_data.get('title')}")

                # 如果仍然是空的，从 messages 中提取 plan_data
                if plan_data is None:
                    for msg in messages:
                        if isinstance(msg, dict) and msg.get("metadata", {}).get("plan_data"):
                            plan_data = msg["metadata"]["plan_data"]
                            logger.info(f"plan_data from messages metadata: title={plan_data.get('title')}")
                            # 强制从 store 获取 session
                            if session is None:
                                from ..storage.session_store import get_session_store
                                store = get_session_store()
                                # 尝试从 messages 内容中提取 session_id
                                import re
                                content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                                session_id_match = re.search(r"ID：`([a-f0-9-]+)`", content)
                                if session_id_match:
                                    found_session_id = session_id_match.group(1)
                                    found_session = await store.get(found_session_id)
                                    if found_session:
                                        session = found_session
                                        # 从 store 中获取最新的 plan_data
                                        if hasattr(found_session, 'current_plan') and found_session.current_plan:
                                            if hasattr(found_session.current_plan, 'to_dict'):
                                                plan_data = found_session.current_plan.to_dict()
                                            else:
                                                plan_data = dict(found_session.current_plan)
                                            logger.info(f"Got plan_data from store: title={plan_data.get('title')}")
                                        logger.info(f"Found session from messages: {found_session_id}")
                            break

                # 最终检查：如果 session 存在但 plan_data 为空，从 session 获取
                if plan_data is None and session and hasattr(session, 'current_plan') and session.current_plan:
                    if hasattr(session.current_plan, 'to_dict'):
                        plan_data = session.current_plan.to_dict()
                    else:
                        plan_data = dict(session.current_plan)
                    logger.info(f"Final plan_data from session.current_plan: title={plan_data.get('title')}")

                # 如果 session 仍然是 None 但有 latest_session，使用 latest_session
                if session is None and latest_session:
                    session = latest_session
                    logger.info(f"Using latest_session as fallback: {latest_session.session_id}")

                # 记录助手回复到对话历史
                response_content = messages[0] if messages else ""
                actual_session_id = session.session_id if session else temp_session_id
                conv_logger.log_assistant_message(actual_session_id, response_content)

                # 提取预览图信息（如果有）
                preview_image_url = None
                preview_title = None
                preview_text_sections = None
                if session and hasattr(session, 'metadata') and session.metadata:
                    preview_image_url = session.metadata.get('preview_image_url')
                    preview_title = session.metadata.get('preview_title')
                    preview_text_sections = session.metadata.get('preview_text_sections')
                    if preview_image_url:
                        logger.info(f"Extracted preview_image_url from session metadata: {preview_image_url[:50]}...")

                wf_logger.end("chat_with_agent_only", success=True)
                return {
                    "success": True,
                    "session": session,
                    "messages": messages,
                    "plan_data": plan_data,
                    "preview_image_url": preview_image_url,
                    "preview_title": preview_title,
                    "preview_text_sections": preview_text_sections,
                }
            else:
                wf_logger.end("chat_with_agent_only", success=False, error="Agent 处理失败")
                return {
                    "success": False,
                    "session": temp_session,
                    "messages": result.get("messages", []),
                    "plan_data": None,
                    "error": result.get("error"),
                }

        except Exception as e:
            logger.error(f"chat_with_agent_only exception: {e}", exc_info=True)
            wf_logger.error("chat_with_agent_only", e)
            return {
                "success": False,
                "session": None,
                "messages": [],
                "plan_data": None,
                "error": f"Agent 处理异常: {str(e)}",
            }

    async def _analyze_intent(
        self,
        user_message: str,
        session: Session,
    ) -> Dict[str, Any]:
        """分析用户消息意图"""
        user_lower = user_message.lower().strip()

        # 检测模糊反馈模式
        vague_patterns = [
            "不够吸引人", "改改", "再改改", "再来", "重新", "随便",
            "再想想", "不够好", "不太好", "差", "烂"
        ]

        # 检测修改目标
        modify_patterns = {
            "title": ["标题", "title"],
            "text": ["正文", "内容", "文案", "text"],
            "image": ["图片", "配图", "图", "image"],
        }

        # 检测操作意图
        generate_patterns = ["生成", "开始", "create", "generate"]
        confirm_patterns = ["确认", "好的", "可以", "开始生成", "ok", "yes"]

        # 1. 检查是否需要澄清
        if any(p in user_message for p in vague_patterns):
            clarification = await self.critic.ask_clarification(user_message, session.items)
            if clarification.get("needs_clarification"):
                questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(clarification["questions"])])
                response = f"为了更好地帮助你，请回答以下问题：\n\n{questions}\n\n或者你可以直接告诉我你的具体想法～"
                return {
                    "type": "clarification_needed",
                    "response": response,
                    "questions": clarification["questions"],
                    "suggested_actions": clarification.get("suggested_actions", []),
                }

        # 2. 检查是否是修改请求
        for target, patterns in modify_patterns.items():
            if any(p in user_message for p in patterns):
                # 需要修改特定内容
                modify_type = target if target != "text" else "content"
                return {
                    "type": "modify_request",
                    "target": modify_type,
                    "original_request": user_message,
                    "response": f"好的，你想修改{self._get_target_name(target)}。请具体说明你想要什么样的效果？",
                }

        # 3. 检查是否是生成请求
        if any(p in user_message for p in generate_patterns):
            if session.status == SessionStatus.PLANNING:
                return {
                    "type": "generate_request",
                    "response": "好的，我现在开始生成内容方案，请稍候...",
                }
            return {
                "type": "generate_request",
                "response": "内容方案已经准备好了，你可以让我开始生成内容。",
            }

        # 4. 检查是否是确认意图
        if any(p in user_message for p in confirm_patterns):
            if session.status == SessionStatus.PLANNING:
                # 返回方案消息让用户在聊天中确认
                plan_dict = session.current_plan.to_dict() if hasattr(session.current_plan, "to_dict") else dict(session.current_plan)
                return {
                    "type": "plan_confirmation",
                    "message_type": "plan",
                    "response": "这是为你生成的内容方案，请确认：",
                    "plan_data": plan_dict,
                }

        # 5. 检查是否是问候
        greeting_patterns = ["你好", "hi", "hello", "嗨", "在吗", "在嘛"]
        if any(p in user_lower for p in greeting_patterns):
            return {
                "type": "greeting",
                "response": "你好！我是 AI 内容助手。告诉我你想创作什么类型的内容，比如：\n\n• \"我想推广我的蓝牙耳机\"\n• \"分享一款好用的护肤品\"\n• \"教大家如何拍照\"\n\n我会帮你完成从需求分析到内容生成的全流程！",
            }

        # 6. 尝试解析为需求描述，更新 Brief
        if len(user_message) > 10 and session.status in [
            SessionStatus.CREATED,
            SessionStatus.PLANNING,
        ]:
            # 可能是新的需求描述
            return {
                "type": "brief_update",
                "response": f"明白了，你想要：{user_message[:50]}...\n\n让我分析一下这个需求，并为你生成合适的内容方案。",
            }

        # 7. 通用响应
        return {
            "type": "general",
            "response": f"我理解你的想法。关于「{user_message[:30]}...」，请告诉我更多细节，或者你可以：\n\n• 描述你想要创作的内容主题\n• 让我开始生成内容方案\n• 修改现有的某个部分",
        }

    def _get_target_name(self, target: str) -> str:
        """获取目标的中文名称"""
        names = {
            "title": "标题",
            "text": "正文内容",
            "content": "正文内容",
            "image": "图片",
        }
        return names.get(target, target)

    async def _handle_modify_request(
        self,
        session: Session,
        intent_result: Dict[str, Any],
    ) -> tuple:
        """处理修改请求"""
        target = intent_result.get("target", "content")
        response = f"好的，你想修改{target}。"

        # 根据不同目标提供建议
        if target in ["title", "text", "content"]:
            response += "\n\n你可以：\n• 直接描述你想要的风格\n• 说「更有趣一些」「更专业一点」\n• 或者给我一个参考示例"
            suggested_actions = ["更有趣", "更专业", "更简短", "更详细"]
        elif target == "image":
            response += "\n\n你想要什么样的图片风格？"
            suggested_actions = ["小清新", "高级感", "生活化", "ins风"]
        else:
            response += "请告诉我具体想要什么样的效果。"
            suggested_actions = []

        return response, suggested_actions

    async def generate_plans(
        self,
        session: Session,
        plan_count: int = 3,
        style_variations: List[str] = None,
    ) -> OrchestratorResult:
        """
        生成多个备选方案供用户选择

        Args:
            session: 会话对象
            plan_count: 生成的方案数量，默认 3 个
            style_variations: 风格变体列表

        Returns:
            OrchestratorResult: 包含多个方案
        """
        wf_logger = get_workflow_logger("orchestrator.generate_plans")
        wf_logger.start("generate_plans")
        logger.info(f"Generating {plan_count} plans for session: {session.session_id}")

        try:
            # 调用 planner 生成多个方案
            plan_results = await self.planner.generate_plans(
                brief=session.brief,
                plan_count=plan_count,
                style_variations=style_variations,
            )

            # 转换为响应格式
            plans = []
            for result in plan_results:
                if result.success and result.plan:
                    plans.append(result.plan.to_dict() if hasattr(result.plan, "to_dict") else dict(result.plan))

            logger.info(f"Generated {len(plans)} plans successfully")
            wf_logger.end("generate_plans", success=True, message=f"count={len(plans)}")

            return OrchestratorResult(
                success=True,
                session=session,
                messages=[f"生成了 {len(plans)} 个备选方案"],
            )

        except Exception as e:
            logger.error(f"generate_plans exception: {e}", exc_info=True)
            wf_logger.error("generate_plans", e)
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"生成方案异常: {str(e)}",
            )

    async def regenerate_plans(
        self,
        session: Session,
        user_feedback: str,
    ) -> OrchestratorResult:
        """
        根据用户反馈重新生成多个方案

        Args:
            session: 会话对象
            user_feedback: 用户反馈/修改需求

        Returns:
            OrchestratorResult: 包含重新生成的多个方案
        """
        wf_logger = get_workflow_logger("orchestrator.regenerate_plans")
        wf_logger.start("regenerate_plans")
        logger.info(f"Regenerating plans for session: {session.session_id}, feedback: {user_feedback[:50]}...")

        try:
            # 1. 调用 planner.generate_plans 生成多个新方案
            plan_results = await self.planner.generate_plans(
                brief=session.brief,
                plan_count=3,
            )

            # 2. 收集方案数据
            plans = []
            for result in plan_results:
                if result.success and result.plan:
                    plans.append(result.plan.to_dict() if hasattr(result.plan, "to_dict") else dict(result.plan))

            # 3. 更新 session 中的当前方案（使用第一个方案）
            if plans:
                session.current_plan = plan_results[0].plan

            logger.info(f"Regenerated {len(plans)} plans successfully")
            wf_logger.end("regenerate_plans", success=True, message=f"count={len(plans)}")

            return OrchestratorResult(
                success=True,
                session=session,
                messages=[
                    f"已根据你的反馈生成 {len(plans)} 个新方案",
                    "请选择一个你喜欢的方案"
                ],
                plans=plans,
            )

        except Exception as e:
            logger.error(f"regenerate_plans exception: {e}", exc_info=True)
            wf_logger.error("regenerate_plans", e)
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"重新生成方案异常: {str(e)}",
            )

    async def modify_plan(
        self,
        session: Session,
        user_feedback: str,
    ) -> OrchestratorResult:
        """
        根据用户反馈直接修改当前方案

        Args:
            session: 会话对象
            user_feedback: 用户修改需求

        Returns:
            OrchestratorResult: 包含修改后的方案
        """
        wf_logger = get_workflow_logger("orchestrator.modify_plan")
        wf_logger.start("modify_plan")
        logger.info(f"Modifying plan for session: {session.session_id}, feedback: {user_feedback[:50]}...")

        try:
            # 1. 调用 planner.modify_plan 生成新方案
            plan_result = await self.planner.modify_plan(session.brief, user_feedback)

            if not plan_result.success or not plan_result.plan:
                logger.warning(f"modify_plan failed: {plan_result.error}")
                wf_logger.end("modify_plan", success=False)
                return OrchestratorResult(
                    success=False,
                    session=session,
                    error=f"修改方案失败: {plan_result.error}",
                )

            # 2. 更新 session 的当前方案
            session.current_plan = plan_result.plan
            logger.info(f"Plan modified successfully: new_title={plan_result.plan.title[:30] if plan_result.plan.title else 'N/A'}...")

            # 3. 发送方案更新事件
            await self._emit_progress(
                session.session_id,
                ProgressEvent(
                    event_type="plan_updated",
                    message=f"方案已更新: {plan_result.plan.title[:20]}..." if plan_result.plan.title else "方案已更新",
                    metadata={
                        "plan_id": plan_result.plan.plan_id,
                        "title": plan_result.plan.title,
                    },
                ),
            )

            wf_logger.end("modify_plan", success=True)
            return OrchestratorResult(
                success=True,
                session=session,
                messages=[
                    "已根据你的反馈修改方案",
                    f"新标题：{plan_result.plan.title}" if plan_result.plan.title else "方案已更新"
                ],
            )

        except Exception as e:
            logger.error(f"modify_plan exception: {e}", exc_info=True)
            wf_logger.error("modify_plan", e)
            return OrchestratorResult(
                success=False,
                session=session,
                error=f"修改方案异常: {str(e)}",
            )

    # ========== 私有方法 ==========

    async def _generate_text(self, session: Session) -> List[ContentItem]:
        """生成文案内容"""
        items = []

        # 构建生成 prompt
        brief = session.brief
        plan = session.current_plan
        total_sections = len([s for s in plan.text_sections if not s.is_optional or brief.need_video])

        for idx, section in enumerate(plan.text_sections):
            if section.is_optional and not brief.need_video:
                continue

            item = ContentItem(
                item_id=section.section_id,
                item_type=ContentType(section.section_type),
                status=ItemStatus.PENDING,
            )

            # Emit generation_start event
            await self._emit_progress(
                session.session_id,
                ProgressEvent.generation_start(
                    item_id=item.item_id,
                    item_type="text",
                    message=f"开始生成 {section.section_type}...",
                ),
            )

            # 构建 prompt
            prompt = self._build_text_prompt(brief, section, session.items)

            try:
                item.status = ItemStatus.GENERATING
                llm_request = LLMRequest(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=800,  # 足够的 token 生成 300-500 字中文内容
                )

                # 使用非流式响应
                response = await self.llm_gateway.invoke(llm_request)
                full_content = response.data.get("content", "") if response.data else ""

                # 去除思考内容（移除 <think>...</think> 块和 "Here's a thinking:" 格式）
                import re
                raw_content = full_content

                # 提取 Final Text: 之后的内容（如果有）
                if 'Final Text:' in raw_content:
                    parts = raw_content.split('Final Text:', 1)
                    if len(parts) > 1:
                        cleaned_content = parts[1].strip()
                        # 去除末尾的 *(Matches...) 等元信息
                        cleaned_content = re.sub(r'\s*\*\(.*?\)\*$', '', cleaned_content, flags=re.DOTALL)
                        cleaned_content = re.sub(r'\s*\(Matches.*', '', cleaned_content, flags=re.DOTALL)
                        cleaned_content = re.sub(r'\s*Output matches.*', '', cleaned_content, flags=re.DOTALL)
                        cleaned_content = re.sub(r'\s*\[Done\.\]\s*$', '', cleaned_content, flags=re.DOTALL)
                        cleaned_content = re.sub(r'\s*✅\s*$', '', cleaned_content, flags=re.DOTALL)
                        cleaned_content = cleaned_content.strip()
                    else:
                        cleaned_content = raw_content.strip()
                else:
                    # 否则尝试去除其他格式的思考内容
                    cleaned_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL)
                    cleaned_content = re.sub(r'Here\'s a thinking:.*?(?=\n\n|\Z)', '', cleaned_content, flags=re.DOTALL)
                    cleaned_content = re.sub(r'\[Output Generation\].*', '', cleaned_content)
                    cleaned_content = re.sub(r'\(Output Generation\).*', '', cleaned_content)
                    cleaned_content = re.sub(r'\(Self-Correction[^)]*\).*', '', cleaned_content)
                    cleaned_content = re.sub(r'\(Note:.*?\)(?=\n|$)', '', cleaned_content)
                    cleaned_content = cleaned_content.strip()

                item.content = cleaned_content
                item.generation_prompt = prompt

                if item.content and len(item.content) > 10:
                    item.status = ItemStatus.COMPLETED
                    logger.debug(f"Text item generated: {section.section_type}, len={len(item.content)}, content={item.content[:50]}...")
                    # 发送完成事件
                    await self._emit_progress(
                        session.session_id,
                        ProgressEvent.token_stream(
                            item_id=item.item_id,
                            token="",
                            done=True,
                        ),
                    )
                    await self._emit_progress(
                        session.session_id,
                        ProgressEvent.generation_complete(
                            item_id=item.item_id,
                            content=item.content[:100] + "..." if len(item.content) > 100 else item.content,
                        ),
                    )
                else:
                    item.status = ItemStatus.FAILED
                    item.error_message = f"Content too short: '{item.content}'"
                    logger.warning(f"Text item FAILED: {section.section_type}, content='{item.content}', len={len(item.content)}")
                    # Emit generation_error event
                    await self._emit_progress(
                        session.session_id,
                        ProgressEvent.generation_error(
                            item_id=item.item_id,
                            error=f"内容过短: {len(item.content)} 字符",
                        ),
                    )
            except Exception as e:
                item.status = ItemStatus.FAILED
                item.error_message = str(e)
                logger.error(f"Text item exception: {section.section_type}, error={e}")
                # Emit generation_error event
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_error(
                        item_id=item.item_id,
                        error=str(e),
                    ),
                )

            except Exception as e:
                item.status = ItemStatus.FAILED
                item.error_message = str(e)
                logger.error(f"Text item exception: {section.section_type}, error={e}")
                # Emit generation_error event
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_error(
                        item_id=item.item_id,
                        error=str(e),
                    ),
                )

            items.append(item)

        return items

    async def _apply_template(self, session: Session, text_items: List[ContentItem], template_url: str) -> Optional[ContentItem]:
        """将文本内容应用到模板图片上"""
        if not text_items:
            logger.warning("No text items to apply to template")
            return None

        # 组合文本内容
        title = ""
        content_parts = []
        hashtags = []

        for item in text_items:
            if item.item_type == ContentType.TITLE:
                title = item.content
            elif item.item_type == ContentType.HEADLINE:
                content_parts.insert(0, item.content)
            elif item.item_type == ContentType.TEXT:
                content_parts.append(item.content)
            elif item.item_type == ContentType.HASHTAG:
                hashtags.append(item.content)
            elif item.item_type == ContentType.CALL_TO_ACTION:
                content_parts.append(item.content)

        # 构建完整的文本内容
        full_text = ""
        if title:
            full_text += f"标题：{title}\n\n"
        if content_parts:
            full_text += "正文：\n" + "\n".join(content_parts) + "\n\n"
        if hashtags:
            full_text += "话题：" + " ".join(hashtags)

        # 创建 ContentItem
        item = ContentItem(
            item_id=f"template_{uuid.uuid4().hex[:8]}",
            item_type=ContentType.COMPOSITE,
            status=ItemStatus.PENDING,
            metadata={"template_url": template_url}
        )

        # 发送进度事件
        await self._emit_progress(
            session.session_id,
            ProgressEvent.generation_start(
                item_id=item.item_id,
                item_type="template",
                message="正在套用模板...",
            ),
        )

        try:
            item.status = ItemStatus.GENERATING

            # 构建视觉编辑 prompt
            prompt = f"""这是一张小红书文案模板图片。
请将模板中的所有文字内容替换为以下新内容：
{full_text}

要求：
1. 保持原有模板图片的布局、样式和装饰元素
2. 移除原来的文字，用新文字替换
3. 新文字的大小、位置、颜色需与原模板保持一致或协调
4. 不要改变图片中的背景、装饰等非文字元素
5. 保持小红书风格的视觉美感"""

            # 调用视觉模型
            vision_request = VisionRequest(
                images=[template_url],
                prompt=prompt,
            )

            response = await self.vision_gateway.invoke(vision_request)

            if response.success:
                images = response.data.get("images", [])
                if images and images[0].get("url"):
                    item.content = images[0].get("url")
                    item.metadata["model_used"] = response.model_used
                    item.metadata["format"] = "url"
                    item.status = ItemStatus.COMPLETED
                    item.generation_prompt = prompt
                    logger.debug(f"Template applied successfully: {item.item_id}")
                else:
                    raise Exception("No image URL in response")
            else:
                raise Exception(response.error or "Vision API failed")

            # 发送完成事件
            await self._emit_progress(
                session.session_id,
                ProgressEvent.generation_complete(
                    item_id=item.item_id,
                    content="模板套用完成",
                ),
            )

            return item

        except Exception as e:
            item.status = ItemStatus.FAILED
            item.error_message = str(e)
            logger.error(f"Template application failed: {e}", exc_info=True)
            await self._emit_progress(
                session.session_id,
                ProgressEvent.generation_error(
                    item_id=item.item_id,
                    error=str(e),
                ),
            )
            return None

    async def _generate_images(self, session: Session) -> List[ContentItem]:
        """生成配图（并行）"""
        if not self.image_gateway:
            logger.warning("Image gateway not available, skipping image generation")
            return []

        brief = session.brief
        plan = session.current_plan
        image_plan = plan.image_plan

        if not image_plan:
            return []

        # Capture session_id for inner function
        session_id = session.session_id

        async def generate_single_image(i: int) -> ContentItem:
            """生成单张图片（异步任务）"""
            item = ContentItem(
                item_id=f"img_{uuid.uuid4().hex[:8]}",
                item_type=ContentType.IMAGE,
                status=ItemStatus.PENDING,
                position=i,
            )

            # Emit generation_start event
            await self._emit_progress(
                session_id,
                ProgressEvent.generation_start(
                    item_id=item.item_id,
                    item_type="image",
                    message=f"开始生成图片 {i + 1}/{image_plan.count}...",
                ),
            )

            prompt = self._build_image_prompt(brief, image_plan, session.items)

            try:
                item.status = ItemStatus.GENERATING
                image_request = ImageGenerationRequest(
                    prompt=prompt,
                    size="1024*1024",
                    n=1,
                )
                response = await self.image_gateway.invoke(image_request)

                if response.success:
                    images = response.data.get("images", [])
                    if images and images[0].get("url"):
                        item.content = images[0].get("url", "")
                        item.metadata = {
                            "model_used": response.model_used,
                            "format": "url",
                        }
                        item.status = ItemStatus.COMPLETED
                        item.generation_prompt = prompt
                        logger.debug(f"Image generated: {item.item_id}, url={item.content[:80]}...")
                        # Emit generation_complete event
                        await self._emit_progress(
                            session_id,
                            ProgressEvent.generation_complete(
                                item_id=item.item_id,
                                content=item.content[:100] + "..." if len(item.content) > 100 else item.content,
                            ),
                        )
                    else:
                        item.status = ItemStatus.FAILED
                        item.error_message = f"No image URL in response: {response.data}"
                        logger.warning(f"Image FAILED: {item.item_id}, no URL in response, data={response.data}")
                        # Emit generation_error event
                        await self._emit_progress(
                            session_id,
                            ProgressEvent.generation_error(
                                item_id=item.item_id,
                                error="No image URL in response",
                            ),
                        )
                else:
                    item.status = ItemStatus.FAILED
                    item.error_message = response.error
                    logger.warning(f"Image FAILED: {item.item_id}, error={response.error}")
                    # Emit generation_error event
                    await self._emit_progress(
                        session_id,
                        ProgressEvent.generation_error(
                            item_id=item.item_id,
                            error=response.error,
                        ),
                    )

            except Exception as e:
                item.status = ItemStatus.FAILED
                item.error_message = str(e)
                logger.error(f"Image exception: {item.item_id}, error={e}")
                # Emit generation_error event
                await self._emit_progress(
                    session_id,
                    ProgressEvent.generation_error(
                        item_id=item.item_id,
                        error=str(e),
                    ),
                )

            return item

        # 并行生成所有图片
        tasks = [generate_single_image(i) for i in range(image_plan.count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        result_items = []
        for r in results:
            if isinstance(r, Exception):
                item = ContentItem(
                    item_id=f"img_{uuid.uuid4().hex[:8]}",
                    item_type=ContentType.IMAGE,
                    status=ItemStatus.FAILED,
                    error_message=str(r),
                )
                result_items.append(item)
            else:
                result_items.append(r)

        return result_items

    def _get_video_gateway(self, model_type: str = "t2v"):
        """获取指定类型的视频网关"""
        from agent.models.gateway_factory import GatewayFactory

        # Debug logging
        logger.debug(f"_get_video_gateway called with model_type={model_type}, config_service={self._config_service is not None}")

        # 如果已有缓存的网关，直接返回
        if model_type in self._video_gateways:
            logger.debug(f"Returning cached gateway for {model_type}")
            return self._video_gateways[model_type]

        # 如果有 config_service，创建新的网关
        if self._config_service:
            gateway = GatewayFactory.get_gateway("video", self._config_service, model_subtype=model_type)
            # 获取网关使用的模型名称用于调试
            try:
                primary_config = gateway._model_config.get("primary", {})
                model_name = primary_config.get("model_name", "unknown")
                logger.debug(f"Created new gateway for {model_type}, model_name={model_name}")
            except Exception:
                logger.debug(f"Created new gateway for {model_type}, could not get model_name")
            self._video_gateways[model_type] = gateway
            return gateway

        # 回退到默认网关
        logger.debug(f"No config_service, using fallback gateway")
        return self._video_gateways.get("default") or self._video_gateways.get("t2v")

    async def _generate_video(self, session: Session) -> List[ContentItem]:
        """生成视频"""
        plan = session.current_plan
        video_plan = plan.video_plan

        if not video_plan:
            return []

        # 获取对应模型类型的视频网关
        model_type = getattr(video_plan, "model_type", "t2v")
        logger.debug(f"_generate_video: video_plan.model_type={getattr(video_plan, 'model_type', 'NOT_SET')}, using model_type={model_type}")
        video_gateway = self._get_video_gateway(model_type)

        if not video_gateway:
            logger.warning(f"No video gateway available for model type: {model_type}")
            return []

        items = []

        item = ContentItem(
            item_id=f"vid_{uuid.uuid4().hex[:8]}",
            item_type=ContentType.VIDEO,
            status=ItemStatus.PENDING,
        )

        # Emit generation_start event
        await self._emit_progress(
            session.session_id,
            ProgressEvent.generation_start(
                item_id=item.item_id,
                item_type="video",
                message=f"开始生成视频 ({model_type})...",
            ),
        )

        # 构建 prompt
        prompt = self._build_video_prompt(session.brief, video_plan)

        # 根据模型类型准备请求参数
        reference_images = []
        video_url = ""

        # 从 session 中提取参考素材
        if session.brief.reference_materials:
            for mat in session.brief.reference_materials:
                if mat.material_type == "image" and mat.url:
                    reference_images.append(mat.url)
                elif mat.material_type == "video" and mat.url:
                    video_url = mat.url

        try:
            item.status = ItemStatus.GENERATING
            video_request = VideoGenerationRequest(
                prompt=prompt,
                duration=video_plan.duration,
                resolution="1080P",
                ratio=getattr(video_plan, "ratio", "16:9"),
                video_url=video_url if model_type == "video-edit" else "",
                reference_images=reference_images if model_type in ("i2v", "r2v", "video-edit") else [],
            )
            response = await video_gateway.invoke(video_request, model_type=model_type)

            if response.success:
                item.content = response.data.get("video_url", "")
                item.metadata = {
                    "model_used": response.model_used,
                    "model_type": model_type,
                    "duration": video_plan.duration,
                }
                item.status = ItemStatus.COMPLETED
                item.generation_prompt = prompt
                # Emit generation_complete event
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_complete(
                        item_id=item.item_id,
                        content=item.content[:100] + "..." if len(item.content) > 100 else item.content,
                    ),
                )
            else:
                item.status = ItemStatus.FAILED
                item.error_message = response.error
                # Emit generation_error event
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_error(
                        item_id=item.item_id,
                        error=response.error,
                    ),
                )

        except Exception as e:
            item.status = ItemStatus.FAILED
            item.error_message = str(e)
            # Emit generation_error event
            await self._emit_progress(
                session.session_id,
                ProgressEvent.generation_error(
                    item_id=item.item_id,
                    error=str(e),
                ),
            )

        items.append(item)
        return items

    async def _generate_audio(self, session: Session) -> List[ContentItem]:
        """生成音频"""
        if not self.tts_gateway:
            return []

        items = []
        plan = session.current_plan
        audio_plan = plan.audio_plan

        if not audio_plan:
            return []

        # 收集正文作为 TTS 文本
        tts_text = ""
        for item in session.items:
            if item.item_type == ContentType.TEXT and item.content:
                tts_text += item.content + "\n"

        item = ContentItem(
            item_id=f"aud_{uuid.uuid4().hex[:8]}",
            item_type=ContentType.AUDIO,
            status=ItemStatus.PENDING,
        )

        # Emit generation_start event
        await self._emit_progress(
            session.session_id,
            ProgressEvent.generation_start(
                item_id=item.item_id,
                item_type="audio",
                message=f"开始生成音频 (voice: {audio_plan.voice})...",
            ),
        )

        try:
            item.status = ItemStatus.GENERATING
            tts_request = TTSRequest(
                input=tts_text or "感谢观看",
                voice_id=audio_plan.voice,
                speed=audio_plan.speed,
            )
            response = await self.tts_gateway.invoke(tts_request)

            if response.success:
                # 将音频 bytes 转换为 base64 编码
                import base64
                audio_bytes = response.data.get("audio", b"")
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
                item.content = f"data:audio/mp3;base64,{audio_base64}"
                item.metadata = {
                    "model_used": response.model_used,
                    "format": audio_plan.voice,
                    "audio_data": audio_base64,
                }
                item.status = ItemStatus.COMPLETED
                # Emit generation_complete event
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_complete(
                        item_id=item.item_id,
                        content=f"音频生成完成 ({len(audio_base64)} bytes)",
                    ),
                )
            else:
                item.status = ItemStatus.FAILED
                item.error_message = response.error
                # Emit generation_error event
                await self._emit_progress(
                    session.session_id,
                    ProgressEvent.generation_error(
                        item_id=item.item_id,
                        error=response.error,
                    ),
                )

        except Exception as e:
            item.status = ItemStatus.FAILED
            item.error_message = str(e)
            # Emit generation_error event
            await self._emit_progress(
                session.session_id,
                ProgressEvent.generation_error(
                    item_id=item.item_id,
                    error=str(e),
                ),
            )

        items.append(item)
        return items

    def _build_text_prompt(
        self,
        brief: Brief,
        section,
        existing_items: List[ContentItem],
    ) -> str:
        """构建文案生成 prompt"""
        # 如果有模板分析，添加模板风格参考
        template_context = ""
        if brief.template_analysis:
            template_context = """
【重要】用户提供了文案模板参考，请按照模板的风格和结构生成内容：
"""
            for i, ta in enumerate(brief.template_analysis):
                analysis = ta.get('analysis', '')
                template_context += f"""
模板 {i+1} 分析结果：
{analysis}
"""

        prompt = f"""请为小红书写一篇{brief.goal.value}风格的文案。
{template_context}
风格要求: {brief.style}
关键词: {', '.join(brief.keywords)}
必须包含: {', '.join(brief.must_include)}
目标受众: {brief.target_audience}

"""

        if section.section_type == "title":
            prompt += "请生成一个吸引人的标题（20字以内）。\n"
        elif section.section_type == "headline":
            prompt += "请生成一个引人注目的开头（50字以内）。\n"
        elif section.section_type == "text":
            prompt += f"请生成正文内容（约{section.content_words}字）。\n"
        elif section.section_type == "hashtag":
            prompt += "请生成 3-5 个相关的话题标签，以 # 开头。\n"
        elif section.section_type == "call_to_action":
            prompt += "请生成互动引导语，激发用户评论和分享。\n"

        # 如果有模板，强调遵循模板风格
        if brief.template_analysis:
            prompt += """
【重点】必须严格遵循模板的风格：
- 标题格式与模板保持一致（如 emoji 使用、疑问句式等）
- 正文的分段方式和长度参考模板
- 语气和表达风格与模板相似
"""

        prompt += "\n只输出文案内容，不要有其他说明。"

        return prompt

    def _build_image_prompt(
        self,
        brief: Brief,
        image_plan,
        existing_items: List[ContentItem],
    ) -> str:
        """构建图像生成 prompt"""
        # 从产品信息中提取视觉描述
        product_desc = brief.extracted_product_info.get("visual_description", "")

        prompt = f"""生成一张小红书风格的配图。

风格: {image_plan.style}
主要元素: {', '.join(image_plan.elements)}

"""

        if product_desc:
            prompt += f"产品外观: {product_desc}\n"

        prompt += "\n要求：画面精美，符合小红书美学风格。"

        return prompt

    def _build_video_prompt(self, brief: Brief, video_plan) -> str:
        """构建视频生成 prompt"""
        scenes_desc = "\n".join([
            f"- {s.get('description', s.get('visual_prompt', ''))}"
            for s in video_plan.scenes
        ])

        prompt = f"""生成一段短视频。

时长: {video_plan.duration} 秒
风格: {video_plan.style}
旁白: {video_plan.voiceover}

场景描述:
{scenes_desc}

"""

        return prompt

    async def _save_content_to_local(self, session: Session, version: int = None):
        """
        保存会话中的媒体内容到本地文件

        Args:
            session: 会话对象
            version: 版本号（可选），为 None 时保存到 current 目录
        """
        if not self.content_store:
            return

        for item in session.items:
            if not item.content:
                continue

            # 确定内容类型
            content_type = None
            if item.item_type == ContentType.IMAGE:
                content_type = "image"
            elif item.item_type == ContentType.VIDEO:
                content_type = "video"
            elif item.item_type == ContentType.AUDIO:
                content_type = "audio"

            if content_type:
                # 保存到本地
                local_path = await self.content_store.save_content(
                    session.session_id,
                    item.item_id,
                    item.content,
                    content_type,
                    version,
                )
                if local_path:
                    item.local_path = local_path
                    item.metadata["local_path"] = local_path

        # 保存版本快照到文件
        if version:
            items_data = [item.to_dict() for item in session.items]
            self.content_store.save_items_snapshot(
                session.session_id, items_data, version
            )
            if hasattr(session.current_plan, "to_dict"):
                plan_data = session.current_plan.to_dict()
            else:
                plan_data = dict(session.current_plan)
            self.content_store.save_plan_snapshot(
                session.session_id, plan_data, version
            )

    async def preview_text(self, plan: "ContentPlan") -> Dict[str, Any]:
        """
        根据方案快速生成预览文案

        用于在方案预览阶段快速生成文案内容，让用户提前看到文案效果

        Args:
            plan: 内容方案

        Returns:
            Dict containing title and text_sections
        """
        plan_id = plan.get('plan_id') if isinstance(plan, dict) else getattr(plan, 'plan_id', 'unknown')
        logger.debug(f"preview_text called for plan: {plan_id}")

        try:
            # 直接构建 prompt 用于预览生成
            from ..models.brief import Brief

            # 从 plan 中提取信息来构建 brief
            plan_dict = plan if isinstance(plan, dict) else vars(plan) if hasattr(plan, '__dict__') else {}
            brief = Brief(
                id=plan_dict.get('brief_id', ''),
                goal=plan_dict.get('goal', 'lifestyle'),
                style=plan_dict.get('style', '活泼'),
                keywords=plan_dict.get('keywords', []),
                must_include=plan_dict.get('must_include', []),
                image_style=plan_dict.get('image_style', ''),
                need_video=False,
                need_voiceover=False,
                need_text=True,
                need_images=False,
                raw_input=plan_dict.get('title', ''),
            )

            # 如果 plan 有 template_analysis，也添加到 brief
            if 'template_analysis' in plan_dict:
                brief.template_analysis = plan_dict['template_analysis']

            # 构建预览文案 prompt
            template_context = ""
            if brief.template_analysis:
                template_context = "\n\n【重要】用户提供了文案模板参考，请按照模板的风格和结构生成内容。"

            prompt = f"""请为小红书生成文案。

目标：{brief.goal}
风格：{brief.style}
关键词：{', '.join(brief.keywords) if brief.keywords else '无'}{template_context}

请生成以下结构的文案：
1. 一个吸引人的标题（20字以内）
2. 若干个小标题（用于分段）
3. 正文内容（每段2-3句话）
4. 话题标签（3-5个）

要求：
- 标题要吸引眼球，引发好奇
- 正文要生动有趣，有画面感
- 语言风格要符合小红书调性
- 话题标签要相关且有热度

请直接输出文案内容，格式如下：
Title: [标题]
Headline: [小标题1]
Text: [正文内容1]
Hashtag: [话题标签]
"""

            # 调用 LLM 生成文案（轻量级，使用更少的迭代）
            request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                model=self.config.fast_model if hasattr(self.config, 'fast_model') else None,
                temperature=0.7,
            )

            response = await self.llm_gateway.invoke(request)

            if not response.success:
                logger.warning(f"preview_text LLM failed: {response.error}")
                return {
                    "success": False,
                    "title": "",
                    "text_sections": [],
                    "error": response.error,
                }

            # 解析生成的文案
            import re
            raw_content = response.data.get("content", "") if response.data else ""

            # 提取标题（第一个 # 开头或 Title: 开头的内容）
            title = ""
            title_match = re.search(r'^#?\s*Title[:：]\s*(.+)$', raw_content, re.MULTILINE | re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # 尝试提取第一行作为标题
                lines = [l.strip() for l in raw_content.split('\n') if l.strip()]
                if lines:
                    title = lines[0].strip('# ')

            # 提取各片段内容
            text_sections = []
            section_pattern = re.compile(
                r'(?:^|\n)(#{0,3})\s*(Title|Title|Headline|headline|Text|text|Hashtag|hashtag|CTA|cta)[：:]\s*(.+?)(?=(?:\n#{0,3}\s*(?:Title|Headline|Text|Hashtag|CTA|$))|\Z)',
                re.DOTALL | re.IGNORECASE
            )

            current_pos = 0
            for match in section_pattern.finditer(raw_content):
                section_type = match.group(2).lower()
                content = match.group(3).strip()

                # 清理内容中的思考标记
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                content = re.sub(r'Here\'s a thinking:.*?(?=\n\n|\Z)', '', content, flags=re.DOTALL)

                if content and len(content) > 5:
                    # 标准化 section_type
                    type_mapping = {
                        'title': 'title',
                        'headline': 'headline',
                        'text': 'text',
                        'hashtag': 'hashtag',
                        'cta': 'cta',
                    }
                    normalized_type = type_mapping.get(section_type, 'text')

                    text_sections.append({
                        "section_id": f"preview_{uuid.uuid4().hex[:8]}",
                        "section_type": normalized_type,
                        "content": content,
                        "content_words": len(content),
                    })

            logger.debug(f"preview_text generated: title={title}, sections={len(text_sections)}")
            return {
                "success": True,
                "title": title,
                "text_sections": text_sections,
            }

        except Exception as e:
            logger.error(f"preview_text exception: {e}", exc_info=True)
            return {
                "success": False,
                "title": "",
                "text_sections": [],
                "error": str(e),
            }

    def _is_likely_base64(self, text: str) -> bool:
        """
        判断字符串是否可能是纯 base64 数据（而不是文件路径或 URL）

        Args:
            text: 待检测的字符串

        Returns:
            bool: 如果看起来像 base64 数据返回 True
        """
        if not text or len(text) < 50:
            return False
        # base64 字符集：字母、数字、+、/、=
        # 如果包含大量换行符或特殊字符（如中文），就不是 base64
        if '\n' in text or '\r' in text:
            return False
        # 检查是否主要是 base64 字符
        base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        char_count = sum(1 for c in text if c in base64_chars)
        return char_count / len(text) > 0.9

    async def preview_template(
        self,
        text_items: List["ContentItem"],
        template_url: str
    ) -> Dict[str, Any]:
        """
        将文案预览渲染到模板图片上

        用于在方案预览阶段快速生成模板预览图，让用户提前看到文案+模板效果

        Args:
            text_items: 文案内容项列表
            template_url: 模板图片 URL

        Returns:
            Dict containing preview_image_url
        """

        if not text_items:
            return {
                "success": False,
                "preview_image_url": None,
                "error": "No text items provided",
            }

        if not template_url:
            return {
                "success": False,
                "preview_image_url": None,
                "error": "No template URL provided",
            }

        try:
            # 组合文本内容
            title = ""
            content_parts = []
            hashtags = []

            for item in text_items:
                if item.item_type == ContentType.TITLE:
                    title = item.content
                elif item.item_type == ContentType.HEADLINE:
                    content_parts.insert(0, item.content)
                elif item.item_type == ContentType.TEXT:
                    content_parts.append(item.content)
                elif item.item_type == ContentType.HASHTAG:
                    hashtags.append(item.content)
                elif item.item_type == ContentType.CALL_TO_ACTION:
                    content_parts.append(item.content)

            # 构建完整的文本内容
            full_text = ""
            if title:
                full_text += f"标题：{title}\n\n"
            if content_parts:
                full_text += "正文：\n" + "\n".join(content_parts) + "\n\n"
            if hashtags:
                full_text += "话题：" + " ".join(hashtags)

            template_url_short = template_url[template_url.find("//")+2:] if "//" in template_url else template_url
            logger.info(f"preview_template: built full_text length={len(full_text)}, template_url_path={template_url_short}")

            # 构建视觉编辑 prompt
            prompt = f"""这是一张小红书文案模板图片。
请将模板中的所有文字内容替换为以下新内容：
{full_text}

要求：
1. 保持原有模板图片的布局、样式和装饰元素
2. 移除原来的文字，用新文字替换
3. 新文字的大小、位置、颜色需与原模板保持一致或协调
4. 不要改变图片中的背景、装饰等非文字元素
5. 保持小红书风格的视觉美感"""

            # 使用 qwen-image-2.0-pro 进行图片编辑
            if not self.image_gateway or not self.image_gateway._primary_provider:
                logger.error("preview_template: image_gateway or _primary_provider is None")
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": "Image generation gateway not available",
                }

            provider = self.image_gateway._primary_provider
            api_url = provider.api_url
            api_key = provider.api_key
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            logger.info(f"preview_template: provider={provider.__class__.__name__}, api_url={api_url}, model={provider.model_name}")

            if not api_url or not api_key:
                logger.error(f"preview_template: missing api_url={bool(api_url)} or api_key={bool(api_key)}")
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": "Missing API configuration",
                }

            # 如果 template_url 是本地文件路径，读取并转为 base64
            # 否则作为 URL 获取
            try:
                if template_url.startswith("data:"):
                    # 已经是 data URL，直接使用
                    image_data_url = template_url
                elif template_url.startswith("http://") or template_url.startswith("https://"):
                    # 是 URL，获取图片内容
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(template_url)
                        if resp.status_code != 200:
                            return {
                                "success": False,
                                "preview_image_url": None,
                                "error": f"Failed to fetch template image: {resp.status_code}",
                            }
                        image_bytes = resp.content
                        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                        # 推断 MIME 类型
                        content_type = resp.headers.get("content-type", "image/png")
                        image_data_url = f"data:{content_type};base64,{image_base64}"
                elif self._is_likely_base64(template_url):
                    # 纯 base64 数据（没有 data: 前缀），转换为 data URL
                    logger.debug(f"Detected pure base64 data, converting to data URL")
                    image_data_url = f"data:image/png;base64,{template_url}"
                else:
                    # 本地文件路径
                    with open(template_url, "rb") as f:
                        image_bytes = f.read()
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    image_data_url = f"data:image/png;base64,{image_base64}"
            except Exception as e:
                logger.warning(f"preview_template: failed to load template image: {e}")
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": f"Failed to load template image: {str(e)}",
                }

            # 构建图像编辑请求，使用配置中的模型
            data = {
                "model": provider.model_name,
                "input": {
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"image": image_data_url},
                            {"text": prompt}
                        ]
                    }]
                },
                "parameters": {
                    "n": 1,
                    "prompt_extend": True,
                    "watermark": False,
                    "size": "2048*2048"
                }
            }

            try:
                logger.info(f"preview_template: calling API with model={provider.model_name}, prompt_length={len(prompt)}, image_data_url_length={len(image_data_url)}")
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(api_url, json=data, headers=headers)
                    logger.info(f"preview_template: API response status={response.status_code}")

                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"preview_template: result keys={list(result.keys()) if isinstance(result, dict) else 'not dict'}")
                        choices = result.get("output", {}).get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content", [])
                            for item in content:
                                if isinstance(item, dict) and "image" in item:
                                    logger.info(f"preview_template: success, image_url length={len(item['image'])}")
                                    return {
                                        "success": True,
                                        "preview_image_url": item["image"],
                                    }

                        logger.warning(f"preview_template: no image in response, choices={choices}")
                        return {
                            "success": False,
                            "preview_image_url": None,
                            "error": "No image URL in response from model",
                        }
                    elif response.status_code == 401:
                        logger.error(f"preview_template: authentication failed")
                        return {
                            "success": False,
                            "preview_image_url": None,
                            "error": "Authentication failed. Check your API key.",
                        }
                    elif response.status_code == 429:
                        logger.error(f"preview_template: rate limit exceeded")
                        return {
                            "success": False,
                            "preview_image_url": None,
                            "error": "Rate limit exceeded. Please try again later.",
                        }
                    else:
                        error_msg = response.text[:500] if response.text else "Unknown error"
                        logger.error(f"preview_template: API error {response.status_code}: {error_msg}")
                        return {
                            "success": False,
                            "preview_image_url": None,
                            "error": f"API error {response.status_code}: {error_msg}",
                        }
            except httpx.TimeoutException:
                logger.error(f"preview_template: request timeout")
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": "Request timeout",
                }
            except Exception as e:
                logger.error(f"preview_template: exception during API call: {e}", exc_info=True)
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": str(e),
                }

        except Exception as e:
            logger.error(f"preview_template exception: {e}", exc_info=True)
            return {
                "success": False,
                "preview_image_url": None,
                "error": str(e),
            }

    async def generate_template_preview(
        self,
        session: "Session",
        session_store=None,
        text_items: List["ContentItem"] = None,
    ) -> Dict[str, Any]:
        """
        生成文案模板预览（整合 preview_text 和 preview_template）

        Args:
            session: 会话对象
            session_store: 可选的 session_store，用于保存预览图 URL 到会话 metadata
            text_items: 可选的预生成文案项列表。如果提供，则跳过文案生成直接渲染模板。

        Returns:
            Dict containing preview_image_url, title, text_sections
        """
        try:
            # 1. 检查是否有模板图片
            template_url = session.brief.template_image_url if session.brief else None
            if not template_url:
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": "没有文案模板图片",
                }

            # 2. 检查是否有方案或预生成的文案
            if not text_items:
                if not session.current_plan:
                    return {
                        "success": False,
                        "preview_image_url": None,
                        "error": "没有可用的方案",
                    }

                # 3. 调用 preview_text 生成文案内容
                plan_data = session.current_plan.to_dict() if hasattr(session.current_plan, 'to_dict') else dict(session.current_plan)
                text_result = await self.preview_text(plan_data)

                if not text_result.get("success"):
                    return {
                        "success": False,
                        "preview_image_url": None,
                        "error": text_result.get("error", "生成文案预览失败"),
                    }

                # 4. 构建 ContentItem 列表
                from ..models.content_item import ContentItem, ContentType
                text_items = []
                for section in text_result.get("text_sections", []):
                    section_type = section.get("section_type", "text")
                    content = section.get("content", "")

                    # 映射 section_type 到 ContentType
                    type_mapping = {
                        "headline": ContentType.HEADLINE,
                        "title": ContentType.TITLE,
                        "text": ContentType.TEXT,
                        "hashtag": ContentType.HASHTAG,
                        "cta": ContentType.CALL_TO_ACTION,
                    }
                    content_type = type_mapping.get(section_type, ContentType.TEXT)

                    text_items.append(ContentItem(
                        item_id=section.get("section_id", f"item_{uuid.uuid4().hex[:8]}"),
                        item_type=content_type,
                        content=content,
                        metadata={},
                        status="pending",
                        generation_prompt="",
                        position=0,
                    ))
            else:
                # 使用预生成的文案项，设置默认的 text_result
                text_result = {"title": "", "text_sections": []}

            # 5. 调用 preview_template 生成渲染预览
            template_result = await self.preview_template(text_items, template_url)

            if not template_result.get("success"):
                return {
                    "success": False,
                    "preview_image_url": None,
                    "error": template_result.get("error", "生成模板预览失败"),
                }

            # 6. 将预览图 URL 保存到会话 metadata
            preview_image_url = template_result.get("preview_image_url")
            if preview_image_url and session_store:
                try:
                    if not hasattr(session, 'metadata') or not session.metadata:
                        session.metadata = {}
                    session.metadata['preview_image_url'] = preview_image_url
                    session.metadata['preview_title'] = text_result.get('title', '')
                    session.metadata['preview_text_sections'] = text_result.get('text_sections', [])
                    await session_store.save(session)
                except Exception as e:
                    logger.warning(f"generate_template_preview: failed to save to session: {e}")

            # 7. 返回结果
            return {
                "success": True,
                "preview_image_url": template_result.get("preview_image_url"),
                "title": text_result.get("title", ""),
                "text_sections": text_result.get("text_sections", []),
            }

        except Exception as e:
            logger.error(f"generate_template_preview exception: {e}", exc_info=True)
            return {
                "success": False,
                "preview_image_url": None,
                "error": str(e),
            }

    # ========== CanvasSession 管理 ==========

    async def create_canvas_session(
        self,
        canvas_id: str,
        user_id: str,
    ) -> "CanvasSession":
        """
        创建画板会话

        Args:
            canvas_id: 画板ID
            user_id: 用户ID

        Returns:
            CanvasSession: 新创建的画板会话
        """
        from ..canvas.canvas_agent import CanvasSession as CanvasSessionClass

        session_id = str(uuid.uuid4())
        session = CanvasSessionClass(
            session_id=session_id,
            canvas_id=canvas_id,
            user_id=user_id,
        )

        # 存储会话
        if not hasattr(self, '_canvas_sessions'):
            self._canvas_sessions: Dict[str, "CanvasSessionClass"] = {}

        self._canvas_sessions[session_id] = session

        logger.info(f"Created canvas session: {session_id} for canvas {canvas_id}")
        return session

    async def get_canvas_session(self, session_id: str) -> Optional["CanvasSession"]:
        """
        获取画板会话

        Args:
            session_id: 会话ID

        Returns:
            CanvasSession 或 None
        """
        if not hasattr(self, '_canvas_sessions'):
            self._canvas_sessions: Dict[str, "CanvasSession"] = {}

        return self._canvas_sessions.get(session_id)

    async def close_canvas_session(self, session_id: str) -> bool:
        """
        关闭画板会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否成功关闭
        """
        if not hasattr(self, '_canvas_sessions'):
            self._canvas_sessions: Dict[str, "CanvasSession"] = {}

        if session_id in self._canvas_sessions:
            del self._canvas_sessions[session_id]
            logger.info(f"Closed canvas session: {session_id}")
            return True

        return False

    async def list_canvas_sessions(self, user_id: Optional[str] = None) -> List["CanvasSession"]:
        """
        列出画板会话

        Args:
            user_id: 可选的用户ID过滤

        Returns:
            CanvasSession 列表
        """
        if not hasattr(self, '_canvas_sessions'):
            self._canvas_sessions: Dict[str, "CanvasSession"] = {}

        sessions = list(self._canvas_sessions.values())

        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]

        return sessions

    def get_canvas_agent(
        self,
        canvas_core,
        max_steps: int = 10,
    ) -> "CanvasAgent":
        """
        获取 CanvasAgent 实例

        Args:
            canvas_core: 画板核心实例
            max_steps: 最大 ReAct 循环步数

        Returns:
            CanvasAgent 实例
        """
        from ..canvas.canvas_agent import CanvasAgent, LLMGatewayAdapter

        # 创建 LLM 适配器
        llm_adapter = LLMGatewayAdapter(self.llm_gateway)

        # 创建 CanvasAgent
        agent = CanvasAgent(
            llm_client=llm_adapter,
            canvas_core=canvas_core,
            orchestrator=self,
            max_steps=max_steps,
        )

        return agent

    def get_canvas_agent_bridge(
        self,
        canvas_core,
        agent: "CanvasAgent",
        throttle_ms: int = 100,
    ) -> "CanvasAgentBridge":
        """
        获取 CanvasAgentBridge 实例

        Args:
            canvas_core: 画板核心实例
            agent: CanvasAgent 实例
            throttle_ms: 节流时间（毫秒）

        Returns:
            CanvasAgentBridge 实例
        """
        from ..canvas.canvas_agent_bridge import CanvasAgentBridge

        bridge = CanvasAgentBridge(
            canvas_core=canvas_core,
            agent=agent,
            throttle_ms=throttle_ms,
        )

        return bridge
