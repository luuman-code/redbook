"""
画板 API 路由 - Canvas Routes

提供画板的 CRUD 操作 API 和 AI 聊天功能
"""

import uuid
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..canvas.canvas_core import CanvasCore, CanvasSnapshot, CanvasElement, ElementMetadata, ElementStyles, ElementType
from ..canvas.canvas_storage import CanvasStorage, CanvasSummary
from ..canvas.canvas_sync import CanvasSyncHandler, get_canvas_sync_handler
from ..canvas.canvas_agent import CanvasAgent, CanvasSession
from ..debug_logger import get_logger
import os

logger = get_logger("canvas_routes")

router = APIRouter(prefix="/api/canvas", tags=["canvas"])

# 存储实例
_storage: Optional[CanvasStorage] = None

# CanvasAgent 实例
_canvas_agent: Optional[CanvasAgent] = None

# CanvasAgent 缓存 (canvas_id -> CanvasAgent)，用于保持工具状态（如 recent_elements）
_canvas_agent_cache: Dict[str, CanvasAgent] = {}

# Canvas 会话存储 (session_id -> CanvasSession)
_canvas_sessions: Dict[str, CanvasSession] = {}

# WebSocket 连接管理
_canvas_ws_connections: Dict[str, Set[WebSocket]] = {}

# 取消标志存储 (canvas_id -> asyncio.Event)
_canvas_cancellations: Dict[str, asyncio.Event] = {}


def get_cancellation_event(canvas_id: str) -> asyncio.Event:
    """获取或创建指定 canvas 的取消事件"""
    global _canvas_cancellations
    if canvas_id not in _canvas_cancellations:
        _canvas_cancellations[canvas_id] = asyncio.Event()
    return _canvas_cancellations[canvas_id]


def set_cancelled(canvas_id: str) -> None:
    """设置指定 canvas 为已取消状态"""
    global _canvas_cancellations
    # 确保 event 存在（如果不存在则创建）
    if canvas_id not in _canvas_cancellations:
        _canvas_cancellations[canvas_id] = asyncio.Event()
    _canvas_cancellations[canvas_id].set()


def clear_cancelled(canvas_id: str) -> None:
    """清除指定 canvas 的取消状态"""
    global _canvas_cancellations
    if canvas_id in _canvas_cancellations:
        _canvas_cancellations[canvas_id].clear()


def is_cancelled(canvas_id: str) -> bool:
    """检查指定 canvas 是否已取消"""
    global _canvas_cancellations
    if canvas_id in _canvas_cancellations:
        return _canvas_cancellations[canvas_id].is_set()
    return False


def get_storage() -> CanvasStorage:
    """获取存储实例"""
    global _storage
    if _storage is None:
        _storage = CanvasStorage(storage_dir="data/studio/canvases")
    return _storage


def get_canvas_agent(canvas_core: CanvasCore) -> CanvasAgent:
    """获取 CanvasAgent 实例（缓存机制，同一 canvas 复用同一实例以保持状态）"""
    global _canvas_agent_cache

    canvas_id = canvas_core.canvas_id

    # 如果缓存中有该 canvas 的 agent，直接返回
    if canvas_id in _canvas_agent_cache:
        logger.info(f"CanvasAgent cache hit for canvas: {canvas_id}")
        return _canvas_agent_cache[canvas_id]

    # 需要 LLM Gateway，可以通过环境变量或配置获取
    from agent import AgentConfigService, GatewayFactory
    from studio.canvas.canvas_agent import LLMGatewayAdapter

    config_service = AgentConfigService()
    llm_gateway = GatewayFactory.get_gateway("llm", config_service)

    # 使用 LLMGatewayAdapter 包装 LLMGateway，提供 generate 方法
    llm_adapter = LLMGatewayAdapter(llm_gateway)

    # 创建 CanvasAgent（绑定到当前的 canvas_core）
    agent = CanvasAgent(
        llm_client=llm_adapter,
        canvas_core=canvas_core,
        orchestrator=None,  # CanvasAgent 不需要 orchestrator
    )

    # 缓存 agent
    _canvas_agent_cache[canvas_id] = agent
    logger.info(f"CanvasAgent created and cached for canvas: {canvas_id}")
    return agent


def set_canvas_agent(agent: CanvasAgent):
    """设置 CanvasAgent 实例（用于外部注入）"""
    global _canvas_agent
    _canvas_agent = agent


# ============ 请求/响应模型 ============

class CreateCanvasRequest(BaseModel):
    name: str = Field(default="Untitled", description="画板名称")
    width: int = Field(default=1920, ge=100, le=10000, description="画板宽度")
    height: int = Field(default=1080, ge=100, le=10000, description="画板高度")
    background_color: str = Field(default="#ffffff", description="背景颜色")


class CanvasResponse(BaseModel):
    success: bool
    canvas_id: Optional[str] = None
    canvas: Optional[dict] = None
    error: Optional[str] = None


class CanvasListResponse(BaseModel):
    success: bool
    canvases: List[dict] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None


class SaveElementsRequest(BaseModel):
    elements: List[dict]


class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="角色: user/assistant")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[str] = None


