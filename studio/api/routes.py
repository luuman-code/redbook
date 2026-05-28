"""
API Routes - FastAPI 路由定义
"""

from typing import Any, Dict, List
from pathlib import Path
import base64

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from .websocket_manager import get_websocket_manager, ProgressEvent
from .schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    GenerateRequest,
    GenerateResponse,
    FeedbackRequest,
    FeedbackResponse,
    PublishRequest,
    PublishResponse,
    SessionResponse,
    ReviewResponse,
    ContentItemSchema,
    GeneratePlansRequest,
    GeneratePlansResponse,
    ChatRequest,
    ChatResponse,
    AgentChatRequest,
    AgentChatResponse,
    PreviewTextResponse,
    PreviewTemplateResponse,
)

from ..models.session import SessionStatus
from ..debug_logger import get_logger, get_workflow_logger

# 获取日志记录器
logger = get_logger("routes")

# 导入 storage（将在 main.py 中注入）
_session_store = None


def get_session_store():
    """获取会话存储（需要先设置）- 使用 session_store.py 中的单例"""
    global _session_store
    if _session_store is None:
        from ..storage.session_store import get_session_store as _get_store
        _session_store = _get_store()
    return _session_store


def set_session_store(store):
    """设置会话存储"""
    global _session_store
    _session_store = store


# 导入 orchestrator（将在 main.py 中设置）
_orchestrator = None


def get_orchestrator():
    """获取 orchestrator"""
    global _orchestrator
    if _orchestrator is None:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    return _orchestrator


def set_orchestrator(orchestrator):
    """设置 orchestrator"""
    global _orchestrator
    _orchestrator = orchestrator


router = APIRouter(prefix="/api/studio", tags=["studio"])


