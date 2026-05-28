"""
XiaohongshuAgent - LLM 驱动的小红书内容创作 Agent

基于 Mini-Agent 的 ReAct 循环模式，让 LLM 决定何时调用工具。
"""

import json
import logging
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mini_agent.tools.base import Tool
from mini_agent.schema import Message, LLMResponse, ToolCall, FunctionCall

from .tools import (
    GenerateContentTool,
    ReviewContentTool,
    IterateContentTool,
    RegeneratePlansTool,
    ModifyPlanTool,
    PublishContentTool,
    GetSessionTool,
    GenerateTemplateTool,
    GetToolResultTool,
    ToolResult,
)
from .system_prompt import SYSTEM_PROMPT
from .context_manager import AgentContextManagementMixin
from ..core.orchestrator import Orchestrator
from ..models.session import Session
from ..models.message import Message as SessionMessage
from ..debug_logger import get_agent_api_logger

logger = logging.getLogger(__name__)


class LLMGatewayAdapter:
    """
    LLM Gateway 适配器

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
        # 转换消息格式
        from agent.models.llm_gateway import LLMRequest

        api_messages = []

        for msg in messages:
            if msg.role == "system":
                # 系统消息作为用户消息的前缀
                continue
            elif msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                assistant_msg = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    # 转换 tool_calls
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
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })

        # 如果有系统提示，添加到第一个用户消息前面（合并所有 system 消息）
        system_contents = []
        for msg in messages:
            if msg.role == "system":
                system_contents.append(msg.content)

        if system_contents and api_messages:
            combined_system = "\n\n".join(system_contents)
            if api_messages[0]["role"] == "user":
                first_msg_content = api_messages[0]["content"]
                if isinstance(first_msg_content, list):
                    # 多模态内容：在开头插入文本类型的 system prompt
                    first_msg_content.insert(0, {"text": combined_system + "\n\n"})
                else:
                    # 纯文本内容
                    api_messages[0]["content"] = combined_system + "\n\n" + first_msg_content
            else:
                api_messages.insert(0, {"role": "user", "content": combined_system})

        try:
            # 构建请求
            request = LLMRequest(messages=api_messages, tools=tools)

            # 调用网关
            response = await self.llm_gateway.invoke(request)

            # ========== 调试日志：记录 LLM 响应 ==========
            if response.success:
                logger.info(f"[LLMGatewayAdapter.generate] LLM 调用成功")
                content = response.data.get("content", "") if response.data else ""
                logger.info(f"[LLMGatewayAdapter.generate] content: {content[:200] if content else '(空)'}...")
                tool_calls_data = response.data.get("tool_calls") if response.data else None
                if tool_calls_data:
                    logger.info(f"[LLMGatewayAdapter.generate] tool_calls: {len(tool_calls_data)} 个")
                    for tc in tool_calls_data:
                        logger.info(f"  - {tc['function']['name']}")
                else:
                    logger.info(f"[LLMGatewayAdapter.generate] tool_calls: 无")
            else:
                logger.warning(f"[LLMGatewayAdapter.generate] LLM 调用失败: {response.error}")
            # ========== 调试日志结束 ==========

            if response.success:
                # 解析响应内容
                content = response.data.get("content", "") if response.data else ""

                # 解析工具调用
                tool_calls = None
                tool_calls_data = response.data.get("tool_calls") if response.data else None

                if tool_calls_data:
                    from mini_agent.schema import ToolCall, FunctionCall

                    tool_calls = []
                    for tc in tool_calls_data:
                        try:
                            func_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError as e:
                            logger.error(f"[Agent] Failed to parse tool arguments: {e}")
                            logger.error(f"[Agent] Raw arguments: {tc['function']['arguments'][:200]}...")
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


@dataclass
class ToolResultRecord:
    """工具结果记录"""
    tool_call_id: str
    tool_name: str
    arguments: dict
    result_content: str
    result_data: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result_content": self.result_content,
            "result_data": self.result_data,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
        }

    @staticmethod
    def from_dict(data: dict) -> "ToolResultRecord":
        data = data.copy()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return ToolResultRecord(**data)


class ToolResultStore:
    """持久化工具结果存储器"""

    def __init__(self, session_id: str, storage_dir: str = "data/tool_results"):
        self.session_id = session_id
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.storage_dir / f"{session_id}_tool_results.json"
        self._lock = threading.Lock()
        self._records: List[ToolResultRecord] = []
        self._load()

    def _load(self):
        """从文件加载记录"""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._records = [ToolResultRecord.from_dict(r) for r in data]
            except Exception as e:
                logger.warning(f"Failed to load tool results: {e}")
                self._records = []

    def _save(self):
        """保存记录到文件"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._records], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save tool results: {e}")

    def add(self, record: ToolResultRecord):
        """添加记录"""
        with self._lock:
            self._records.append(record)
            self._save()

    def get_latest(self, tool_name: Optional[str] = None, index: int = 0) -> Optional[ToolResultRecord]:
        """按添加顺序获取工具结果

        index=0 返回最老的记录（V1）
        index=1 返回第二个记录（V2）
        index=2 返回第三个记录（V3）
        以此类推...
        """
        with self._lock:
            records = [r for r in self._records if r.tool_name == tool_name] if tool_name else self._records
            if not records:
                return None
            # 按 timestamp 升序排序（最老在前）
            sorted_records = sorted(records, key=lambda r: r.timestamp, reverse=False)
            # 安全检查
            if index < 0 or index >= len(sorted_records):
                return None
            return sorted_records[index]

    def get_field(self, tool_name: str, field_name: str, index: int = 0) -> Any:
        """从工具结果中获取特定字段

        index=0 获取最老版本，index=1 获取第二个版本，以此类推"""
        record = self.get_latest(tool_name, index)
        if not record or not record.result_data:
            return None
        return record.result_data.get(field_name)

    def get_all_records(self) -> List[ToolResultRecord]:
        """获取所有记录"""
        with self._lock:
            return self._records.copy()

    def get_history(self, tool_name: Optional[str] = None, limit: int = 10) -> List[dict]:
        """获取历史记录（按添加顺序，最老在前）

        返回格式：[V1, V2, V3, ...]"""
        with self._lock:
            records = [r for r in self._records if r.tool_name == tool_name] if tool_name else self._records
            # 按 timestamp 升序排序（最老在前）
            sorted_records = sorted(records, key=lambda r: r.timestamp, reverse=False)
            return [r.to_dict() for r in sorted_records[:limit]]

    def rollback(self, index: int = 1) -> Optional[ToolResultRecord]:
        """回滚到第 N 个最新记录（默认回滚到上一个）"""
        with self._lock:
            if len(self._records) < index + 1:
                return None
            removed = self._records[-index:]
            self._records = self._records[:-index]
            self._save()
            return removed[0] if removed else None

    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._records.clear()
            self._save()