class SelectionInfo(BaseModel):
    """选择区域信息"""
    type: str = Field(..., description="选择类型: lasso/rect/element")
    bounds: Optional[dict] = Field(None, description="边界框")
    element_ids: Optional[List[str]] = Field(default_factory=list, description="选中的元素ID列表")
    lasso: Optional[dict] = Field(None, description="套索绘制点序列")


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息")
    messages: Optional[List[ChatMessage]] = Field(default_factory=list, description="历史消息")
    selection: Optional[SelectionInfo] = Field(None, description="当前选择区域")
    session_id: Optional[str] = Field(None, description="会话ID，不提供则创建新会话")
    image_urls: Optional[List[str]] = Field(default=None, description="用户上传的参考图片 URL 列表，用于多模态模型识别")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    message: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="AI 执行的操作")
    elements: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="最新的画布元素")
    session_id: Optional[str] = Field(None, description="会话ID，用于保持对话历史")
    agent_mode: Optional[str] = Field(None, description="Agent 当前模式: daily, planning, working")
    needs_confirm: Optional[bool] = Field(None, description="是否需要用户确认模式切换")
    confirm_type: Optional[str] = Field(None, description="需要确认的类型: planning, working")
    route_confidence: Optional[float] = Field(None, description="路由置信度")
    route_reason: Optional[str] = Field(None, description="路由原因")
    error: Optional[str] = None


class CleanupResponse(BaseModel):
    """清理响应"""
    success: bool
    archive_paths: List[str] = Field(default_factory=list)
    record_count: int = 0
    error: Optional[str] = None


class ArchiveListResponse(BaseModel):
    """归档列表响应"""
    success: bool
    archives: List[dict] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None


# ============ 路由 ============

@router.get("/canvases", response_model=CanvasListResponse)
async def list_canvases(limit: int = 100, offset: int = 0):
    """列出用户的所有画板"""
    try:
        storage = get_storage()
        summaries = await storage.list_canvases(user_id="default")
        summaries_data = []
        for s in summaries:
            if hasattr(s, 'to_dict'):
                summaries_data.append(s.to_dict())
            elif isinstance(s, dict):
                summaries_data.append(s)
        return CanvasListResponse(
            success=True,
            canvases=summaries_data[offset:offset + limit],
            total=len(summaries_data)
        )
    except Exception as e:
        logger.error(f"Failed to list canvases: {e}", exc_info=True)
        return CanvasListResponse(success=False, error=str(e))


@router.post("/canvases", response_model=CanvasResponse)
async def create_canvas(request: CreateCanvasRequest):
    """创建新画板"""
    try:
        storage = get_storage()

        # 创建画板ID
        canvas_id = str(uuid.uuid4())

        # 创建 CanvasCore
        canvas = CanvasCore(canvas_id=canvas_id)
        canvas.name = request.name
        canvas.width = request.width
        canvas.height = request.height
        canvas.background_color = request.background_color

        # 保存到存储
        await storage.save_canvas(canvas)

        logger.info(f"Created canvas: {canvas_id}")

        return CanvasResponse(
            success=True,
            canvas_id=canvas_id,
            canvas={
                "canvas_id": canvas_id,
                "name": request.name,
                "width": request.width,
                "height": request.height,
                "background_color": request.background_color,
                "elements": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_by": "user"
            }
        )
    except Exception as e:
        logger.error(f"Failed to create canvas: {e}", exc_info=True)
        return CanvasResponse(success=False, error=str(e))


@router.get("/canvases/{canvas_id}", response_model=CanvasResponse)
async def get_canvas(canvas_id: str):
    """获取画板详情"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            return CanvasResponse(success=False, error="画板不存在")

        # 获取快照
        snapshot = canvas.get_snapshot()
        return CanvasResponse(
            success=True,
            canvas_id=canvas_id,
            canvas=snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
        )
    except Exception as e:
        logger.error(f"Failed to get canvas {canvas_id}: {e}", exc_info=True)
        return CanvasResponse(success=False, error=str(e))


@router.put("/canvases/{canvas_id}", response_model=CanvasResponse)
async def save_canvas(canvas_id: str):
    """保存画板"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)
        if canvas:
            await storage.save_canvas(canvas)
        return CanvasResponse(success=True, canvas_id=canvas_id)
    except Exception as e:
        logger.error(f"Failed to save canvas {canvas_id}: {e}", exc_info=True)
        return CanvasResponse(success=False, error=str(e))


@router.delete("/canvases/{canvas_id}", response_model=CanvasResponse)
async def delete_canvas(canvas_id: str, cleanup: bool = True):
    """
    删除画板（可选是否清理工具记录）

    【修复】如果 cleanup=True 且归档失败，不再继续删除操作
    """
    try:
        if cleanup and canvas_id in _canvas_agent_cache:
            agent = _canvas_agent_cache[canvas_id]
            try:
                result = agent.archive_and_cleanup(archive_all=True)
                if not result["success"]:
                    # 归档失败，返回错误，不继续删除画板
                    return CanvasResponse(
                        success=False,
                        error=f"归档失败: {result.get('error', '未知错误')}。请重试或手动清理。",
                        canvas_id=canvas_id
                    )
            except Exception as e:
                logger.warning(f"Failed to cleanup tool records: {e}")
                return CanvasResponse(
                    success=False,
                    error=f"清理失败: {str(e)}",
                    canvas_id=canvas_id
                )
            finally:
                # 无论成功失败，都从缓存中移除
                if canvas_id in _canvas_agent_cache:
                    del _canvas_agent_cache[canvas_id]

        storage = get_storage()
        success = await storage.delete_canvas(canvas_id)
        return CanvasResponse(success=success, canvas_id=canvas_id)
    except Exception as e:
        logger.error(f"Failed to delete canvas {canvas_id}: {e}", exc_info=True)
        return CanvasResponse(success=False, error=str(e))