# WebSocket endpoint for real-time progress
@router.websocket("/ws/studio/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time progress updates.

    Clients connect to receive progress events during content generation.
    """
    ws_manager = get_websocket_manager()
    await ws_manager.connect(websocket, session_id)
    logger.info(f"WebSocket connection established: session_id={session_id}")

    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Echo back or handle client messages if needed
            logger.debug(f"Received WebSocket message from {session_id}: {data}")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, session_id)
        logger.info(f"WebSocket disconnected: session_id={session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: session_id={session_id}, error={e}")
        await ws_manager.disconnect(websocket, session_id)


# WebSocket endpoint at /api/studio/sessions/{session_id}/progress (matching frontend expectation)
@router.websocket("/sessions/{session_id}/progress")
async def websocket_progress_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time progress updates at the path expected by the frontend.

    This is an alias for /ws/studio/{session_id} to match frontend conventions.
    Clients connect to receive progress events during content generation.

    Event types sent to client:
    - item_start: When an item generation starts
    - item_complete: When an item generation completes
    - item_error: When an item generation fails
    - progress: General progress updates
    - complete: When all generation is complete
    """
    ws_manager = get_websocket_manager()
    await ws_manager.connect(websocket, session_id)
    logger.info(f"WebSocket progress connection established: session_id={session_id}")

    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message from {session_id}: {data}")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, session_id)
        logger.info(f"WebSocket progress disconnected: session_id={session_id}")
    except Exception as e:
        logger.error(f"WebSocket progress error: session_id={session_id}, error={e}")
        await ws_manager.disconnect(websocket, session_id)


@router.get("/sessions")
async def list_sessions(
    store=Depends(get_session_store),
):
    """
    列出所有会话

    返回会话概要列表（不含完整内容）
    """
    wf_logger = get_workflow_logger("list_sessions")
    wf_logger.start("list_sessions")

    try:
        session_ids = await store.list()
        logger.debug(f"Found {len(session_ids)} session IDs")

        sessions = []
        for session_id in session_ids:
            session = await store.get(session_id)
            if session:
                sessions.append({
                    "session_id": session.session_id,
                    "status": session.status.value if hasattr(session.status, "value") else str(session.status),
                    "current_version": session.current_version,
                    "brief": session.brief.to_dict() if hasattr(session.brief, "to_dict") else session.brief,
                    "created_at": session.created_at.isoformat() if hasattr(session.created_at, "isoformat") else session.created_at,
                    "updated_at": session.updated_at.isoformat() if hasattr(session.updated_at, "isoformat") else session.updated_at,
                })

        # 按创建时间倒序排列
        sessions.sort(key=lambda x: x["created_at"], reverse=True)

        logger.info(f"返回 {len(sessions)} 个会话")
        wf_logger.end("list_sessions", success=True, message=f"total={len(sessions)}")

        return {
            "sessions": sessions,
            "total": len(sessions),
        }
    except Exception as e:
        logger.error(f"list_sessions failed: {e}", exc_info=True)
        wf_logger.error("list_sessions", e)
        raise


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    创建新会话

    1. 解析用户需求
    2. 生成内容方案
    3. 创建会话
    """
    wf_logger = get_workflow_logger("create_session")
    wf_logger.start("create_session")
    logger.info(f"create_session called with user_input: {request.user_input[:100]}...")

    try:
        # 转换素材
        materials = [
            {
                "type": m.type,
                "url": m.url,
                "content": m.content,
            }
            for m in request.materials
        ]
        logger.debug(f"Materials count: {len(materials)}")

        # 调用 orchestrator 创建会话
        logger.debug("Calling orchestrator.create_session...")
        result = await orchestrator.create_session(
            user_input=request.user_input,
            materials=materials,
            user_context=request.user_context,
            auto_generate=request.auto_generate,
        )
        logger.debug(f"orchestrator.create_session returned: success={result.success}")

        if result.success and result.session:
            # 保存会话
            logger.debug(f"Saving session: {result.session.session_id}")
            await store.save(result.session)
            logger.info(f"Session created successfully: {result.session.session_id}")

            # 如果 auto_generate=True，自动生成内容
            if request.auto_generate:
                logger.debug("Auto-generating content...")
                # 更新状态为已确认
                result.session.update_status(SessionStatus.CONFIRMED)
                await store.save(result.session)

                # 调用生成
                gen_result = await orchestrator.generate(result.session)
                if gen_result.success:
                    await store.save(result.session)
                    logger.info(f"Auto-generation completed: {len(result.session.items)} items")
                    wf_logger.end("create_session", success=True, message=f"session_id={result.session.session_id}, items={len(result.session.items)}")

                    return CreateSessionResponse(
                        success=True,
                        session_id=result.session.session_id,
                        brief_id=result.session.brief.id,
                        plan_id=result.session.current_plan.plan_id,
                        messages=gen_result.messages + [f"生成完成 ({len(result.session.items)} 项内容)"],
                    )
                else:
                    logger.warning(f"Auto-generation failed: {gen_result.error}")
                    wf_logger.end("create_session", success=False, message=gen_result.error)
                    return CreateSessionResponse(
                        success=False,
                        session_id=result.session.session_id,
                        error=f"生成失败: {gen_result.error}",
                        messages=gen_result.messages,
                    )

            wf_logger.end("create_session", success=True, message=f"session_id={result.session.session_id}")

            return CreateSessionResponse(
                success=True,
                session_id=result.session.session_id,
                brief_id=result.session.brief.id,
                plan_id=result.session.current_plan.plan_id if result.session.current_plan else None,
                messages=result.messages,
            )
        else:
            logger.warning(f"create_session failed: {result.error}")
            wf_logger.end("create_session", success=False, message=result.error)

            return CreateSessionResponse(
                success=False,
                error=result.error,
                messages=result.messages,
            )
    except Exception as e:
        logger.error(f"create_session exception: {e}", exc_info=True)
        wf_logger.error("create_session", e)
        raise


@router.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat_no_session(
    request: AgentChatRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    直接使用 Agent 处理用户消息，无需预先创建会话

    用户发送消息后，Agent 自动完成：
    1. 调用 create_session 工具创建会话
    2. 继续对话（根据需要调用更多工具）

    这是纯粹的 Agent 对话模式，移除了前端 UI 的表单流程。
    所有方案数据与前端 UI 模式一致（plan_data 完整结构）。
    """
    wf_logger = get_workflow_logger("agent_chat_no_session")
    wf_logger.start("agent_chat_no_session")
    logger.info(f"agent_chat_no_session called with message: {request.message[:50]}...")

    try:
        # 初始化 Agent（如需要）
        if not hasattr(orchestrator, '_agent'):
            orchestrator._agent = await orchestrator.init_agent()
            logger.info("Agent initialized for agent_chat_no_session")

        # 构造用户消息
        user_message = request.message

        # 由于没有 session_id，需要先创建一个临时会话来让 Agent 处理
        # Agent 的 system prompt 会让它调用 create_session 工具

        # 先创建一个临时会话（状态为 CREATED），让 Agent 可以处理
        from ..core.orchestrator import OrchestratorResult
        import uuid

        # 创建临时会话
        temp_session_id = str(uuid.uuid4())
        temp_session = None

        # 尝试让 Agent 处理消息
        # Agent 会在内部调用 create_session 工具
        result = await orchestrator.chat_with_agent_only(
            user_message=user_message,
            materials=request.materials,
        )

        if result["success"]:
            session = result.get("session")
            session_id = session.session_id if session else temp_session_id
            messages = result.get("messages", [])
            plan_data = result.get("plan_data")
            preview_image_url = result.get("preview_image_url")
            preview_title = result.get("preview_title")
            preview_text_sections = result.get("preview_text_sections")

            logger.info(f"Agent chat result: session={session}, session_id={session_id}, plan_data_title={plan_data.get('title') if plan_data else None}, preview_image_url={preview_image_url[:50] if preview_image_url else None}")

            # 保存会话
            if session:
                await store.save(session)
                logger.info(f"Session saved to store: {session.session_id}")
            else:
                logger.warning(f"Session is None, not saved! temp_session_id={temp_session_id}")

            logger.info(f"Agent chat processed successfully, session_id: {session_id}")
            wf_logger.end("agent_chat_no_session", success=True)

            return AgentChatResponse(
                success=True,
                session_id=session_id,
                messages=messages,
                plan_data=plan_data,
                preview_image_url=preview_image_url,
                preview_title=preview_title,
                preview_text_sections=preview_text_sections,
            )
        else:
            logger.warning(f"Agent chat failed: {result.get('error')}")
            wf_logger.end("agent_chat_no_session", success=False)

            return AgentChatResponse(
                success=False,
                session_id=None,
                messages=result.get("messages", []),
                error=result.get("error"),
            )
    except Exception as e:
        logger.error(f"agent_chat_no_session exception: {e}", exc_info=True)
        wf_logger.error("agent_chat_no_session", e)
        raise


@router.post("/sessions/{session_id}/confirm-plan")
async def confirm_plan(
    session_id: str,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """确认内容方案"""
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await orchestrator.confirm_plan(session)

    if result.success:
        await store.save(session)
        return {"success": True, "session_id": session_id, "messages": result.messages}
    else:
        return {"success": False, "error": result.error}


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: str,
    request: ChatRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    处理聊天消息，实现实时交互式需求理解

    1. 接收用户消息
    2. 解析意图
    3. 返回 AI 回复
    """
    wf_logger = get_workflow_logger("chat")
    wf_logger.start("chat")
    logger.info(f"chat called for session: {session_id}, message: {request.message[:50]}...")

    try:
        session = await store.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # 转换素材
        materials = [
            {
                "type": m.type,
                "url": m.url,
                "content": m.content,
            }
            for m in request.materials
        ]
        logger.debug(f"Chat materials count: {len(materials)}")

        result = await orchestrator.chat(session, request.message, materials)

        # 提取 plan_data 从 session
        plan_data = None
        if session.current_plan:
            if hasattr(session.current_plan, 'to_dict'):
                plan_data = session.current_plan.to_dict()
            else:
                plan_data = dict(session.current_plan)
            logger.info(f"plan_data extracted from session: title={plan_data.get('title') if plan_data else 'N/A'}")

        if result.success:
            await store.save(session)
            logger.info(f"Chat processed successfully for session: {session_id}")
            wf_logger.end("chat", success=True)

            return ChatResponse(
                success=True,
                session_id=session_id,
                messages=result.messages,
                plan_data=plan_data,
            )
        else:
            logger.warning(f"Chat failed for session: {session_id}, error: {result.error}")
            wf_logger.end("chat", success=False, message=result.error)

            return ChatResponse(
                success=False,
                session_id=session_id,
                messages=result.messages,
                plan_data=plan_data,
                error=result.error,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"chat exception: {e}", exc_info=True)
        wf_logger.error("chat", e)
        raise


@router.post("/sessions/{session_id}/agent-chat", response_model=ChatResponse)
async def agent_chat(
    session_id: str,
    request: ChatRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    使用 LLM Agent 处理聊天消息

    这是 /chat 端点的 Agent 版本，使用 LLM 驱动的意图识别。
    """
    wf_logger = get_workflow_logger("agent_chat")
    wf_logger.start("agent_chat")
    logger.info(f"agent_chat called for session: {session_id}, message: {request.message[:50]}...")

    try:
        session = await store.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # 初始化 Agent（如需要）
        if not hasattr(orchestrator, '_agent'):
            orchestrator._agent = await orchestrator.init_agent()

        result = await orchestrator._agent.chat(session, request.message)

        if result["success"]:
            await store.save(session)
            logger.info(f"Agent chat processed successfully for session: {session_id}")
            wf_logger.end("agent_chat", success=True)

            return ChatResponse(
                success=True,
                session_id=session_id,
                messages=result["messages"],
            )
        else:
            logger.warning(f"Agent chat failed for session: {session_id}")
            wf_logger.end("agent_chat", success=False)

            return ChatResponse(
                success=False,
                session_id=session_id,
                messages=result["messages"],
                error=result.get("error"),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"agent_chat exception: {e}", exc_info=True)
        wf_logger.error("agent_chat", e)
        raise


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    store=Depends(get_session_store),
):
    """
    获取会话的消息历史
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "messages": [
            msg.to_dict() if hasattr(msg, "to_dict") else msg
            for msg in session.messages
        ],
    }


@router.post("/sessions/{session_id}/generate-plans", response_model=GeneratePlansResponse)
async def generate_plans(
    session_id: str,
    request: GeneratePlansRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    生成多个备选方案供用户选择

    生成不同风格变体的内容方案，如：
    - 种草风格
    - 教程风格
    - 测评风格
    """
    wf_logger = get_workflow_logger("generate_plans")
    wf_logger.start("generate_plans")
    logger.info(f"generate_plans called for session: {session_id}, plan_count: {request.plan_count}")

    try:
        session = await store.get(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        # 调用 orchestrator 生成多个方案
        result = await orchestrator.generate_plans(
            session=session,
            plan_count=request.plan_count,
            style_variations=request.style_variations,
        )

        if result.success:
            logger.info(f"Generated {request.plan_count} plans successfully")
            wf_logger.end("generate_plans", success=True, message=f"count={request.plan_count}")

            # 从 planner 获取方案列表
            plan_results = await orchestrator.planner.generate_plans(
                brief=session.brief,
                plan_count=request.plan_count,
                style_variations=request.style_variations,
            )

            plans = []
            for pr in plan_results:
                if pr.success and pr.plan:
                    plans.append(pr.plan.to_dict() if hasattr(pr.plan, "to_dict") else dict(pr.plan))

            return GeneratePlansResponse(
                success=True,
                session_id=session_id,
                plans=plans,
                messages=[f"生成了 {len(plans)} 个备选方案"],
            )
        else:
            logger.warning(f"generate_plans failed: {result.error}")
            wf_logger.end("generate_plans", success=False, message=result.error)

            return GeneratePlansResponse(
                success=False,
                session_id=session_id,
                plans=[],
                messages=result.messages,
                error=result.error,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"generate_plans exception: {e}", exc_info=True)
        wf_logger.error("generate_plans", e)
        raise


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    store=Depends(get_session_store),
):
    """
    获取会话详情
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=session.session_id,
        status=session.status.value,
        current_version=session.current_version,
        brief=session.brief.to_dict() if hasattr(session.brief, "to_dict") else session.brief,
        plan=session.current_plan.to_dict() if session.current_plan and hasattr(session.current_plan, "to_dict") else None,
        items=[
            ContentItemSchema(
                item_id=item.item_id,
                item_type=item.item_type.value,
                content=item.content,
                metadata=item.metadata,
                status=item.status.value if hasattr(item.status, "value") else str(item.status),
                generation_prompt=item.generation_prompt,
                position=item.position,
                local_path=item.local_path,
            )
            for item in session.items
        ],
        created_at=session.created_at,
        updated_at=session.updated_at,
        versions=[
            {
                "version_number": v.version_number,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by,
                "change_summary": v.change_summary,
            }
            for v in session.versions
        ],
        messages=[
            msg.to_dict() if hasattr(msg, "to_dict") else msg
            for msg in session.messages
        ],
        metadata=session.metadata if hasattr(session, 'metadata') and session.metadata else {},
    )


@router.post("/sessions/{session_id}/generate", response_model=GenerateResponse)
async def generate_content(
    session_id: str,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    执行内容生成

    1. 生成文案
    2. 生成配图
    3. 生成视频/音频（如需要）
    """
    wf_logger = get_workflow_logger("generate_content")
    wf_logger.start("generate_content")
    logger.info(f"generate_content called for session: {session_id}")

    try:
        session = await store.get(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        logger.debug(f"Session found, status={session.status}")
        wf_logger.start("orchestrator.generate")

        result = await orchestrator.generate(session)

        logger.debug(f"orchestrator.generate returned: success={result.success}")

        if result.success:
            # 更新会话
            await store.save(session)
            logger.info(f"Content generated successfully: {len(session.items)} items")

            wf_logger.end("orchestrator.generate", success=True, message=f"items={len(session.items)}")
            wf_logger.end("generate_content", success=True, message=f"items={len(session.items)}")

            return GenerateResponse(
                success=True,
                session_id=session_id,
                items_count=len(session.items),
                messages=result.messages,
            )
        else:
            logger.warning(f"generate_content failed: {result.error}")
            wf_logger.end("orchestrator.generate", success=False, message=result.error)
            wf_logger.end("generate_content", success=False, message=result.error)

            return GenerateResponse(
                success=False,
                session_id=session_id,
                error=result.error,
                messages=result.messages,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"generate_content exception: {e}", exc_info=True)
        wf_logger.error("generate_content", e)
        raise


@router.post("/sessions/{session_id}/review", response_model=ReviewResponse)
async def review_content(
    session_id: str,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    审核内容

    1. 合规检查
    2. 质量评分
    3. 生成建议
    """
    wf_logger = get_workflow_logger("review_content")
    wf_logger.start("review_content")
    logger.info(f"review_content called for session: {session_id}")

    try:
        session = await store.get(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        # 调用 critic 审核
        from ..core.critic import Critic
        critic = Critic(orchestrator.llm_gateway, orchestrator.config)

        wf_logger.start("critic.critique")
        critique = await critic.critique(
            session.brief,
            session.current_plan,
            session.items,
        )
        wf_logger.end("critic.critique", success=True, message=f"score={critique.score:.2f}, passed={critique.passed}")

        logger.info(f"Review completed: score={critique.score:.2f}, passed={critique.passed}, issues={len(critique.issues)}")
        wf_logger.end("review_content", success=True, message=f"score={critique.score:.2f}")

        return ReviewResponse(
            passed=critique.passed,
            score=critique.score,
            issues=critique.issues,
            suggestions=critique.suggestions,
            overall_comment=critique.overall_comment,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"review_content exception: {e}", exc_info=True)
        wf_logger.error("review_content", e)
        raise


@router.post("/sessions/{session_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    session_id: str,
    request: FeedbackRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    提交用户反馈

    1. 解析反馈意图
    2. 执行迭代修改
    3. 更新版本
    """
    wf_logger = get_workflow_logger("submit_feedback")
    wf_logger.start("submit_feedback")
    logger.info(f"submit_feedback called for session: {session_id}, feedback: {request.user_feedback[:50]}...")

    try:
        session = await store.get(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        wf_logger.start("orchestrator.iterate")
        result = await orchestrator.iterate(session, request.user_feedback)
        logger.debug(f"orchestrator.iterate returned: success={result.success}")

        if result.success:
            await store.save(session)
            logger.info(f"Feedback processed: iteration={result.iteration_count}, modified={len(result.modified_items)}")

            wf_logger.end("orchestrator.iterate", success=True, message=f"modified={len(result.modified_items)}")
            wf_logger.end("submit_feedback", success=True, message=f"iteration={result.iteration_count}")

            return FeedbackResponse(
                success=True,
                session_id=session_id,
                iteration_count=result.iteration_count,
                modified_items_count=len(result.modified_items),
                messages=result.messages,
            )
        else:
            logger.warning(f"submit_feedback failed: {result.error}")
            wf_logger.end("orchestrator.iterate", success=False, message=result.error)
            wf_logger.end("submit_feedback", success=False, message=result.error)

            return FeedbackResponse(
                success=False,
                session_id=session_id,
                error=result.error,
                messages=result.messages,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"submit_feedback exception: {e}", exc_info=True)
        wf_logger.error("submit_feedback", e)
        raise


@router.post("/sessions/{session_id}/publish", response_model=PublishResponse)
async def publish_content(
    session_id: str,
    request: PublishRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    发布内容

    支持：
    - simulate: 模拟发布
    - export: 导出素材包
    - api: API 发布（预留）
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.method == "export":
        # 导出素材包
        publisher = orchestrator.publisher
        zip_data = publisher.export_package(session)

        return PublishResponse(
            success=True,
            session_id=session_id,
            method="export",
            messages=["素材包已生成"],
            exported_content=f"/api/studio/sessions/{session_id}/export",
        )

    else:
        # simulate 或 api
        result = await orchestrator.publish(session)

        return PublishResponse(
            success=result.success,
            session_id=session_id,
            method=request.method,
            messages=result.messages,
            error=result.error if not result.success else None,
        )


@router.get("/sessions/{session_id}/export")
async def export_package(
    session_id: str,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    下载素材包
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    publisher = orchestrator.publisher
    zip_data = publisher.export_package(session)

    return StreamingResponse(
        iter([zip_data]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=session_{session_id}.zip"
        },
    )


@router.get("/sessions/{session_id}/versions")
async def get_version_history(
    session_id: str,
    store=Depends(get_session_store),
):
    """
    获取版本历史
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "current_version": session.current_version,
        "versions": [
            {
                "version_number": v.version_number,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by,
                "change_summary": v.change_summary,
            }
            for v in session.versions
        ],
    }


@router.post("/sessions/{session_id}/rollback/{version}")
async def rollback_version(
    session_id: str,
    version: int,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    回退到指定版本
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    iterator = orchestrator.iterator
    success = iterator.rollback(session, version)

    if success:
        await store.save(session)
        return {
            "success": True,
            "session_id": session_id,
            "rolled_back_to_version": version,
        }
    else:
        return {
            "success": False,
            "error": f"Version {version} not found",
        }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    store=Depends(get_session_store),
):
    """
    删除会话
    """
    logger.info(f"[delete_session] 开始删除会话: {session_id}")

    # 获取会话并清除历史消息
    session = await store.get(session_id)
    if session:
        logger.info(f"[delete_session] 找到会话, messages数量: {len(session.messages)}")
        # 清除历史消息
        session.messages = []
        await store.save(session)
        logger.info(f"[delete_session] 已清除会话消息并保存")
    else:
        logger.warning(f"[delete_session] 会话不存在: {session_id}")

    success = await store.delete(session_id)
    if not success:
        logger.warning(f"[delete_session] 删除失败: {session_id}")
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(f"[delete_session] 会话已删除: {session_id}")
    return {"success": True, "session_id": session_id}


@router.get("/sessions/{session_id}/versions/{version}/content")
async def get_version_content(
    session_id: str,
    version: int,
    store=Depends(get_session_store),
):
    """
    获取指定版本的内容快照
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 从 versions 中查找指定版本
    version_data = None
    for v in session.versions:
        if v.version_number == version:
            version_data = v
            break

    if not version_data:
        raise HTTPException(status_code=404, detail="Version not found")

    return {
        "session_id": session_id,
        "version_number": version,
        "items": version_data.items_snapshot,
        "plan": version_data.plan_snapshot,
    }


@router.post("/sessions/{session_id}/restore/{version}")
async def restore_version(
    session_id: str,
    version: int,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    从指定版本恢复内容到当前
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 查找指定版本
    target_version = None
    for v in session.versions:
        if v.version_number == version:
            target_version = v
            break

    if not target_version:
        raise HTTPException(status_code=404, detail="Version not found")

    # 恢复 items
    from ..models.content_item import ContentItem

    session.items = [
        ContentItem.from_dict(item_data) for item_data in target_version.items_snapshot
    ]

    # 增加版本号
    session.current_version += 1

    # 创建新的版本快照
    from ..models.version import Version

    new_version = Version.create_snapshot(
        session_id=session.session_id,
        version_number=session.current_version,
        plan=session.current_plan,
        items=session.items,
        change_summary=f"从 V{version} 恢复",
        created_by="user",
    )
    session.versions.append(new_version)

    # 更新状态
    session.update_status(SessionStatus.ITERATING)

    # 保存到本地
    if orchestrator.content_store:
        await orchestrator._save_content_to_local(session, session.current_version)

    await store.save(session)

    return {
        "success": True,
        "session_id": session_id,
        "restored_from_version": version,
        "current_version": session.current_version,
    }


@router.post("/sessions/{session_id}/items/{item_id}/upload")
async def upload_item_content(
    session_id: str,
    item_id: str,
    file: UploadFile = File(...),
    store=Depends(get_session_store),
):
    """
    上传本地文件替换指定内容项
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 找到对应的 item
    item = None
    for i in session.items:
        if i.item_id == item_id:
            item = i
            break

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 读取文件内容
    content = await file.read()

    # 根据 item_type 确定内容类型
    content_type_map = {
        "image": "images",
        "video": "videos",
        "audio": "audio",
    }

    from ..models.content_item import ContentType

    item_type_str = item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type)
    subdir = content_type_map.get(item_type_str, "others")

    # 获取 content store
    from ..storage.content_store import ContentStore

    content_store = ContentStore(base_dir="data/studio/sessions")

    # 保存文件
    session_dir = content_store.get_session_dir(session_id)
    content_dir = session_dir / subdir
    content_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lstrip(".") or "jpg"
    file_path = content_dir / f"{item_id}.{ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    # 更新 item
    item.content = f"data:{file.content_type};base64,{base64.b64encode(content).decode()}"
    item.metadata["local_path"] = str(file_path)
    item.metadata["original_filename"] = file.filename

    await store.save(session)

    return {
        "success": True,
        "item_id": item_id,
        "local_path": str(file_path),
        "content": item.content,
    }


@router.patch("/sessions/{session_id}/items/{item_id}")
async def update_item_content(
    session_id: str,
    item_id: str,
    content: str = Body(...),
    store=Depends(get_session_store),
):
    """
    直接更新内容项的文本内容，不经过重新生成
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 找到对应的 item
    item = session.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 更新内容
    item.content = content
    item.metadata["manual_edit"] = True

    await store.save(session)

    return {
        "success": True,
        "item_id": item_id,
        "content": content,
    }


@router.post("/sessions/{session_id}/versions/compose")
async def compose_versions(
    session_id: str,
    version_selections: Dict[str, int],
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    从不同版本中选择性组合成新版本

    version_selections 格式: {"title": 2, "text_0": 1, "image_1": 3}
    - key: 内容项类型，可选索引，如 "title", "text_0", "image_1"
    - value: 版本号
    """
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await orchestrator.iterator.compose_version(session, version_selections)

    if result.success:
        await store.save(session)
        return {
            "success": True,
            "session_id": session_id,
            "version_number": result.iteration_count,
            "items_count": len(result.modified_items),
        }
    else:
        return {
            "success": False,
            "error": result.error,
        }


class PreviewTextRequest(BaseModel):
    """预览文案请求"""
    plan_data: Dict[str, Any] = Field(..., description="方案数据")


class PreviewTemplateRequest(BaseModel):
    """预览模板请求"""
    text_items: List[ContentItemSchema] = Field(..., description="文案内容项列表")
    template_url: str = Field(..., description="模板图片 URL")


@router.post("/sessions/{session_id}/preview-text", response_model=PreviewTextResponse)
async def preview_text(
    session_id: str,
    request: PreviewTextRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    预览文案生成

    根据方案数据快速生成文案内容，用于在方案预览阶段让用户提前看到文案效果
    """
    logger.info(f"preview_text called for session: {session_id}")

    try:
        session = await store.get(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        # 将 plan_data 转换为 ContentPlan 对象
        from ..models.content_plan import ContentPlan
        plan = ContentPlan.from_dict(request.plan_data) if hasattr(ContentPlan, 'from_dict') else request.plan_data

        # 调用 orchestrator 的 preview_text 方法
        result = await orchestrator.preview_text(plan)

        if result.get("success"):
            return PreviewTextResponse(
                success=True,
                title=result.get("title", ""),
                text_sections=result.get("text_sections", []),
            )
        else:
            return PreviewTextResponse(
                success=False,
                error=result.get("error", "Unknown error"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"preview_text exception: {e}", exc_info=True)
        return PreviewTextResponse(
            success=False,
            error=str(e),
        )


@router.post("/sessions/{session_id}/preview-template", response_model=PreviewTemplateResponse)
async def preview_template(
    session_id: str,
    request: PreviewTemplateRequest,
    store=Depends(get_session_store),
    orchestrator=Depends(get_orchestrator),
):
    """
    预览模板渲染

    将文案内容渲染到模板图片上，用于在方案预览阶段让用户提前看到文案+模板效果
    """
    logger.info(f"preview_template called for session: {session_id}")

    try:
        session = await store.get(session_id)
        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        # 将 text_items 转换为 ContentItem 对象
        from ..models.content_item import ContentItem, ContentType, ItemStatus
        text_items = []
        for item_data in request.text_items:
            item = ContentItem(
                item_id=item_data.item_id,
                item_type=ContentType(item_data.item_type) if item_data.item_type in [e.value for e in ContentType] else ContentType.TEXT,
                content=item_data.content,
                metadata=item_data.metadata,
                status=ItemStatus(item_data.status) if item_data.status in [e.value for e in ItemStatus] else ItemStatus.PENDING,
                generation_prompt=item_data.generation_prompt,
                position=item_data.position,
            )
            text_items.append(item)

        # 调用 orchestrator 的 preview_template 方法
        result = await orchestrator.preview_template(text_items, request.template_url)

        if result.get("success"):
            return PreviewTemplateResponse(
                success=True,
                preview_image_url=result.get("preview_image_url"),
            )
        else:
            return PreviewTemplateResponse(
                success=False,
                error=result.get("error", "Unknown error"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"preview_template exception: {e}", exc_info=True)
        return PreviewTemplateResponse(
            success=False,
            error=str(e),
        )


@router.post("/materials/upload")
async def upload_material(
    file: UploadFile = File(...),
):
    """
    上传素材文件（图片、视频、音频等）

    文件将上传到阿里云 OSS，返回公网 URL 地址。
    """
    import uuid
    from pathlib import Path

    # 验证文件类型
    allowed_types = ["image/", "video/", "audio/"]
    if not any(file.content_type.startswith(t) for t in allowed_types):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.content_type}。仅支持图片、视频和音频。"
        )

    # 生成唯一文件名
    ext = Path(file.filename).suffix.lstrip(".") if file.filename else "jpg"
    if not ext:
        ext = file.content_type.split("/")[-1] or "jpg"
    filename = f"{uuid.uuid4().hex[:16]}.{ext}"

    # 读取文件内容
    content = await file.read()

    # 获取 OSS 配置
    try:
        from agent.config.config_service import get_config_service
        config_service = get_config_service()
        env_config = config_service.get_environment_config()
        oss_config = env_config.get("oss", {})

        if not oss_config or not oss_config.get("access_key_id"):
            raise ValueError("OSS 配置未找到")

        access_key_id = oss_config["access_key_id"]
        access_key_secret = oss_config["access_key_secret"]
        bucket_name = oss_config["bucket"]
        endpoint = oss_config["endpoint"]

        # 上传到 OSS
        import oss2
        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

        # 上传文件
        result = bucket.put_object(filename, content)

        if result.status == 200:
            # 生成公网 URL
            material_url = f"https://{bucket_name}.{endpoint}/{filename}"
            logger.info(f"素材上传成功: {filename}, 大小: {len(content)} bytes, URL: {material_url}")
        else:
            raise Exception(f"OSS 上传失败: status={result.status}")

    except Exception as e:
        logger.error(f"OSS 上传失败: {e}")
        # 如果 OSS 上传失败，回退到本地存储
        upload_dir = Path("data/studio/materials")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
        material_url = f"http://localhost:8080/api/studio/materials/{filename}"
        logger.warning(f"回退到本地存储: {material_url}")

    return {
        "success": True,
        "filename": filename,
        "url": material_url,
        "content_type": file.content_type,
        "size": len(content),
    }


@router.get("/proxy/image")
async def proxy_image(url: str):
    """
    代理图片请求，解决跨域问题

    前端通过此接口访问 OSS 图片，避免 CORS 问题
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                # 获取原始内容的 MIME 类型
                content_type = response.headers.get("content-type", "image/png")
                return Response(
                    content=response.content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "Access-Control-Allow-Origin": "*",
                    }
                )
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch image")
    except Exception as e:
        logger.error(f"Proxy image failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

