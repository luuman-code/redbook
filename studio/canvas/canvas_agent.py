"""
CanvasAgent - 创意工坊画板专用 Agent

独立于 XiaohongshuAgent 的画板专用 AI 辅助创作 Agent。

【核心原则】用户主导，AI辅助
- 用户是创作者，Agent只是辅助工具
- 所有操作必须等待用户明确指令
- 不主动修改任何内容

基于 Mini-Agent 的 ReAct 循环模式。
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mini_agent.tools.base import Tool
from mini_agent.schema import Message, LLMResponse, ToolCall, FunctionCall

from .canvas_prompt import CANVAS_SYSTEM_PROMPT, CANVAS_CONTEXT_TEMPLATE
from .mode_router import get_mode_router, RouteResult
from ..agent.message_store import AgentMessageStore, AgentMode
from .canvas_core import CanvasCore, CanvasSnapshot
from .canvas_tool_result_store import CanvasToolResultStore, CanvasToolResultRecord
from ..core.orchestrator import Orchestrator
from ..debug_logger import get_agent_api_logger, get_mode_debug_logger
from ..agent.context_manager import AgentContextManagementMixin
from ..agent.canvas_tools import (
    CanvasUnderstandTool,
    CanvasEditTool,
    CanvasGlobalEditTool,
    CanvasGenerateTool,
    CanvasOperateTool,
    CanvasSuggestTool,
    CanvasImageEditTool,
    CanvasDrawTool,
    CanvasUndoTool,
    CanvasSnapshotTool,
    CanvasShapeTool,
    CanvasTransformTool,
    GetCanvasToolResultTool,
    CanvasToolResult,
)
from studio.skills import SkillRegistry, ToolEnforcer
from studio.skills.skill_tools import UseSkillTool, DeactivateSkillTool, PreviewSkillTool

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Agent 响应"""
    success: bool
    message: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class CanvasSession:
    """
    画板会话

    用于管理 CanvasAgent 的会话状态。
    """
    session_id: str
    canvas_id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime = field(default_factory=datetime.now)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "canvas_id": self.canvas_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, 'isoformat') else self.created_at,
            "last_active_at": self.last_active_at.isoformat() if hasattr(self.last_active_at, 'isoformat') else self.last_active_at,
            "messages": self.messages,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanvasSession":
        """从字典创建"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        last_active_at = data.get("last_active_at")
        if isinstance(last_active_at, str):
            last_active_at = datetime.fromisoformat(last_active_at)
        elif last_active_at is None:
            last_active_at = datetime.now()

        return cls(
            session_id=data["session_id"],
            canvas_id=data["canvas_id"],
            user_id=data["user_id"],
            created_at=created_at,
            last_active_at=last_active_at,
            messages=data.get("messages", []),
            metadata=data.get("metadata", {}),
        )


class CanvasAgent(AgentContextManagementMixin):
    """
    创意工坊 Agent - 独立于 XiaohongshuAgent

    【核心原则】用户主导，AI辅助
    - 用户是创作者，Agent只是辅助工具
    - 所有操作必须等待用户明确指令
    - 不主动修改任何内容
    """

    def __init__(
        self,
        llm_client,
        canvas_core: CanvasCore,
        orchestrator: Orchestrator,
        max_steps: int = 50,
        max_messages: int = 50,
        enable_skills: bool = True,
    ):
        """
        初始化 CanvasAgent

        Args:
            llm_client: LLM 客户端实例
            canvas_core: 画板核心实例
            orchestrator: 编排器实例
            max_steps: 最大 ReAct 循环步数
            max_messages: 消息历史最大数量限制（不包括系统提示），超过后删除旧消息
        """
        self.llm = llm_client
        self.canvas = canvas_core
        self.orchestrator = orchestrator
        self.max_steps = max_steps
        self.max_messages = max_messages

        # 当前会话（需要在 _init_canvas_tools 之前初始化）
        self._current_session: Optional[CanvasSession] = None

        # 取消事件相关（存储 canvas_id 以便查询最新的 event）
        self._cancellation_canvas_id: Optional[str] = None
        self._cancellation_event: Optional[asyncio.Event] = None

        # 初始化画板工具结果存储器
        self._tool_result_store = CanvasToolResultStore(
            canvas_id=canvas_core.canvas_id,
            storage_dir="data/canvas_tool_results"
        )

        # ========== ML + LLM 混合路由初始化 ==========
        self._mode_router = get_mode_router()
        self._enable_ml_routing = True  # 可以通过配置关闭

        # ========== Skill 机制相关初始化 ==========
        # 技能开关（默认为开启）
        self.enable_skills = enable_skills

        # 消息历史（必须在技能工具初始化之前定义）
        self.messages: List[Message] = []

        if self.enable_skills:
            # 初始化 SkillRegistry
            skill_dir = str(Path(__file__).parent / "skills")
            self.skill_registry = SkillRegistry(skill_dir=skill_dir)

            # 初始化技能工具
            self.use_skill_tool = UseSkillTool(
                self.skill_registry,
                self.messages,
                tool_enforcer=None  # 暂时为 None，后面会创建 ToolEnforcer
            )
            self.deactivate_skill_tool = DeactivateSkillTool(
                self.skill_registry,
                self.messages,
                tool_enforcer=None
            )
            self.preview_skill_tool = PreviewSkillTool(
                self.skill_registry,
                self.messages
            )
        else:
            self.skill_registry = None
            self.use_skill_tool = None
            self.deactivate_skill_tool = None
            self.preview_skill_tool = None

        # 初始化画板专用工具
        self.tools = self._init_canvas_tools()

        # 如果启用技能，创建 ToolEnforcer
        if self.enable_skills:
            # 构建所有工具列表（包含 Canvas 工具和技能工具）
            self.all_tools = self.tools.copy()
            if self.use_skill_tool:
                self.all_tools.append(self.use_skill_tool)
            if self.deactivate_skill_tool:
                self.all_tools.append(self.deactivate_skill_tool)
            if self.preview_skill_tool:
                self.all_tools.append(self.preview_skill_tool)

            # 创建工具过滤器（通过 messages 读取技能状态）
            self.tool_enforcer = ToolEnforcer(
                all_tools=self.all_tools,
                skill_registry=self.skill_registry,
                messages=self.messages
            )

            # 更新技能工具的 tool_enforcer 引用
            if self.use_skill_tool:
                self.use_skill_tool.tool_enforcer = self.tool_enforcer
            if self.deactivate_skill_tool:
                self.deactivate_skill_tool.tool_enforcer = self.tool_enforcer

            # 设置技能激活限制（在规划模式下只能激活特定技能）
            self._setup_skill_restrictions()

            # 构建工具列表（用于 LLM）
            self.tool_schemas = [tool.to_openai_schema() for tool in self.all_tools]
        else:
            self.all_tools = self.tools
            self.tool_enforcer = None
            self.tool_schemas = [tool.to_openai_schema() for tool in self.tools]

        # 用户上传的素材
        self._current_materials: List[Dict[str, Any]] = []

        # Agent API 日志记录器
        self._api_logger = get_agent_api_logger()

        # 模式调试日志记录器
        self._mode_debug_logger = get_mode_debug_logger()

        # ========== 消息分块存储初始化 ==========
        # 消息存储（用于分块管理和模式切换）
        self.message_store = AgentMessageStore()
        # system_base 只包含技能目录等不变内容（稍后在 chat 时设置）
        # 模式 prompt 在 _build_system_prompt 中根据 mode 动态选择

        # 当前模式（默认日常模式）
        self.current_mode = AgentMode.DAILY

        # 初始化上下文管理器
        self._init_context_manager(
            max_messages=max_messages,
            sliding_window_mode="hybrid",
            llm_client=llm_client,
            memory_manager=getattr(orchestrator, 'memory', None)
        )

    def _init_canvas_tools(self) -> List[Tool]:
        """初始化画板专用工具集"""
        session_id = self._current_session.session_id if self._current_session else None
        return [
            CanvasUnderstandTool(self.canvas, self.orchestrator),
            CanvasEditTool(self.canvas, self.orchestrator),
            CanvasGlobalEditTool(self.canvas, self.orchestrator),
            CanvasGenerateTool(self.canvas, self.orchestrator),
            CanvasOperateTool(self.canvas),
            CanvasSuggestTool(self.canvas, self.orchestrator),
            CanvasImageEditTool(self.canvas, self.orchestrator),
            CanvasDrawTool(self.canvas, self.orchestrator, session_id=session_id, tool_result_store=self._tool_result_store),
            CanvasUndoTool(self.canvas, self.orchestrator, tool_result_store=self._tool_result_store, canvas_id=self.canvas.canvas_id),
            CanvasSnapshotTool(self.canvas, self.orchestrator, tool_result_store=self._tool_result_store, canvas_id=self.canvas.canvas_id),
            CanvasShapeTool(self.canvas, self.orchestrator, session_id=session_id, tool_result_store=self._tool_result_store),
            CanvasTransformTool(self.canvas, self.orchestrator, tool_result_store=self._tool_result_store, canvas_id=self.canvas.canvas_id),
            GetCanvasToolResultTool(self._tool_result_store, canvas_id=self.canvas.canvas_id),
        ]

    def _find_tool(self, name: str) -> Optional[Tool]:
        """根据名称查找工具"""
        for tool in self.all_tools:
            if tool.name == name:
                return tool
        return None

    async def _execute_tool_with_validation(self, tool, tool_name: str, arguments: dict) -> CanvasToolResult:
        """执行工具并验证必需参数

        Args:
            tool: 工具实例
            tool_name: 工具名称
            arguments: 参数字典

        Returns:
            CanvasToolResult
        """
        # 检查工具是否有 parameters 定义（大多数工具都有）
        if hasattr(tool, 'parameters') and tool.parameters:
            required_params = tool.parameters.get("required", [])
            if required_params:
                missing_params = [p for p in required_params if p not in arguments]
                if missing_params:
                    logger.warning(f"[CanvasAgent] Tool '{tool_name}' missing required parameters: {missing_params}")
                    return CanvasToolResult(
                        success=False,
                        error=f"工具 {tool_name} 缺少必需参数: {', '.join(missing_params)}"
                    )

        # 执行工具
        try:
            return await tool.execute(**arguments)
        except TypeError as e:
            # 处理参数不匹配的错误（如缺少必需参数）
            logger.error(f"[CanvasAgent] Tool '{tool_name}' execution error: {e}")
            return CanvasToolResult(
                success=False,
                error=f"工具 {tool_name} 执行失败: {str(e)}"
            )

    def _setup_skill_restrictions(self):
        """设置技能激活限制

        在规划模式下，只能激活 canvas_understand 和 canvas_planning 技能。
        其他技能（如 canvas_draw）不允许在规划模式下激活。
        """
        def skill_allowed_checker(skill_name: str) -> bool:
            if self.current_mode == AgentMode.PLANNING:
                # 规划模式：只允许激活 canvas_understand 和 canvas_planning
                allowed_in_planning = {"canvas_understand", "canvas_planning"}
                return skill_name in allowed_in_planning
            elif self.current_mode == AgentMode.DAILY:
                # 日常模式：只允许激活 canvas_understand
                return skill_name == "canvas_understand"
            else:
                # 工作模式：允许所有技能
                return True

        if self.use_skill_tool:
            self.use_skill_tool.set_skill_allowed_checker(skill_allowed_checker)
            logger.info("[CanvasAgent] Skill restrictions configured for use_skill_tool")

    def _get_allowed_tool_names(self, mode: AgentMode) -> List[str]:
        """获取当前模式允许的工具名称列表

        Args:
            mode: 当前模式

        Returns:
            允许的工具名称列表
        """
        if mode == AgentMode.WORKING:
            # 工作模式：所有 Canvas 工具可用（排除 canvas_planning 这个技能）
            # 注意：use_skill/deactivate_skill/preview_skill 是技能工具，需要单独处理
            return [t.name for t in self.tools]
        elif mode == AgentMode.PLANNING:
            # 规划模式：只能使用 canvas_understand（了解画布状态）
            return ["canvas_understand"]
        else:
            # 日常模式：只能使用 canvas_understand
            return ["canvas_understand"]

    def _get_tool_schemas_for_mode(self, mode: AgentMode) -> List[Dict]:
        """获取当前模式对应的工具 schema 列表

        Args:
            mode: 当前模式

        Returns:
            过滤后的工具 schema 列表
        """
        allowed_names = set(self._get_allowed_tool_names(mode))

        # 同时添加技能工具（use_skill, deactivate_skill, preview_skill）
        # 这些工具在所有模式下都需要可用
        skill_tool_names = {"use_skill", "deactivate_skill", "preview_skill"}

        filtered_schemas = []
        for tool in self.all_tools:
            if tool.name in allowed_names or tool.name in skill_tool_names:
                filtered_schemas.append(tool.to_openai_schema())

        logger.debug(f"[CanvasAgent] Tool schemas for mode {mode}: {[t['function']['name'] for t in filtered_schemas]}")
        return filtered_schemas

    def _build_skill_catalog(self, mode: AgentMode = None) -> str:
        """生成技能目录供渐进式披露

        Args:
            mode: 当前模式，用于过滤技能
                - WORKING 模式：所有技能可用（除 canvas_planning）
                - PLANNING 模式：canvas_understand + canvas_planning（介绍工作模式工具）
                - DAILY 模式：只有 canvas_understand 可用
        """
        if not self.enable_skills or not self.skill_registry:
            return ""

        summaries = self.skill_registry.get_all_summaries()
        if not summaries:
            return ""

        # 根据模式过滤技能
        if mode == AgentMode.WORKING:
            # 工作模式：所有技能可用（排除 canvas_planning，它只在规划模式有用）
            filtered_summaries = [s for s in summaries if s.name != "canvas_planning"]
        elif mode == AgentMode.PLANNING:
            # 规划模式：canvas_understand + canvas_planning（介绍工作模式工具）
            filtered_summaries = [s for s in summaries if s.name in ["canvas_understand", "canvas_planning"]]
        else:
            # 日常模式：只有 canvas_understand 可用
            filtered_summaries = [s for s in summaries if s.name == "canvas_understand"]

        if not filtered_summaries:
            return ""

        lines = ["## 可用技能", "", "通过 use_skill(name) 激活技能:", ""]
        for s in filtered_summaries:
            lines.append(f"- **{s.name}**: {s.description}")
        lines.append("")
        lines.append("通过 preview_skill(name) 可以查看技能概要（不激活）。")
        catalog = "\n".join(lines)
        logger.debug(f"[CanvasAgent] Built skill catalog with {len(filtered_summaries)} skills for mode {mode}")
        return catalog

    def _maybe_inject_active_skills(self) -> None:
        """
        LLM 调用前检查是否需要注入技能摘要

        注意：不重复注入完整 prompt，只注入简短激活状态
        通过对话历史获取已激活技能（而非 session_state）
        """
        if not self.enable_skills:
            return

        active = self._get_active_skills_from_history()
        if not active:
            logger.debug(f"[CanvasAgent] No active skills to inject")
            return

        # 检查是否已存在激活状态摘要（避免重复）
        for msg in reversed(self.messages[-5:]):
            if msg.role == "system" and "【技能状态】" in msg.content:
                logger.debug(f"[CanvasAgent] Skill status already injected, skipping")
                return  # 已存在，跳过

        # 只注入简短激活状态，不重复注入完整 prompt
        skill_list = ", ".join(sorted(active))
        logger.info(f"[CanvasAgent] Injecting skill status: {skill_list}")
        self.messages.append(Message(
            role="system",
            content=f"【技能状态】当前已激活技能: {skill_list}。请遵循这些技能的指令。"
        ))

    def _get_active_skills_from_history(self) -> set:
        """从对话历史中解析已激活的技能"""
        import re
        active = set()
        for msg in self.messages:
            if msg.role == "tool":
                content = msg.content or ""
                # 匹配 "技能 'xxx' 已激活" 或 "技能 'xxx' 已经在激活状态"
                matches = re.findall(r"技能 '([^']+)' 已激活", content)
                active.update(matches)
        return active

    def set_cancellation_event(self, canvas_id: str, event: asyncio.Event) -> None:
        """设置取消事件，用于打断正在进行的操作"""
        self._cancellation_canvas_id = canvas_id
        self._cancellation_event = event

    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        # 优先使用存储的 event（如果存在）
        if self._cancellation_event:
            if self._cancellation_event.is_set():
                return True
            # 如果 event 未设置，但 canvas_id 存在，重新查询全局字典
            # 这可以处理 event 被替换的情况
            if self._cancellation_canvas_id:
                from ..api.canvas_routes import is_cancelled as check_canvas_cancelled
                return check_canvas_cancelled(self._cancellation_canvas_id)
        return False

    async def draw_streaming(self, session_id: str, operation: str,
                            params: Dict[str, Any]) -> Dict[str, Any]:
        """流式绘画方法"""
        tool = CanvasDrawTool(self.canvas, self.orchestrator, session_id=session_id, tool_result_store=self._tool_result_store)
        return await tool.execute_streaming(operation, params)

    async def think(self, user_message: str, context: Dict[str, Any]) -> AgentResponse:
        """
        ReAct 循环的 Think 步骤

        Args:
            user_message: 用户消息
            context: 上下文信息

        Returns:
            AgentResponse
        """
        # 构建画板上下文
        canvas_context = self._build_canvas_context(context)
        self.messages.append(Message(role="system", content=canvas_context))

        # 添加用户消息
        self.messages.append(Message(role="user", content=user_message))

        # 执行 ReAct 循环
        result = await self._run_react_loop()

        return AgentResponse(
            success=True,
            message=result,
        )

    async def act(self, tool_name: str, tool_input: Dict[str, Any]) -> "CanvasToolResult":
        """
        ReAct 循环的 Act 步骤

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            工具执行结果
        """
        tool = self._find_tool(tool_name)
        if not tool:
            from ..agent.canvas_tools import CanvasToolResult
            return CanvasToolResult(success=False, error=f"工具不存在: {tool_name}")

        # 执行工具
        result = await tool.execute(**tool_input)
        return result

    async def observe(self, result: "CanvasToolResult") -> str:
        """
        ReAct 循环的 Observe 步骤

        Args:
            result: 工具执行结果

        Returns:
            观察到的结果描述
        """
        if result.success:
            return f"观察结果: {result.content}"
        else:
            # 如果有 warning 信息，也一并返回给 Agent
            if result.warning:
                return f"操作失败: {result.error}\n\n警告信息: {result.warning}"
            return f"操作失败: {result.error}"

    async def chat(
        self,
        session: CanvasSession,
        user_message: str,
        image_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        处理聊天消息

        Args:
            session: 画板会话
            user_message: 用户消息
            image_urls: 用户上传的参考图片 URL 列表（用于多模态识别）

        Returns:
            Dict containing:
            - success: bool
            - message: str - AI 回复消息
            - session: CanvasSession - 更新后的会话
        """
        # 检查是否切换了会话
        if self._current_session is not None and self._current_session.session_id != session.session_id:
            logger.info(f"CanvasSession changed from {self._current_session.session_id} to {session.session_id}")
            self._clear_agent_messages_for_new_session()

        # 检查 session 是否有历史消息需要恢复
        if len(session.messages) > 0:
            self._restore_session_messages(session)

        self._current_session = session

        # 更新 CanvasDrawTool 的 session_id 和取消事件
        for tool in self.tools:
            if hasattr(tool, 'session_id'):
                tool.session_id = session.session_id
            # 将取消事件传递给每个 tool（用于流式绘制时检查中断）
            if hasattr(tool, '_cancellation_event'):
                tool._cancellation_event = self._cancellation_event

        # 构建画板上下文
        canvas_context = self._build_canvas_context({})
        logger.info(f"[CanvasAgent] _build_canvas_context length: {len(canvas_context)}")
        if "selection_x_start" in canvas_context or "选择区域" in canvas_context:
            logger.info(f"[CanvasAgent] canvas_context contains selection info")

        # 如果启用技能，添加技能目录到 system_base（不变部分）
        if self.enable_skills:
            skill_catalog = self._build_skill_catalog(self.current_mode)
            if skill_catalog:
                # 技能目录作为 system_base 的一部分
                self.message_store.set_system_base(skill_catalog)

        # 添加用户消息（支持多模态图片）
        if image_urls:
            # 构建多模态内容
            image_contents = []
            for idx, url in enumerate(image_urls):
                image_contents.append({"image": url})
            # 添加文本说明
            text_content = f"【用户上传的参考图片，共 {len(image_urls)} 张】\n{user_message}"
            image_contents.insert(0, {"text": text_content})

            user_msg = Message(
                role="user",
                content=image_contents  # 直接传递列表，让 _build_llm_request 处理
            )
            # 只添加到 message_store（不添加到 self.messages）
            self.message_store.add_message(user_msg)
        else:
            user_msg = Message(role="user", content=user_message)
            # 只添加到 message_store（不添加到 self.messages）
            self.message_store.add_message(user_msg)

        # 更新 message_store 的 system_context（动态上下文）
        self.message_store.set_system_context(canvas_context)
        logger.info(f"[CanvasAgent] set_system_context called, canvas_context length: {len(canvas_context)}")

        # ML + LLM 混合路由判断是否需要切换模式（返回路由结果，不执行切换）
        route_result = await self._maybe_route_mode(user_message)

        # 执行 ReAct 循环
        result = await self._run_react_loop()

        # 将回复追加到 session.messages
        self._append_to_session_messages(session, user_message, result)

        # 裁剪工作窗口上下文并归档旧消息
        await self._trim_and_archive_messages(session.session_id)

        # 构建返回结果
        response_data = {
            "success": True,
            "message": result,
            "session": session,
            "agent_mode": self.current_mode.value,  # 返回当前 agent 模式
        }

        # 如果路由建议切换到规划模式且置信度足够高，返回需要确认的标记
        if route_result and route_result.mode.value == "planning" and route_result.confidence >= 0.7:
            response_data["needs_confirm"] = True
            response_data["confirm_type"] = "planning"
            response_data["route_confidence"] = route_result.confidence
            response_data["route_reason"] = route_result.reason
            logger.info(f"[CanvasAgent] 返回需要确认切换到规划模式 (confidence={route_result.confidence:.2f})")

        return response_data

    async def _maybe_route_mode(self, user_message: str) -> Optional[RouteResult]:
        """
        使用 ML + LLM 混合路由判断是否需要切换模式（不执行切换，只返回路由结果）

        Args:
            user_message: 用户消息

        Returns:
            RouteResult 如果路由建议切换模式，否则返回 None
        """
        # 只在 DAILY 模式下进行路由判断
        if self.current_mode != AgentMode.DAILY:
            return None

        if not self._enable_ml_routing:
            return None

        # 提取纯文本消息（用于路由）
        if isinstance(user_message, list):
            # 多模态消息，提取文本部分
            text_parts = []
            for item in user_message:
                if isinstance(item, dict):
                    if item.get("text"):
                        text_parts.append(item["text"])
                    elif item.get("image"):
                        text_parts.append("[图片]")
            routing_text = " ".join(text_parts)
        elif isinstance(user_message, str):
            routing_text = user_message
        else:
            routing_text = str(user_message)

        # 如果消息太短（<2个字符），不做路由
        if len(routing_text.strip()) < 2:
            return None

        try:
            # 使用混合路由判断
            route_result = await self._mode_router.route(routing_text)

            session_id = self._current_session.session_id if self._current_session else 'unknown'

            logger.info(f"[ModeRouter] 路由结果: mode={route_result.mode.value}, "
                       f"confidence={route_result.confidence:.2f}, method={route_result.method}, "
                       f"reason={route_result.reason[:50]}")

            # 记录路由日志
            self._mode_debug_logger.log_mode_switch(
                mode=self.current_mode,
                session_id=session_id,
                from_mode=AgentMode.DAILY.value,
                to_mode=route_result.mode.value,
                reason=f"[ML路由] {route_result.reason}"
            )

            # 如果路由结果是 PLANNING 且置信度足够高，返回路由结果（不执行切换）
            if route_result.mode.value == "planning" and route_result.confidence >= 0.7:
                logger.info(f"[ModeRouter] ML 路由建议切换到规划模式 (confidence={route_result.confidence:.2f})，等待用户确认")
                return route_result

        except Exception as e:
            logger.warning(f"[ModeRouter] 路由失败: {e}")

        return None

    def execute_mode_switch(self, target_mode: str) -> bool:
        """
        执行模式切换（供外部调用，需用户确认）

        Args:
            target_mode: 目标模式 ("planning" 或 "working")

        Returns:
            是否切换成功
        """
        session_id = self._current_session.session_id if self._current_session else 'unknown'

        if target_mode == "planning" and self.current_mode == AgentMode.DAILY:
            from_mode = self.current_mode.value
            self.enter_planning_mode()
            logger.info(f"[ModeRouter] 执行规划模式切换")

            self._mode_debug_logger.log_mode_switch(
                mode=self.current_mode,
                session_id=session_id,
                from_mode=from_mode,
                to_mode=AgentMode.PLANNING.value,
                reason=f"[用户确认] 切换到规划模式"
            )
            return True

        elif target_mode == "working" and self.current_mode == AgentMode.PLANNING:
            # 工作模式切换需要计划文本
            plan_text = self.message_store.get_plan()
            if not plan_text:
                logger.warning("[ModeRouter] 无法切换到工作模式：没有找到计划")
                return False

            from_mode = self.current_mode.value
            user_confirmation = Message(
                message_id=str(uuid.uuid4()),
                role="user",
                content="好的，执行吧",
            )
            self.confirm_plan(plan_text, user_confirmation)
            logger.info(f"[ModeRouter] 执行工作模式切换")

            self._mode_debug_logger.log_mode_switch(
                mode=self.current_mode,
                session_id=session_id,
                from_mode=from_mode,
                to_mode=AgentMode.WORKING.value,
                reason=f"[用户确认] 切换到工作模式"
            )
            return True

        else:
            logger.warning(f"[ModeRouter] 无法切换模式: 当前={self.current_mode.value}, 目标={target_mode}")
            return False

    async def _run_react_loop(self) -> str:
        """执行 ReAct 循环"""
        step = 0

        while step < self.max_steps:
            # 检查是否已取消
            if self.is_cancelled():
                logger.info("Agent execution cancelled")
                return "用户已取消操作"

            step += 1

            # 获取 canvas_id
            canvas_id = self.canvas.canvas_id if self.canvas else 'unknown'

            # 在调用 LLM 生成响应之前添加
            if self.enable_skills:
                # 检查是否需要注入激活技能摘要
                self._maybe_inject_active_skills()

            # 调用 LLM 生成响应
            start_time = datetime.now()

            # 获取当前模式对应的工具列表（按模式过滤）
            current_tool_schemas = self._get_tool_schemas_for_mode(self.current_mode)

            # 记录 API 请求（使用过滤后的工具列表）
            session_id = self._current_session.session_id if self._current_session else 'unknown'
            self._api_logger.log_request(
                session_id=session_id,
                messages=self.messages,
                tools=current_tool_schemas,
            )

            # 使用消息存储构建当前模式的消息
            current_messages = self.message_store.build_messages(self.current_mode)
            logger.info(f"[CanvasAgent] build_messages called for mode {self.current_mode.value}, result message count: {len(current_messages)}")
            # 检查第一条消息（system）的长度
            if current_messages and current_messages[0].role == "system":
                logger.info(f"[CanvasAgent] system message length: {len(current_messages[0].content)}")

            # 记录模式调试日志 - LLM 请求
            self._mode_debug_logger.log_llm_request(
                mode=self.current_mode,
                session_id=session_id,
                messages=current_messages,
                tools=current_tool_schemas,
            )

            response = await self.llm.generate(
                messages=current_messages,
                tools=current_tool_schemas,
            )
            end_time = datetime.now()
            latency_ms = (end_time - start_time).total_seconds() * 1000

            # 检查是否已取消（LLM 调用后）
            if self.is_cancelled():
                logger.info("Agent execution cancelled after LLM call")
                return "用户已取消操作"

            # 记录 API 响应
            response_text = response.content if hasattr(response, 'content') else str(response)
            self._api_logger.log_response(
                session_id=session_id,
                response_content=response_text,
                success=True,
                latency_ms=latency_ms,
            )

            # 记录模式调试日志 - LLM 响应
            self._mode_debug_logger.log_llm_response(
                mode=self.current_mode,
                session_id=session_id,
                response_content=response_text,
                latency_ms=latency_ms,
            )

            # 添加助手响应到消息历史
            assistant_msg = Message(role="assistant", content=response_text)
            if response.tool_calls:
                assistant_msg.tool_calls = response.tool_calls
            self.messages.append(assistant_msg)
            # 同时添加到消息存储（工作模式下会维护 _working_stream）
            self.message_store.add_message(assistant_msg)

            # 检查是否有工具调用
            tool_calls = response.tool_calls

            if not tool_calls:
                # 没有工具调用，直接返回响应
                return response_text

            # 执行工具调用
            for tool_call in tool_calls:
                # 检查是否已取消（每个工具调用前）
                if self.is_cancelled():
                    logger.info("Agent execution cancelled before tool call")
                    return "用户已取消操作"

                tool_name = tool_call.function.name
                try:
                    arguments = tool_call.function.arguments
                except (json.JSONDecodeError, AttributeError):
                    arguments = {}

                # 查找工具
                tool = self._find_tool(tool_name)
                if not tool:
                    tool_result = CanvasToolResult(
                        success=False,
                        error=f"工具不存在: {tool_name}"
                    )
                else:
                    # 检查工具是否在允许列表（仅当 enable_skills 且 tool_enforcer 存在时）
                    if self.enable_skills and self.tool_enforcer:
                        if not self.tool_enforcer.is_tool_allowed(tool_name):
                            logger.warning(f"[CanvasAgent] Tool '{tool_name}' blocked by ToolEnforcer")
                            tool_result = CanvasToolResult(
                                success=False,
                                error=f"工具 {tool_name} 在当前技能上下文中不可用"
                            )
                        else:
                            logger.debug(f"[CanvasAgent] Tool '{tool_name}' allowed by ToolEnforcer")
                            # 验证必需参数
                            tool_result = await self._execute_tool_with_validation(tool, tool_name, arguments)
                    else:
                        # 执行工具
                        tool_result = await self._execute_tool_with_validation(tool, tool_name, arguments)

                # 记录工具调用
                self._api_logger.log_tool_call(
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result_success=tool_result.success,
                    result_preview=tool_result.content if tool_result.success else tool_result.error,
                )

                # 记录模式调试日志 - 工具调用
                self._mode_debug_logger.log_tool_call(
                    mode=self.current_mode,
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=tool_result.content if tool_result.success else tool_result.error,
                    success=tool_result.success,
                )

                # 存储工具结果到 CanvasToolResultStore
                result_content = tool_result.content if tool_result.success else ""
                result_data = None
                element_id = None
                element_type = None
                drawing_session_id = None

                # 尝试解析 JSON 结果
                if tool_result.success and result_content:
                    try:
                        result_data = json.loads(result_content)
                        # 提取 element_id 和 element_type
                        if isinstance(result_data, dict):
                            element_id = result_data.get("element_id")
                            element_type = result_data.get("element_type")
                            # 【新增】提取 drawing_session_id
                            drawing_session_id = result_data.get("drawing_session_id")
                    except json.JSONDecodeError:
                        pass

                tool_record = CanvasToolResultRecord(
                    tool_call_id=tool_call.id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result_content=result_content,
                    result_data=result_data,
                    element_id=element_id,
                    element_type=element_type,
                    drawing_session_id=drawing_session_id,  # 【新增】
                    success=tool_result.success,
                    error=tool_result.error,
                )
                self._tool_result_store.add(tool_record)

                # 将工具结果添加到消息历史
                result_content = tool_result.content if tool_result.success else f"Error: {tool_result.error}"

                tool_msg = Message(
                    role="tool",
                    content=result_content,
                    tool_call_id=tool_call.id,
                    name=tool_name,
                )
                self.messages.append(tool_msg)
                # 同时添加到消息存储（工作模式下会维护 _working_stream）
                self.message_store.add_message(tool_msg)

        # 达到最大步数限制
        return "已达到最大处理步数，请稍后再试。"

    def _build_canvas_context(self, context: Dict[str, Any]) -> str:
        """
        构建画板上下文信息

        Args:
            context: 上下文信息

        Returns:
            包含画板上下文的字符串
        """
        canvas_id = self.canvas.canvas_id if self.canvas else "unknown"
        snapshot = self.canvas.get_snapshot() if self.canvas else None

        element_count = len(snapshot.elements) if snapshot else 0

        # 获取选择信息
        selection_info = "无选中"
        selection_x_start = selection_y_start = selection_x_end = selection_y_end = 0
        selection_width = selection_height = 0

        if snapshot and snapshot.selection:
            selection_info = f"已选中 {len(snapshot.selection.element_ids)} 个元素"
            bounds = snapshot.selection.bounds
            selection_x_start = bounds.get("x", 0)
            selection_y_start = bounds.get("y", 0)
            selection_width = bounds.get("width", 0)
            selection_height = bounds.get("height", 0)
            selection_x_end = selection_x_start + selection_width
            selection_y_end = selection_y_start + selection_height

        # 获取元素类型统计
        elements_summary = {}
        if snapshot:
            for elem in snapshot.elements:
                elem_type = elem.type
                elements_summary[elem_type] = elements_summary.get(elem_type, 0) + 1

        available_operations = [
            "移动元素 (move)",
            "缩放元素 (resize)",
            "旋转元素 (rotate)",
            "对齐元素 (align)",
            "组合/取消组合 (group/ungroup)",
            "编辑文本 (text_edit)",
        ]

        context_str = CANVAS_CONTEXT_TEMPLATE.format(
            canvas_id=canvas_id,
            element_count=element_count,
            selection_info=selection_info,
            available_operations=", ".join(available_operations),
            selection_x_start=selection_x_start,
            selection_y_start=selection_y_start,
            selection_x_end=selection_x_end,
            selection_y_end=selection_y_end,
            selection_width=selection_width,
            selection_height=selection_height,
        )

        # 添加元素类型统计
        if elements_summary:
            type_stats = ", ".join([f"{k}: {v}" for k, v in elements_summary.items()])
            context_str += f"\n\n## 元素类型统计\n{type_stats}"

        return context_str

    def _clear_agent_messages_for_new_session(self) -> None:
        """
        清空 Agent 的消息历史，但保留系统提示词。
        用于切换到新会话时开始新的对话上下文。
        """
        for i, msg in enumerate(self.messages):
            if msg.role == "system" and "创意工坊" in msg.content:
                # 只保留系统提示词
                self.messages = [msg]
                logger.debug("Cleared canvas agent messages, kept system prompt")
                return

    def _restore_session_messages(self, session: CanvasSession) -> None:
        """
        从 session.messages 恢复到 Agent 的消息历史。

        Args:
            session: 画板会话
        """
        if not session.messages:
            return

        # 找到系统提示词的位置
        system_prompt_index = None
        for i, msg in enumerate(self.messages):
            if msg.role == "system" and "创意工坊" in msg.content:
                system_prompt_index = i
                break

        if system_prompt_index is None:
            return

        # 保留系统提示词
        system_prompt = self.messages[system_prompt_index]
        self.messages = [system_prompt]

        # 恢复所有消息
        for msg_data in session.messages:
            llm_msg = Message(
                role=msg_data.get("role", "user"),
                content=msg_data.get("content", ""),
                thinking=None,
                tool_calls=None,
                tool_call_id=None,
                name=None,
            )
            self.messages.append(llm_msg)

        logger.debug(f"Restored {len(session.messages)} messages from session {session.session_id}")

    def _append_to_session_messages(self, session: CanvasSession, user_message: str, result: str) -> None:
        """
        将用户消息和助手回复追加到 session.messages。

        Args:
            session: 画板会话
            user_message: 用户消息
            result: 助手回复
        """
        # 添加用户消息
        session.messages.append({
            "role": "user",
            "content": user_message,
            "message_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
        })

        # 添加助手回复
        if result:
            session.messages.append({
                "role": "assistant",
                "content": result,
                "message_id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
            })

        # 检查消息数量限制（不包括系统提示）
        # 系统提示的 role 是 "system"，用户和助手消息是 "user" 和 "assistant"
        non_system_messages = [msg for msg in session.messages if msg.get("role") != "system"]
        if len(non_system_messages) > self.max_messages:
            # 计算需要删除的消息数量
            excess = len(non_system_messages) - self.max_messages
            # 找到前几个非系统消息的索引
            indices_to_remove = []
            for i, msg in enumerate(session.messages):
                if msg.get("role") != "system":
                    indices_to_remove.append(i)
                    if len(indices_to_remove) >= excess:
                        break
            # 删除旧消息
            for index in reversed(indices_to_remove):
                session.messages.pop(index)
            logger.debug(f"Trimmed {excess} old messages, keeping last {self.max_messages} messages")

    def get_history(self) -> List[Dict[str, Any]]:
        """获取消息历史"""
        return [msg.dict() if hasattr(msg, 'dict') else msg for msg in self.messages]

    # ==================== 模式切换方法 ====================

    def set_mode(self, mode: AgentMode):
        """切换 Agent 模式

        Args:
            mode: 目标模式
        """
        old_mode = self.current_mode
        self.current_mode = mode
        self.message_store.set_mode(mode)
        logger.info(f"Agent mode changed: {old_mode.value} -> {mode.value}")

    def enter_planning_mode(self):
        """进入规划模式"""
        self.set_mode(AgentMode.PLANNING)
        # 保留系统消息，清空规划相关消息重新开始
        self.message_store.clear_planning_messages()

    def confirm_plan(self, plan_text: str, user_confirmation: Message):
        """确认规划，切换到工作模式

        Args:
            plan_text: 确认的计划文本
            user_confirmation: 用户确认的那条消息（如"好的，执行吧"）
        """
        # 保存计划文本
        self.message_store.set_plan(plan_text)

        # 保存用户确认消息（工作模式组装时注入）
        self.message_store.set_user_confirmation(user_confirmation)

        # 自动切换到工作模式
        self.set_mode(AgentMode.WORKING)

        # 清空工作模式的消息（assistant + tool），规划模式历史保留
        self.message_store.clear_working_messages()

    def return_to_daily_mode(self):
        """返回日常模式"""
        self.set_mode(AgentMode.DAILY)
        # 清空工作流和用户确认消息
        self.message_store.clear_working_stream()
        self.message_store.clear_user_confirmation()
        # 可选：根据日常模式裁剪策略裁剪历史
        self.message_store.trim_for_daily_mode()

    def reset(self) -> None:
        """重置 Agent 状态"""
        self.messages = [Message(role="system", content=CANVAS_SYSTEM_PROMPT)]
        self._current_session = None
        # 重置消息存储
        self.message_store.clear_except_system()
        self.set_mode(AgentMode.DAILY)

    def archive_and_cleanup(self, archive_all: bool = True) -> dict:
        """归档工具记录并清理状态"""
        try:
            if archive_all:
                archive_paths = self._tool_result_store.archive_all_and_clear()
            else:
                archive_paths = []
                for record in self._tool_result_store.get_all_records():
                    if record.drawing_session_id:
                        path = self._tool_result_store.archive_by_drawing_session(record.drawing_session_id)
                        if path:
                            archive_paths.append(path)

            # 【修复】同时重置所有工具的 drawing_session 状态
            for tool in self.tools:
                if isinstance(tool, CanvasDrawTool):
                    tool.reset_drawing_session()

            return {
                "success": True,
                "archive_paths": archive_paths,
                "record_count": len(archive_paths),
            }
        except Exception as e:
            logger.error(f"Failed to archive and cleanup: {e}")
            return {"success": False, "error": str(e)}

    def get_drawing_by_session(self, drawing_session_id: str) -> List[dict]:
        """获取指定图案会话的所有绘制数据（优先从内存，内存没有则从归档查询）"""
        try:
            # 先从内存查询
            records = self._tool_result_store.get_by_drawing_session(drawing_session_id)
            if records:
                return [r.to_dict() for r in records]

            # 内存没有，从归档文件查询
            archive_data = self._tool_result_store.get_archive_by_drawing_session_id(
                self.canvas.canvas_id, drawing_session_id
            )
            if archive_data:
                return archive_data.get("records", [])

            return []
        except Exception as e:
            logger.error(f"Failed to get drawing by session: {e}")
            return []

    def reset_drawing_session(self):
        """重置绘图会话（代理到 CanvasDrawTool）"""
        for tool in self.tools:
            if isinstance(tool, CanvasDrawTool):
                tool.reset_drawing_session()