@router.post("/canvases/{canvas_id}/cleanup", response_model=CleanupResponse)
async def cleanup_canvas(canvas_id: str, archive_all: bool = True):
    """清理画板 - 归档工具记录并清空短期存储"""
    if canvas_id not in _canvas_agent_cache:
        return CleanupResponse(success=False, error="CanvasAgent not found")

    agent = _canvas_agent_cache[canvas_id]
    result = agent.archive_and_cleanup(archive_all=archive_all)

    if not result["success"]:
        return CleanupResponse(
            success=False,
            error=result.get("error", "Unknown error"),
        )

    return CleanupResponse(
        success=True,
        archive_paths=result.get("archive_paths", []),
        record_count=result.get("record_count", 0),
    )


@router.post("/canvases/{canvas_id}/drawing-session/reset")
async def reset_drawing_session(canvas_id: str):
    """重置绘图会话（用户点击'绘制完成'按钮时调用）"""
    if canvas_id not in _canvas_agent_cache:
        return {"success": False, "error": "CanvasAgent not found"}

    agent = _canvas_agent_cache[canvas_id]
    agent.reset_drawing_session()
    return {"success": True}


@router.get("/canvases/{canvas_id}/archives", response_model=ArchiveListResponse)
async def list_canvas_archives(canvas_id: str):
    """获取画板的归档历史列表"""
    from ..canvas.canvas_tool_result_store import CanvasToolResultStore
    archives = CanvasToolResultStore.list_archives(canvas_id)
    return ArchiveListResponse(success=True, archives=archives, total=len(archives))


@router.get("/canvases/{canvas_id}/drawings/{drawing_session_id}")
async def get_drawing_by_session(canvas_id: str, drawing_session_id: str):
    """
    获取指定图案会话的完整绘制数据

    优先从内存查询，内存没有则从归档文件直接查询（无需先加载到内存）
    """
    if canvas_id not in _canvas_agent_cache:
        return {"success": False, "error": "CanvasAgent not found"}

    agent = _canvas_agent_cache[canvas_id]
    records = agent.get_drawing_by_session(drawing_session_id)
    return {"success": True, "records": records}