class AutoInjectStore:
    """自动注入存储"""

    def __init__(self):
        self._values: Dict[str, Any] = {}  # backup_param_name -> value

    def set(self, backup_param: str, value: Any):
        """存储 backup 参数值"""
        self._values[backup_param] = value

    def get(self, backup_param: str) -> Any:
        """获取 backup 参数值"""
        return self._values.get(backup_param)

    def clear(self):
        """清空存储"""
        self._values.clear()


# Backup 参数映射表
# key: 目标工具名称
# value: {源字段名: backup参数名}
BACKUP_FIELD_MAPPING = {
    "iterate_content": {
        "preview_image_url": "backup_template_image_url",
        "title": "backup_title",
        "text_sections": "backup_text_sections",
    },
    "generate_template": {
        "preview_image_url": "backup_preview_image_url",
    },
}


class XiaohongshuAgent(AgentContextManagementMixin):
    """
    小红书内容创作 Agent

    使用 LLM 驱动的 ReAct 循环替代原有的 if-elif 规则引擎。

    工作流程：
    1. 用户输入 → LLM 分析意图
    2. LLM 决定调用哪个工具
    3. 工具执行 → 观察结果
    4. LLM 决定是否继续或结束
    """

    def __init__(
        self,
        llm_client,
        orchestrator: Orchestrator,
        max_steps: int = 50,
    ):
        """
        初始化 XiaohongshuAgent

        Args:
            llm_client: LLM 客户端实例（可以是 Mini-Agent LLMClient 或适配器）
            orchestrator: 编排器实例（用于工具执行）
            max_steps: 最大 ReAct 循环步数
        """
        self.llm = llm_client
        self.orchestrator = orchestrator
        self.max_steps = max_steps

        # 初始化工具
        self.tools = self._init_tools()

        # 构建工具列表（用于 LLM）
        self.tool_schemas = [tool.to_openai_schema() for tool in self.tools]

        # 消息历史
        self.messages: List[Dict[str, Any]] = []

        # 当前会话
        self._current_session: Optional[Session] = None

        # 用户上传的素材（由 orchestrator 设置）
        self._current_materials: List[Dict[str, Any]] = []

        # 模板分析结果（用于 analyze_template 工具分析后传递给 create_session）
        self._current_template_analysis: Optional[List[Dict]] = None

        # 工具结果存储器（持久化到文件）
        self._tool_result_store = ToolResultStore(session_id="default")

        # 自动注入存储
        self._auto_inject_store = AutoInjectStore()

        # 添加工具到消息历史
        self.messages.append(Message(role="system", content=SYSTEM_PROMPT))

        # 初始化上下文管理器
        self._init_context_manager(
            max_messages=50,
            sliding_window_mode="hybrid",
            llm_client=llm_client,
            memory_manager=getattr(orchestrator, 'memory', None)
        )

    def _init_tools(self) -> List[Tool]:
        """初始化工具列表"""
        return [
            GenerateContentTool(self.orchestrator),
            ReviewContentTool(self.orchestrator),
            IterateContentTool(self.orchestrator),
            RegeneratePlansTool(self.orchestrator),
            GenerateTemplateTool(self.orchestrator),
            PublishContentTool(self.orchestrator),
            GetSessionTool(self.orchestrator),
            GetToolResultTool(self.orchestrator),
        ]

    def _find_tool(self, name: str) -> Optional[Tool]:
        """根据名称查找工具"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    async def chat(
        self,
        session: Session,
        user_message: str,
    ) -> Dict[str, Any]:
        """
        处理聊天消息

        Args:
            session: 会话对象
            user_message: 用户消息

        Returns:
            Dict containing:
            - success: bool
            - messages: List[str] - AI 回复消息列表
            - session: Session - 更新后的会话
        """
        # 检查是否切换了会话
        if self._current_session is not None and self._current_session.session_id != session.session_id:
            logger.info(f"Session changed from {self._current_session.session_id} to {session.session_id}")
            # 保存旧会话的消息到 session.messages
            self._save_session_messages()
            # 清空 Agent 消息，保留系统提示词
            self._clear_agent_messages_for_new_session()

        # 检查 session 是否有历史消息需要恢复
        if len(session.messages) > 0:
            self._restore_session_messages(session)

        self._current_session = session

        # 构建会话上下文信息
        session_context = self._build_session_context(session)
        # 添加会话上下文作为系统消息的一部分
        context_msg = Message(role="system", content=session_context)

        # 添加带有上下文的用户消息
        self.messages.append(context_msg)

        # 构建包含素材信息的用户消息
        user_content = user_message
        materials = getattr(self, '_current_materials', None)

        # 检查是否有图片素材需要直接传给多模态模型
        image_materials = []
        if materials and len(materials) > 0:
            for mat in materials:
                if mat.get('type') == 'image':
                    # 优先使用 url（OSS 公网 URL）
                    if mat.get('url'):
                        image_materials.append({"image": mat['url']})
                    elif mat.get('content'):
                        # 回退到 base64
                        image_materials.append({"image": mat['content']})

        if image_materials:
            # 使用 DashScope MultiModalConversation 格式：文本 + 图片
            text_content = user_message
            # DashScope 格式：文本用 {"text": "..."}，图片用 {"image": "base64..."}
            user_content = [
                {"text": text_content},
                *image_materials
            ]
            logger.info(f"[DEBUG] user_message length: {len(user_message)}")
            logger.info(f"[DEBUG] text_content preview: {text_content[:100]}...")
            logger.info(f"[DEBUG] Multimodal content: text=1, images={len(image_materials)}")
            logger.info(f"Passing {len(image_materials)} images directly to LLM (multimodal format)")
            self.messages.append(Message(role="user", content=user_content))
        else:
            # 只有文本消息
            material_desc = ""
            if materials and len(materials) > 0:
                material_desc = f"\n\n【用户上传了 {len(materials)} 个素材】\n"
                for i, mat in enumerate(materials):
                    mat_type = mat.get('type', 'unknown')
                    if mat_type == 'image':
                        material_desc += f"- 素材 {i+1}: 图片\n"
                    elif mat_type == 'video':
                        material_desc += f"- 素材 {i+1}: 视频\n"
                    elif mat_type == 'text':
                        material_desc += f"- 素材 {i+1}: 文本\n"
                    else:
                        material_desc += f"- 素材 {i+1}: {mat_type}\n"
            self.messages.append(Message(role="user", content=user_message + material_desc))

        # 执行 ReAct 循环
        result = await self._run_react_loop()

        # 将新消息追加到 session.messages（用于持久化）
        self._append_to_session_messages(session, user_message, result)

        # 【重要修复】同步 session 和 _current_session 的消息
        # 当 create_session 创建新 session 时，_current_session 会变成新 session
        # 为了确保消息不丢失，将 _current_session 的消息同步到 session
        if self._current_session is not None and self._current_session is not session:
            if self._current_session.messages:
                # 记录旧 session 的消息 ID（用于去重）
                existing_msg_ids = {msg.message_id for msg in session.messages}
                # 将 _current_session 的消息合并到 session
                for msg in self._current_session.messages:
                    if msg.message_id not in existing_msg_ids:
                        session.messages.append(msg)
                logger.debug(f"Synced {len(self._current_session.messages)} messages from _current_session to session")

        # 如果 _current_session 有 current_plan（由 orchestrator.create_session 设置），更新 session 的其他属性
        if self._current_session is not None and self._current_session.current_plan is not None:
            session.current_plan = self._current_session.current_plan
            session.brief = self._current_session.brief
            session.status = self._current_session.status
            logger.debug(f"Updated session with current_plan from _current_session")

        # 返回 _current_session（如果被 create_session 工具更新过，则包含新 session 和 plan）
        # 注意：_current_session 可能在 Agent._run_react_loop() 执行期间被 create_session 工具更新
        return_session = self._current_session if self._current_session is not None else session

        # 裁剪工作窗口上下文并归档旧消息
        await self._trim_and_archive_messages(session.session_id)

        return {
            "success": True,
            "messages": [result] if result else [],
            "session": return_session,
        }

    def _trigger_auto_inject(self, result_data: dict, source_tool: str):
        """触发自动注入机制

        根据映射表，将工具结果中的字段值存储到自动注入存储中，
        供后续工具调用时自动注入 backup 参数。
        """
        for target_tool, mapping in BACKUP_FIELD_MAPPING.items():
            for field_name, backup_param in mapping.items():
                if field_name in result_data:
                    value = result_data[field_name]
                    self._auto_inject_store.set(backup_param, value)
                    logger.info(f"[AutoInject] {field_name} -> {backup_param} = {value}")

    async def _run_react_loop(self) -> str:
        """执行 ReAct 循环"""
        step = 0

        while step < self.max_steps:
            step += 1

            # 获取 session_id
            session_id = self._current_session.session_id if self._current_session else 'unknown'

            # ========== Agent API 调用日志：记录请求 ==========
            api_logger = get_agent_api_logger()
            api_logger.log_request(session_id, self.messages, self.tool_schemas)
            # ========== 日志记录结束 ==========

            # 调用 LLM 生成响应
            start_time = datetime.now()
            response = await self.llm.generate(
                messages=self.messages,
                tools=self.tool_schemas,
            )
            end_time = datetime.now()
            latency_ms = (end_time - start_time).total_seconds() * 1000

            # ========== Agent API 调用日志：记录响应 ==========
            # LLMResponse 没有 success 属性，通过 content 是否存在来判断成功
            response_content = response.content if hasattr(response, 'content') else str(response)
            if response_content:
                api_logger.log_response(session_id, response_content, True, latency_ms=latency_ms)
            else:
                api_logger.log_response(session_id, "", False, error=str(response), latency_ms=latency_ms)
            # ========== 日志记录结束 ==========

            # 解析响应
            response_text = response_content

            # 添加助手响应到消息历史
            assistant_msg = Message(role="assistant", content=response_text)
            if response.tool_calls:
                assistant_msg.tool_calls = response.tool_calls
            self.messages.append(assistant_msg)

            # 检查是否有工具调用
            tool_calls = response.tool_calls

            if not tool_calls:
                # 没有工具调用，直接返回响应
                return response_text

            # 执行工具调用
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = tool_call.function.arguments
                except (json.JSONDecodeError, AttributeError):
                    arguments = {}

                # 查找工具
                tool = self._find_tool(tool_name)
                if not tool:
                    tool_result = ToolResult(
                        success=False,
                        error=f"工具不存在: {tool_name}"
                    )
                else:
                    # 执行工具之前，自动注入 backup 参数
                    if tool_name in BACKUP_FIELD_MAPPING:
                        mapping = BACKUP_FIELD_MAPPING[tool_name]
                        for field_name, backup_param in mapping.items():
                            backup_value = self._auto_inject_store.get(backup_param)
                            if backup_value is not None:
                                # 如果参数中不存在这个 backup 参数，或者存在但为空
                                if backup_param not in arguments or not arguments.get(backup_param):
                                    arguments[backup_param] = backup_value
                                    logger.info(f"[AutoInject] Injected {backup_param}={backup_value} to {tool_name}")

                    # 执行工具
                    tool_result = await tool.execute(**arguments)

                # ========== Agent API 调用日志：记录工具调用 ==========
                api_logger = get_agent_api_logger()
                session_id = self._current_session.session_id if self._current_session else 'unknown'
                api_logger.log_tool_call(
                    session_id,
                    tool_name,
                    arguments,
                    tool_result.success,
                    result_preview=tool_result.content[:200] if tool_result.content else tool_result.error
                )
                # ========== 日志记录结束 ==========

                # 将工具结果添加到消息历史
                result_content = tool_result.content if tool_result.success else f"Error: {tool_result.error}"

                tool_msg = Message(
                    role="tool",
                    content=result_content,
                    tool_call_id=tool_call.id,
                    name=tool_name,
                )
                self.messages.append(tool_msg)

                # 将工具结果存储到 ToolResultStore（持久化）
                try:
                    result_data = json.loads(result_content) if result_content else {}
                except (json.JSONDecodeError, TypeError):
                    result_data = {}

                tool_record = ToolResultRecord(
                    tool_call_id=tool_call.id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result_content=result_content,
                    result_data=result_data,
                    success=tool_result.success,
                    error=tool_result.error,
                )
                self._tool_result_store.add(tool_record)

                # 触发自动提取机制
                if tool_result.success and result_data:
                    self._trigger_auto_inject(result_data, tool_name)

        # 达到最大步数限制
        return "已达到最大处理步数，请稍后再试。"

    def _save_session_messages(self):
        """
        将当前 Agent 的消息保存到 session.messages。
        只保存用户消息和助手回复，不包含系统提示词和会话上下文。
        """
        if self._current_session is None:
            return

        # 过滤出用户消息和助手消息（排除系统消息和工具结果）
        session_messages = []
        for msg in self.messages:
            if msg.role in ("user", "assistant"):
                session_messages.append(msg)

        if session_messages:
            self._current_session.messages.extend(session_messages)
            logger.debug(f"Saved {len(session_messages)} messages to session {self._current_session.session_id}")

    def _clear_agent_messages_for_new_session(self):
        """
        清空 Agent 的消息历史，但保留系统提示词。
        用于切换到新会话时开始新的对话上下文。
        """
        for i, msg in enumerate(self.messages):
            if msg.role == "system" and "你是一个专业的小红书内容创作助手" in msg.content:
                # 只保留系统提示词
                self.messages = [msg]
                logger.debug("Cleared agent messages, kept system prompt")
                return

    def _restore_session_messages(self, session: Session):
        """
        从 session.messages 恢复到 Agent 的消息历史。
        恢复所有消息，但在添加用户消息时去重（避免重复）。

        注意：需要将 studio.models.message.Message 转换为 mini_agent.schema.Message
        """
        if not session.messages:
            return

        # 找到系统提示词的位置
        system_prompt_index = None
        for i, msg in enumerate(self.messages):
            if msg.role == "system" and "你是一个专业的小红书内容创作助手" in msg.content:
                system_prompt_index = i
                break

        if system_prompt_index is None:
            return

        # 保留系统提示词
        system_prompt = self.messages[system_prompt_index]
        self.messages = [system_prompt]

        # 用于用户消息去重：记录已添加的用户消息内容
        seen_user_contents = set()

        # 恢复所有消息（用户消息和助手消息）
        for msg in session.messages:
            if msg.role == "user":
                # 用户消息需要去重
                msg_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if msg_content in seen_user_contents:
                    logger.debug(f"Skipping duplicate user message: {msg_content[:50]}...")
                    continue
                seen_user_contents.add(msg_content)

            # 将 studio.models.message.Message 转换为 mini_agent.schema.Message
            llm_msg = Message(
                role=msg.role,
                content=msg.content,
                thinking=None,
                tool_calls=None,
                tool_call_id=None,
                name=None,
            )
            self.messages.append(llm_msg)

        logger.debug(f"Restored {len(session.messages)} messages from session {session.session_id}")

    def _append_to_session_messages(self, session: Session, user_message: str, result: str):
        """
        将助手回复追加到 session.messages。
        注意：用户消息由 orchestrator.chat() 添加，这里不再重复添加。
        """
        # 添加助手回复
        if result:
            session.messages.append(SessionMessage(
                role="assistant",
                content=result,
                message_id=str(uuid.uuid4()),
                timestamp=datetime.now(),
            ))

    def _build_session_context(self, session: Session) -> str:
        """
        构建会话上下文信息，用于告知 LLM 当前会话状态

        Returns:
            包含会话上下文的字符串
        """
        session_id = session.session_id if session else "unknown"
        has_plan = session.current_plan is not None
        session_status = session.status.value if session and hasattr(session.status, 'value') else "unknown"

        # 构建会话状态描述
        if has_plan:
            plan_title = session.current_plan.title if hasattr(session.current_plan, 'title') else "未命名方案"
            status_desc = f"会话 {session_id} 已有一个内容方案：{plan_title}，状态：{session_status}"
        else:
            status_desc = f"会话 {session_id} 是空会话，尚未生成方案，状态：{session_status}"

        # 构建指导 LLM 行为的指令
        instructions = """
## 当前会话状态

""" + status_desc + """

### 行为指导

- **直接回答问题**：如果用户只是询问会话信息（如会话ID、方案内容等），**直接用自然语言回答**，不要调用任何工具
- 如果用户提供新的创作需求：
  1. 当前会话是空会话 → 直接调用 create_session 工具
  2. 当前会话已有方案 → 调用 create_session 工具（会使用当前 session_id）
- **重要**：不要在回复中询问用户"是否要创建会话"，直接决定并执行

### 工具调用原则
- create_session 工具会自动使用当前会话 ID（如果存在），不会创建重复会话
- 工具执行结果会返回 session_id，无需在回复中提及
"""

        return instructions

    def get_history(self) -> List[Dict[str, Any]]:
        """获取消息历史"""
        return [msg.dict() if hasattr(msg, 'dict') else msg for msg in self.messages]

    def reset(self):
        """重置 Agent 状态"""
        self.messages = [Message(role="system", content=SYSTEM_PROMPT)]
        self._current_session = None