class LLMGatewayAdapter:
    """
    LLM Gateway 适配器（用于 CanvasAgent）

    将 redbook 的 LLMGateway 适配为 Mini-Agent 的 LLMClient 接口
    """

    def __init__(self, llm_gateway):
        self.llm_gateway = llm_gateway

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
    ) -> LLMResponse:
        """
        生成响应

        Args:
            messages: Mini-Agent Message 列表
            tools: 工具列表

        Returns:
            LLMResponse
        """
        from agent.models.llm_gateway import LLMRequest

        api_messages = []

        for msg in messages:
            if msg.role == "system":
                continue
            elif msg.role == "user":
                # 检查是否是多媒体消息（列表格式）还是纯文本
                if isinstance(msg.content, list):
                    # 多模态消息，直接传递内容列表
                    api_messages.append({"role": "user", "content": msg.content})
                else:
                    # 普通文本消息
                    api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                assistant_msg = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    tool_calls = []
                    for tc in msg.tool_calls:
                        tool_calls.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": json.dumps(tc.function.arguments),
                            },
                        })
                    assistant_msg["tool_calls"] = tool_calls
                api_messages.append(assistant_msg)
            elif msg.role == "tool":
                tool_content = msg.content
                # 检查是否包含 visual_snapshot_url，如果有则转换为多模态格式
                try:
                    result_json = json.loads(tool_content)
                    if isinstance(result_json, dict) and result_json.get("visual_snapshot_url"):
                        # 提取图片 URL 和文本描述
                        image_url = result_json.get("visual_snapshot_url")
                        # 构建多模态内容
                        # 移除 visual_snapshot_base64 以减少 token 消耗
                        snapshot_info = {
                            "canvas_info": result_json.get("canvas_info"),
                            "selection_info": result_json.get("selection_info"),
                            "elements_summary": result_json.get("elements_summary"),
                        }
                        text_part = json.dumps(snapshot_info, ensure_ascii=False)

                        # 转换为多模态格式（参考 DashScope 格式）
                        api_messages.append({
                            "role": "tool",
                            "tool_call_id": msg.tool_call_id,
                            "content": [
                                {"text": f"【画布快照图片】\n{text_part}"},
                                {"image": image_url}  # DashScope 多模态格式
                            ]
                        })
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

                # 默认处理：直接传递字符串内容
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": tool_content,
                })

        # 如果有系统提示，添加到第一个用户消息前面
        system_contents = []
        for msg in messages:
            if msg.role == "system":
                system_contents.append(msg.content)

        if system_contents and api_messages:
            combined_system = "\n\n".join(system_contents)
            if api_messages[0]["role"] == "user":
                first_msg_content = api_messages[0]["content"]
                if isinstance(first_msg_content, list):
                    first_msg_content.insert(0, {"text": combined_system + "\n\n"})
                else:
                    api_messages[0]["content"] = combined_system + "\n\n" + first_msg_content
        elif system_contents and not api_messages:
            # 如果只有 system 消息没有 user/assistant 消息，
            # 将 system 内容作为第一条用户消息（用于首次对话）
            combined_system = "\n\n".join(system_contents)
            api_messages.append({"role": "user", "content": combined_system})

        try:
            # 构建请求
            request = LLMRequest(messages=api_messages, tools=tools)

            # 调用网关
            response = await self.llm_gateway.invoke(request)

            if response.success:
                content = response.data.get("content", "") if response.data else ""

                # 解析工具调用
                tool_calls = None
                tool_calls_data = response.data.get("tool_calls") if response.data else None

                if tool_calls_data:
                    tool_calls = []
                    for tc in tool_calls_data:
                        try:
                            func_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError as e:
                            logger.error(f"[CanvasAgent] Failed to parse tool arguments: {e}")
                            logger.error(f"[CanvasAgent] Raw arguments: {tc['function']['arguments'][:200]}...")
                            func_args = {}
                        function_call = FunctionCall(
                            name=tc["function"]["name"],
                            arguments=func_args
                        )
                        tool_call = ToolCall(
                            id=tc["id"],
                            type="function",
                            function=function_call
                        )
                        tool_calls.append(tool_call)

                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    finish_reason="stop",
                )
            else:
                return LLMResponse(
                    content=f"Error: {response.error}",
                    finish_reason="error",
                )
        except Exception as e:
            return LLMResponse(
                content=f"Exception: {str(e)}",
                finish_reason="error",
            )