@router.post("/canvases/{canvas_id}/drawings/{drawing_session_id}/restore")
async def restore_drawing(canvas_id: str, drawing_session_id: str, archive_path: str):
    """从归档恢复指定图案到当前会话"""
    if canvas_id not in _canvas_agent_cache:
        return {"success": False, "error": "CanvasAgent not found"}

    agent = _canvas_agent_cache[canvas_id]
    try:
        records = agent._tool_result_store.load_archive(archive_path)
        return {"success": True, "record_count": len(records)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.patch("/canvases/{canvas_id}/rename", response_model=CanvasResponse)
async def rename_canvas(canvas_id: str, request: dict):
    """重命名画板"""
    try:
        storage = get_storage()
        new_name = request.get("name", "Untitled")
        await storage.rename_canvas(canvas_id, new_name)
        return CanvasResponse(success=True, canvas_id=canvas_id)
    except Exception as e:
        logger.error(f"Failed to rename canvas {canvas_id}: {e}", exc_info=True)
        return CanvasResponse(success=False, error=str(e))


@router.post("/canvases/{canvas_id}/duplicate", response_model=CanvasResponse)
async def duplicate_canvas(canvas_id: str):
    """复制画板"""
    try:
        storage = get_storage()
        new_canvas = await storage.duplicate_canvas(canvas_id)

        if new_canvas:
            new_id = new_canvas.canvas_id if hasattr(new_canvas, 'canvas_id') else new_canvas.get('canvas_id')
            return CanvasResponse(
                success=True,
                canvas_id=new_id,
                canvas=new_canvas.to_dict() if hasattr(new_canvas, 'to_dict') else new_canvas
            )
        else:
            return CanvasResponse(success=False, error="复制失败")
    except Exception as e:
        logger.error(f"Failed to duplicate canvas {canvas_id}: {e}", exc_info=True)
        return CanvasResponse(success=False, error=str(e))


@router.post("/canvases/{canvas_id}/elements", response_model=dict)
async def add_element(canvas_id: str, element: dict):
    """添加元素到画板"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            raise HTTPException(status_code=404, detail="画板不存在")

        # 添加元素
        from ..canvas.canvas_core import CanvasElement
        element_id = element.get("id", str(uuid.uuid4()))
        element["id"] = element_id

        # 创建元素对象
        canvas_element = CanvasElement.from_dict(element)
        canvas.add_element(canvas_element)

        # 保存
        await storage.save_canvas(canvas)

        return {"success": True, "element": element}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add element: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.patch("/canvases/{canvas_id}/elements/{element_id}", response_model=dict)
async def update_element(canvas_id: str, element_id: str, updates: dict):
    """更新画板元素"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            raise HTTPException(status_code=404, detail="画板不存在")

        # 更新元素
        canvas.update_element(element_id, updates)

        # 保存
        await storage.save_canvas(canvas)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update element: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.delete("/canvases/{canvas_id}/elements", response_model=dict)
async def delete_elements(canvas_id: str, request: dict):
    """删除画板元素"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            raise HTTPException(status_code=404, detail="画板不存在")

        # 获取要删除的元素ID
        element_ids = request.get("element_ids", [])

        # 删除元素
        canvas.delete_elements(element_ids)

        # 保存
        await storage.save_canvas(canvas)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete elements: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.put("/canvases/{canvas_id}/elements/batch", response_model=dict)
async def batch_save_elements(canvas_id: str, request: SaveElementsRequest):
    """批量保存元素"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            raise HTTPException(status_code=404, detail="画板不存在")

        # 清空现有元素并添加新元素
        from ..canvas.canvas_core import CanvasElement

        # 获取现有元素ID
        existing_ids = [el.id for el in canvas.elements]
        await canvas.delete_elements(existing_ids)  # 需要 await 异步方法

        # 添加新元素
        for el_dict in request.elements:
            # 如果没有 id，生成一个新的
            if not el_dict.get("id"):
                el_dict["id"] = canvas._generate_id() if hasattr(canvas, '_generate_id') else str(uuid.uuid4())
            canvas_element = CanvasElement.from_dict(el_dict)
            await canvas.add_element(canvas_element)  # 需要 await 异步方法

        # 保存
        await storage.save_canvas(canvas)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch save elements: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/canvases/{canvas_id}/versions", response_model=dict)
async def get_version_history(canvas_id: str):
    """获取版本历史"""
    try:
        storage = get_storage()
        versions = await storage.get_version_history(canvas_id)
        return {"success": True, "versions": versions or []}
    except Exception as e:
        logger.error(f"Failed to get versions: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/canvases/{canvas_id}/restore/{version}", response_model=dict)
async def restore_version(canvas_id: str, version: int):
    """恢复到指定版本"""
    try:
        storage = get_storage()
        success = await storage.restore_version(canvas_id, version)
        return {"success": success}
    except Exception as e:
        logger.error(f"Failed to restore version: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ============ WebSocket 端点 ============

@router.websocket("/ws/canvas/{canvas_id}")
async def websocket_canvas(websocket: WebSocket, canvas_id: str):
    """
    画板 WebSocket 端点

    支持：
    - 实时操作同步
    - AI 助手交互
    - 操作节流
    """
    await websocket.accept()

    # 添加到连接池
    if canvas_id not in _canvas_ws_connections:
        _canvas_ws_connections[canvas_id] = set()
    _canvas_ws_connections[canvas_id].add(websocket)

    # 用于跟踪当前正在执行的 chat 任务
    current_chat_task = None

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "REPORT_OPERATION":
                    # 处理画板操作
                    payload = message.get("payload", {})
                    await handle_ws_operation(websocket, canvas_id, payload)

                elif msg_type == "CHAT_MESSAGE":
                    # 处理聊天消息 - 使用 task 并发执行，允许同时处理 STOP_MESSAGE
                    user_message = message.get("message", "")
                    selection = message.get("selection", None)

                    # 如果有正在执行的 chat 任务，先取消它
                    if current_chat_task and not current_chat_task.done():
                        logger.info(f"[WebSocket] Cancelling previous chat task")
                        current_chat_task.cancel()
                        try:
                            await current_chat_task
                        except asyncio.CancelledError:
                            pass

                    # 创建新的 chat 任务（不 await，让它并发执行）
                    current_chat_task = asyncio.create_task(
                        handle_ws_chat(websocket, canvas_id, user_message, selection)
                    )

                elif msg_type == "PING":
                    await websocket.send_json({"type": "PONG"})

                elif msg_type == "SYNC_STATE":
                    # 处理前端同步状态请求（用于自动保存）
                    elements = message.get("elements", [])
                    await handle_ws_sync_state(canvas_id, elements)
                    await websocket.send_json({"type": "SYNC_STATE_ACK"})

                elif msg_type == "BRUSH_STROKE":
                    # 处理画笔笔画数据
                    await handle_ws_brush_stroke(websocket, canvas_id, message)

                elif msg_type == "STOP_MESSAGE":
                    # 处理停止消息 - 打断正在进行的 Agent 操作
                    logger.info(f"Received STOP_MESSAGE for canvas_id: {canvas_id}")
                    set_cancelled(canvas_id)
                    await websocket.send_json({"type": "STOP_ACK"})

                    # 取消当前正在执行的 chat 任务
                    if current_chat_task and not current_chat_task.done():
                        logger.info(f"[WebSocket] Cancelling chat task due to STOP_MESSAGE")
                        current_chat_task.cancel()
                        try:
                            await current_chat_task
                        except asyncio.CancelledError:
                            logger.info(f"[WebSocket] Chat task cancelled successfully")
                        except Exception as e:
                            logger.error(f"[WebSocket] Error awaiting cancelled task: {e}")
                    logger.info(f"Received STOP_MESSAGE for canvas_id: {canvas_id}")
                    set_cancelled(canvas_id)
                    await websocket.send_json({"type": "STOP_ACK"})

                else:
                    logger.warning(f"Unknown message type: {msg_type}")

            except json.JSONDecodeError:
                logger.error(f"Invalid JSON: {data}")
    except WebSocketDisconnect:
        pass  # Client disconnected normally
    except Exception as e:
        logger.error(f"Canvas WebSocket error: {e}", exc_info=True)
    finally:
        # 从连接池移除
        if canvas_id in _canvas_ws_connections:
            _canvas_ws_connections[canvas_id].discard(websocket)
            if not _canvas_ws_connections[canvas_id]:
                del _canvas_ws_connections[canvas_id]


async def handle_ws_operation(websocket: WebSocket, canvas_id: str, payload: dict):
    """处理 WebSocket 操作消息"""
    try:
        # 获取画板
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            await websocket.send_json({
                "type": "ERROR",
                "error": "Canvas not found"
            })
            return

        # 获取同步处理器
        sync_handler = get_canvas_sync_handler()
        sync_handler.set_canvas_manager(lambda cid: storage.load_canvas(cid) if cid == canvas_id else None)

        # 构建操作对象
        from ..canvas.canvas_core import CanvasOperation
        operation = CanvasOperation.from_dict(payload)

        # 执行操作
        result = await canvas.execute_operation(operation)

        # 广播到其他客户端（发送完整的 elements 列表，让前端更新状态）
        elements_data = [el.to_dict() for el in canvas.elements.values()]
        # DEBUG: 检查元素颜色数据
        if elements_data:
            first_elem = elements_data[0]
            logger.info(f"[DEBUG CANVAS_UPDATE operation] canvas_id={canvas_id}, elements_count={len(elements_data)}")
            logger.info(f"[DEBUG CANVAS_UPDATE operation] first_element id={first_elem.get('id')}")
            logger.info(f"[DEBUG CANVAS_UPDATE operation] first_element metadata.fill_color={first_elem.get('metadata', {}).get('fill_color')}")
            logger.info(f"[DEBUG CANVAS_UPDATE operation] first_element metadata.stroke_color={first_elem.get('metadata', {}).get('stroke_color')}")
        await broadcast_to_canvas(canvas_id, {
            "type": "CANVAS_UPDATE",
            "data": {
                "canvas_id": canvas_id,
                "elements": elements_data,
            }
        })

        # 发送确认
        await websocket.send_json({
            "type": "OPERATION_ACK",
            "operation_id": operation.id,
            "success": result.success,
            "error": result.error,
        })

    except Exception as e:
        logger.error(f"Handle operation error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "ERROR",
            "error": str(e),
        })


async def handle_ws_chat(websocket: WebSocket, canvas_id: str, user_message: str, selection: dict = None):
    """处理 WebSocket 聊天消息（此函数在独立 task 中执行，允许并发处理 STOP_MESSAGE）"""
    try:
        # 获取画板和 Agent
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            await websocket.send_json({
                "type": "ERROR",
                "error": "Canvas not found"
            })
            return

        # 清除之前的取消状态
        clear_cancelled(canvas_id)

        # 获取取消事件并设置给 agent
        cancellation_event = get_cancellation_event(canvas_id)

        agent = get_canvas_agent(canvas)
        agent.set_cancellation_event(canvas_id, cancellation_event)

        # 创建或获取会话
        session = CanvasSession(
            session_id=str(uuid.uuid4()),
            canvas_id=canvas_id,
            user_id="websocket_user"
        )

        # 构建用户消息（包含选择区域上下文）
        final_message = user_message
        if selection:
            selection_info = SelectionInfo(**selection)
            selection_context = await _build_selection_context(selection_info, canvas)
            if selection_context:
                final_message = f"""【用户选择区域内容】
{selection_context}

【用户消息】
{user_message}"""

            # 将 selection 存储到 canvas 的 _current_selection，以便 CanvasDrawTool 能够获取 bounds
            from ..canvas.canvas_core import SelectionRegion, LassoSelection
            bounds = selection.get("bounds") or {"x": 0, "y": 0, "width": 0, "height": 0}
            lasso_data = None
            if selection.get("lasso"):
                lasso_data = LassoSelection(
                    id=selection["lasso"].get("id", f"lasso_{canvas.canvas_id}"),
                    type="lasso",
                    points=selection["lasso"].get("points", []),
                    closed=selection["lasso"].get("closed", True)
                )
            canvas._current_selection = SelectionRegion(
                id=f"selection_{canvas.canvas_id}",
                type=selection.get("type", "rect"),
                bounds=bounds,
                element_ids=selection.get("element_ids") or [],
                lasso=lasso_data
            )

        # 处理聊天（此调用可能被 WebSocket handler 取消）
        result = await agent.chat(session, final_message)

        if result.get("success"):
            # 发送 AI 回复
            ai_message = result.get("message", "")
            agent_mode = result.get("agent_mode", "daily")

            # 保存画板
            await storage.save_canvas(canvas)

            await websocket.send_json({
                "type": "CHAT_RESPONSE",
                "message": ai_message,
                "agent_mode": agent_mode,  # 发送当前 agent 模式
            })

            # 如果有操作，广播更新
            # (Agent 执行的操作会更新 canvas.elements)
            elements_data = [el.to_dict() for el in canvas.elements.values()]
            # DEBUG: 检查元素颜色数据
            if elements_data:
                first_elem = elements_data[0]
                logger.info(f"[DEBUG CANVAS_UPDATE] canvas_id={canvas_id}, elements_count={len(elements_data)}")
                logger.info(f"[DEBUG CANVAS_UPDATE] first_element id={first_elem.get('id')}")
                logger.info(f"[DEBUG CANVAS_UPDATE] first_element metadata.fill_color={first_elem.get('metadata', {}).get('fill_color')}")
                logger.info(f"[DEBUG CANVAS_UPDATE] first_element metadata.stroke_color={first_elem.get('metadata', {}).get('stroke_color')}")
                logger.info(f"[DEBUG CANVAS_UPDATE] first_element styles.fill={first_elem.get('styles', {}).get('fill')}")
                logger.info(f"[DEBUG CANVAS_UPDATE] first_element styles.stroke={first_elem.get('styles', {}).get('stroke')}")
            await broadcast_to_canvas(canvas_id, {
                "type": "CANVAS_UPDATE",
                "data": {
                    "canvas_id": canvas_id,
                    "elements": elements_data,
                }
            })
        else:
            await websocket.send_json({
                "type": "ERROR",
                "error": result.get("error", "Chat failed"),
            })

        # 清除取消状态
        clear_cancelled(canvas_id)

    except asyncio.CancelledError:
        logger.info(f"[handle_ws_chat] Chat task was cancelled, clearing cancellation state")
        clear_cancelled(canvas_id)
    except Exception as e:
        logger.error(f"Handle chat error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "ERROR",
            "error": str(e),
        })


async def broadcast_to_canvas(canvas_id: str, message: dict):
    """广播消息到画板所有连接"""
    if canvas_id not in _canvas_ws_connections:
        logger.info(f"[DEBUG] No WebSocket connections for canvas_id={canvas_id}")
        return

    logger.info(f"[DEBUG] Broadcasting to {len(_canvas_ws_connections[canvas_id])} connections")
    dead_connections = []
    for ws in _canvas_ws_connections[canvas_id]:
        try:
            await ws.send_json(message)
        except Exception:
            dead_connections.append(ws)

    # 清理断开的连接
    for ws in dead_connections:
        _canvas_ws_connections[canvas_id].discard(ws)


async def handle_ws_sync_state(canvas_id: str, elements: list):
    """
    处理 WebSocket 状态同步（用于自动保存）

    【核心设计】数据单向循环：
    1. Agent 绘制 → WebSocket DRAW_COMPLETE → 前端
    2. 前端更新本地状态
    3. 前端 auto-save → syncState(elements) → 后端存储

    后端不维护自己的元素状态，完全信任前端传来的数据。
    这样确保前后端状态一致，避免竞态问题。
    """
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            logger.error(f"Sync state failed: canvas {canvas_id} not found")
            return

        from ..canvas.canvas_core import CanvasElement

        # 【修改】完全替换策略：前端传来什么，后端就变成什么
        # 这样确保前后端状态完全一致

        # 1. 清空当前 elements（保留其他非元素数据如 name, width 等）
        current_elements = canvas.elements
        if current_elements:
            element_ids_to_delete = [el.id for el in current_elements]
            await canvas.delete_elements(element_ids_to_delete)

        # 2. 添加前端传来的所有元素
        for el_dict in elements:
            if el_dict.get("id"):
                canvas_element = CanvasElement.from_dict(el_dict)
                await canvas.add_element(canvas_element)

        # 3. 保存到存储
        await storage.save_canvas(canvas)

        logger.info(f"[SYNC] Synced {len(elements)} elements for canvas {canvas_id}, backend now has {len(canvas.elements)} elements")
    except Exception as e:
        logger.error(f"Handle sync state error: {e}", exc_info=True)


async def handle_ws_brush_stroke(websocket: WebSocket, canvas_id: str, message: dict):
    """
    处理 WebSocket 画笔笔画数据

    消息格式:
    {
        "type": "BRUSH_STROKE",
        "points": [[x1, y1], [x2, y2], ...],  // 路径点（绝对坐标）
        "color": "#FF0000",                     // 描边颜色
        "stroke_width": 2,                      // 描边宽度
        "element_id": "optional-id"             // 可选：更新现有元素
    }
    """
    try:
        points = message.get("points", [])
        color = message.get("color", "#000000")
        stroke_width = message.get("stroke_width", 2)
        element_id = message.get("element_id")

        if not points or len(points) < 2:
            await websocket.send_json({
                "type": "ERROR",
                "error": "At least 2 points required for brush stroke"
            })
            return

        # 获取画板
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            await websocket.send_json({
                "type": "ERROR",
                "error": "Canvas not found"
            })
            return

        # 计算边界框
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # 计算画笔的实际边界（考虑线条宽度）
        half_stroke = stroke_width / 2
        bounds_x = min_x - half_stroke
        bounds_y = min_y - half_stroke
        bounds_w = max_x - min_x + stroke_width
        bounds_h = max_y - min_y + stroke_width

        if element_id:
            # 更新现有元素
            element = await canvas.get_element(element_id)
            if element:
                element.metadata.points = points
                element.metadata.stroke_color = color
                element.metadata.stroke_width = stroke_width
                element.size = {"width": bounds_w, "height": bounds_h}
                await canvas.update_element(element)
                logger.info(f"[BRUSH] Updated element {element_id} with {len(points)} points")
            else:
                await websocket.send_json({
                    "type": "ERROR",
                    "error": f"Element {element_id} not found"
                })
                return
        else:
            # 创建新元素
            element_id = str(uuid.uuid4())
            element = CanvasElement(
                id=element_id,
                type=ElementType.SHAPE.value,
                position={"x": bounds_x, "y": bounds_y},
                size={"width": bounds_w, "height": bounds_h},
                metadata=ElementMetadata(
                    shape_type="path",
                    points=points,
                    stroke_color=color,
                    stroke_width=stroke_width,
                ),
                styles=ElementStyles(
                    x=bounds_x,
                    y=bounds_y,
                    width=bounds_w,
                    height=bounds_h,
                    stroke=color,
                    stroke_width=stroke_width,
                    fill="none",
                ),
                created_by="user"
            )
            await canvas.add_element(element)
            logger.info(f"[BRUSH] Created element {element_id} with {len(points)} points")

        # 保存画板
        await storage.save_canvas(canvas)

        # 广播给所有连接的客户端（包括发送者）
        from .websocket_manager import get_websocket_manager, ProgressEvent
        ws_manager = get_websocket_manager()
        event = ProgressEvent(
            event_type="DRAW_COMPLETE",
            item_id=element_id,
            content=json.dumps({
                "element": element.to_dict(),
                "points": points,
                "stroke_color": color,
                "stroke_width": stroke_width,
            }, ensure_ascii=False)
        )
        await ws_manager.broadcast_to_canvas(canvas_id, event)

        # 确认发送
        await websocket.send_json({
            "type": "BRUSH_STROKE_ACK",
            "element_id": element_id,
            "points_count": len(points)
        })

    except Exception as e:
        logger.error(f"Handle brush stroke error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "ERROR",
            "error": str(e)
        })


# ============ Chat API 端点 ============

@router.post("/canvases/{canvas_id}/chat", response_model=ChatResponse)
async def chat(canvas_id: str, request: ChatRequest):
    """
    AI 聊天 API

    处理用户消息，返回 AI 回复和执行的操作
    如果提供了选择区域，会提取区域内内容供 AI 理解
    """
    try:
        # 获取画板
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            return ChatResponse(success=False, error="画板不存在")

        # 构建用户消息（包含选择区域上下文）
        user_message = request.message

        # 如果有选择区域，提取内容并添加到消息中
        if request.selection:
            selection_context = await _build_selection_context(request.selection, canvas)
            if selection_context:
                user_message = f"""【用户选择区域内容】
{selection_context}

【用户消息】
{request.message}"""

            # 将 selection 存储到 canvas 的 _current_selection，以便 CanvasDrawTool 能够获取 bounds
            from ..canvas.canvas_core import SelectionRegion, LassoSelection
            bounds = request.selection.bounds or {"x": 0, "y": 0, "width": 0, "height": 0}
            lasso_data = None
            if request.selection.lasso:
                lasso_data = LassoSelection(
                    id=request.selection.lasso.get("id", f"lasso_{canvas.canvas_id}"),
                    type="lasso",
                    points=request.selection.lasso.get("points", []),
                    closed=request.selection.lasso.get("closed", True)
                )
            canvas._current_selection = SelectionRegion(
                id=f"selection_{canvas.canvas_id}",
                type=request.selection.type,
                bounds=bounds,
                element_ids=request.selection.element_ids or [],
                lasso=lasso_data
            )

        # 获取或创建会话
        if request.session_id and request.session_id in _canvas_sessions:
            session = _canvas_sessions[request.session_id]
            logger.info(f"Using existing session: {session.session_id}")
        else:
            # 创建新会话
            session = CanvasSession(
                session_id=str(uuid.uuid4()),
                canvas_id=canvas_id,
                user_id="http_user"
            )
            _canvas_sessions[session.session_id] = session
            logger.info(f"Created new session: {session.session_id}")

        # 获取 Agent（使用当前 canvas 创建）
        agent = get_canvas_agent(canvas)

        # 处理聊天（传递 image_urls 以支持多模态图片）
        result = await agent.chat(session, user_message, image_urls=request.image_urls)

        if result.get("success"):
            # 保存画板更新
            await storage.save_canvas(canvas)

            # 获取最新 elements
            elements_list = list(canvas.elements.values()) if hasattr(canvas.elements, 'values') else canvas.elements
            elements_dict_list = [el.to_dict() for el in elements_list]

            # 直接在响应中返回 elements，前端会通过 auto-save 保存
            return ChatResponse(
                success=True,
                message=result.get("message", ""),
                elements=elements_dict_list,
                session_id=session.session_id,
                agent_mode=result.get("agent_mode"),  # 返回 Agent 模式
                needs_confirm=result.get("needs_confirm"),
                confirm_type=result.get("confirm_type"),
                route_confidence=result.get("route_confidence"),
                route_reason=result.get("route_reason"),
            )
        else:
            return ChatResponse(
                success=False,
                error=result.get("error", "Chat failed"),
            )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return ChatResponse(success=False, error=str(e))


class ModeSwitchRequest(BaseModel):
    """模式切换请求"""
    session_id: str = Field(..., description="会话ID")
    target_mode: str = Field(..., description="目标模式: planning, working")


class ModeSwitchResponse(BaseModel):
    """模式切换响应"""
    success: bool
    agent_mode: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


@router.post("/canvases/{canvas_id}/confirm-mode-switch", response_model=ModeSwitchResponse)
async def confirm_mode_switch(canvas_id: str, request: ModeSwitchRequest):
    """
    确认模式切换 API

    用户在确认对话框中点击确认后，调用此 API 执行模式切换。
    支持:
    - planning: 从 daily 切换到 planning
    - working: 从 planning 切换到 working
    """
    try:
        # 获取画板
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)

        if not canvas:
            return ModeSwitchResponse(success=False, error="画板不存在")

        # 获取会话
        if request.session_id not in _canvas_sessions:
            return ModeSwitchResponse(success=False, error="会话不存在")

        session = _canvas_sessions[request.session_id]

        # 获取 Agent
        agent = get_canvas_agent(canvas)

        # 执行模式切换
        success = agent.execute_mode_switch(request.target_mode)

        if success:
            return ModeSwitchResponse(
                success=True,
                agent_mode=agent.current_mode.value,
                message=f"已切换到 {request.target_mode} 模式"
            )
        else:
            return ModeSwitchResponse(
                success=False,
                error=f"切换到 {request.target_mode} 模式失败"
            )

    except Exception as e:
        logger.error(f"confirm_mode_switch error: {e}", exc_info=True)
        return ModeSwitchResponse(success=False, error=str(e))


async def _build_selection_context(selection: SelectionInfo, canvas: CanvasCore) -> str:
    """
    构建选择区域的上下文信息

    Args:
        selection: 选择区域信息
        canvas: 画板核心

    Returns:
        格式化的选择区域内容描述
    """
    try:
        from ..canvas.selection_extractor import SelectionExtractor
        from ..canvas.canvas_core import ElementType

        # 优先使用前端传来的 element_ids（已通过精确的射线法计算）
        element_ids = selection.element_ids or []

        # 直接通过 element_ids 获取元素（使用前端已计算的结果）
        elements = []
        for element_id in element_ids:
            element = canvas.get_element(element_id)
            if element:
                elements.append(element)

        # 如果通过 element_ids 获取失败，回退到 SelectionExtractor
        if not elements:
            from ..canvas.canvas_core import SelectionRegion, LassoSelection
            region = SelectionRegion(
                id=selection.lasso.get("id", f"selection_{canvas.canvas_id}") if selection.lasso else f"selection_{canvas.canvas_id}",
                type=selection.type,
                bounds=selection.bounds or {"x": 0, "y": 0, "width": 0, "height": 0},
                element_ids=element_ids,
            )
            if selection.lasso:
                region.lasso = LassoSelection(
                    id=selection.lasso.get("id", ""),
                    type="lasso",
                    points=selection.lasso.get("points", []),
                    closed=selection.lasso.get("closed", True),
                )
            extractor = SelectionExtractor()
            extracted = extractor.extract(region, canvas)
        else:
            # 使用 SelectionExtractor 的分类提取方法
            extractor = SelectionExtractor()
            texts = extractor._extract_texts(elements)
            images = extractor._extract_images(elements)
            videos = extractor._extract_videos(elements)
            audio = extractor._extract_audio(elements)
            summary = extractor._generate_summary(texts, images, videos, audio, elements)

            from ..canvas.canvas_core import ExtractedContent
            extracted = ExtractedContent(
                texts=texts,
                images=images,
                videos=videos,
                audio=audio,
                summary=summary,
            )

        # 构建上下文描述
        context_parts = []

        # 添加框选区域信息（无论是否有选中元素）
        bounds = selection.bounds
        if bounds:
            context_parts.append(f"【框选区域】左上角坐标 ({bounds.get('x', 0):.0f}, {bounds.get('y', 0):.0f})，宽度 {bounds.get('width', 0):.0f}，高度 {bounds.get('height', 0):.0f}")

        if extracted.texts:
            texts_content = "\n".join([
                f"- 文本元素 (ID: {t.get('id')}): \"{t.get('content', '')}\""
                for t in extracted.texts[:5]  # 最多5个文本
            ])
            context_parts.append(f"【文本内容】\n{texts_content}")

        if extracted.images:
            images_content = "\n".join([
                f"- 图片元素 (ID: {img.get('id')}): {img.get('url', img.get('local_path', '未指定'))}"
                for img in extracted.images[:5]  # 最多5个图片
            ])
            context_parts.append(f"【图片内容】\n{images_content}")

        if extracted.videos:
            videos_content = "\n".join([
                f"- 视频元素: {v.get('url', '未指定')} (时长: {v.get('duration', 0)}秒)"
                for v in extracted.videos[:3]
            ])
            context_parts.append(f"【视频内容】\n{videos_content}")

        if extracted.audio:
            audio_content = "\n".join([
                f"- 音频元素: {a.get('url', '未指定')} (时长: {a.get('duration', 0)}秒)"
                for a in extracted.audio[:3]
            ])
            context_parts.append(f"【音频内容】\n{audio_content}")

        # 添加摘要
        if extracted.summary:
            context_parts.append(f"【区域摘要】\n{extracted.summary}")

        total_elements = len(extracted.texts or []) + len(extracted.images or []) + \
                        len(extracted.videos or []) + len(extracted.audio or [])

        if not context_parts:
            return f"选择了 {len(selection.element_ids or [])} 个元素"

        return "\n\n".join(context_parts) + f"\n\n（共 {total_elements} 个元素）"

    except Exception as e:
        logger.error(f"Failed to build selection context: {e}", exc_info=True)
        return ""


# ============ 导出端点 ============

@router.get("/canvases/{canvas_id}/export")
async def export_canvas(canvas_id: str, format: str = "json"):
    """导出画板"""
    try:
        storage = get_storage()
        canvas = await storage.load_canvas(canvas_id)
        if not canvas:
            raise HTTPException(status_code=404, detail="画板不存在")

        snapshot = canvas.get_snapshot()
        return snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export canvas {canvas_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
