"""
Debug Logger - 调试日志记录器

提供统一的调试日志输出，便于追踪工作流程中每一步的执行情况。
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import json


# 日志级别配置 - 从环境变量读取
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
CONFIG_LOG_LEVEL = LOG_LEVEL_MAP.get(LOG_LEVEL, logging.INFO)

# 日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonFormatter(logging.Formatter):
    """JSON 格式化日志"""

    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class DebugLogger:
    """调试日志记录器"""

    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_logger()
        return cls._instance

    def _init_logger(self):
        """初始化日志记录器"""
        self._logger = logging.getLogger("studio")
        self._logger.setLevel(CONFIG_LOG_LEVEL)

        # 避免重复添加 handler
        if self._logger.handlers:
            return

        # 控制台输出 (文本格式)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(CONFIG_LOG_LEVEL)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

        # 文件输出 - JSON格式，使用 RotatingFileHandler
        # __file__ is C:/Users/LWB/Desktop/redbook/studio/debug_logger.py
        # parent.parent = C:/Users/LWB/Desktop/redbook
        log_dir = Path(__file__).parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"studio_debug_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(CONFIG_LOG_LEVEL)
        file_handler.setFormatter(JsonFormatter())

        self._logger.addHandler(console_handler)
        self._logger.addHandler(file_handler)

    @property
    def logger(self):
        return self._logger


# 全局日志实例
_logger = DebugLogger().logger


def get_logger(name: str = None) -> logging.Logger:
    """获取日志记录器

    Args:
        name: 模块名称，如 "routes", "orchestrator", "brief_parser"

    Returns:
        日志记录器实例
    """
    if name:
        return logging.getLogger(f"studio.{name}")
    return _logger


# ========== 工作流程日志工具 ==========

class WorkflowLogger:
    """工作流程日志记录器，用于追踪每一步的执行"""

    def __init__(self, logger: logging.Logger, workflow_name: str):
        self.logger = logger
        self.workflow_name = workflow_name
        self.step_times = {}

    def start(self, step_name: str):
        """开始一个步骤"""
        self.logger.info(f"[{self.workflow_name}] ▶ 开始: {step_name}")
        self.step_times[step_name] = {"start": datetime.now(), "end": None}

    def end(self, step_name: str, success: bool = True, message: str = ""):
        """结束一个步骤"""
        start_time = self.step_times.get(step_name, {}).get("start")
        end_time = datetime.now()
        duration = ""

        if start_time:
            delta = end_time - start_time
            duration = f" (耗时: {delta.total_seconds():.2f}s)"

        status = "✓ 完成" if success else "✗ 失败"
        self.logger.info(
            f"[{self.workflow_name}] {status}: {step_name}{duration}"
            + (f" - {message}" if message else "")
        )
        self.step_times[step_name]["end"] = end_time

    def error(self, step_name: str, error: Exception):
        """记录步骤错误"""
        self.logger.error(
            f"[{self.workflow_name}] ✗ 错误: {step_name} - {type(error).__name__}: {str(error)}"
        )

    def info(self, message: str):
        """记录一般信息"""
        self.logger.info(f"[{self.workflow_name}] ℹ {message}")

    def debug(self, message: str):
        """记录调试信息"""
        self.logger.debug(f"[{self.workflow_name}] 🔍 {message}")


def get_workflow_logger(workflow_name: str) -> WorkflowLogger:
    """获取工作流程日志记录器"""
    return WorkflowLogger(_logger, workflow_name)


# ========== 对话记录日志工具 ==========

class ConversationLogger:
    """对话记录器 - 专门记录用户与Agent的完整对话历史"""

    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_logger()
        return cls._instance

    def _init_logger(self):
        """初始化对话记录器"""
        self._logger = logging.getLogger("studio.conversation")
        self._logger.setLevel(logging.INFO)

        # 避免重复添加 handler
        if self._logger.handlers:
            return

        # 对话记录文件 - JSON 格式
        log_dir = Path(__file__).parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"conversation_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = logging.FileHandler(
            log_file,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))

        self._logger.addHandler(file_handler)

    def log_user_message(self, session_id: str, message: str):
        """记录用户消息

        Args:
            session_id: 会话ID
            message: 用户发送的消息内容
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "user",
            "session_id": session_id,
            "content": message,
        }
        self._logger.info(json.dumps(log_entry, ensure_ascii=False))

    def log_assistant_message(self, session_id: str, message: str):
        """记录助手回复

        Args:
            session_id: 会话ID
            message: 助手回复内容
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "assistant",
            "session_id": session_id,
            "content": message,
        }
        self._logger.info(json.dumps(log_entry, ensure_ascii=False))


# 全局对话记录器实例
_conversation_logger = ConversationLogger()


def get_conversation_logger() -> ConversationLogger:
    """获取对话记录器"""
    return _conversation_logger


# ========== Agent API 调用日志工具 ==========

class AgentAPILogger:
    """Agent API 调用记录器 - 专门记录 Agent 发送给 LLM 的请求消息"""

    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_logger()
        return cls._instance

    def _init_logger(self):
        """初始化 API 调用记录器"""
        self._logger = logging.getLogger("studio.agent_api")
        self._logger.setLevel(logging.INFO)

        # 避免重复添加 handler
        if self._logger.handlers:
            return

        # API 调用记录文件 - JSON 格式
        log_dir = Path(__file__).parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"agent_api_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = logging.FileHandler(
            log_file,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))

        self._logger.addHandler(file_handler)

    def log_request(self, session_id: str, messages: list, tools: list = None):
        """记录 Agent 发送的 API 请求

        Args:
            session_id: 会话ID
            messages: 发送的消息列表 (List[Message])
            tools: 发送的工具列表
        """
        # 提取消息摘要（不记录完整的 base64 数据）
        message_summaries = []
        for i, msg in enumerate(messages):
            # 处理 Message 对象（通过属性访问）
            if hasattr(msg, 'model_dump'):
                # Pydantic 模型，使用 model_dump 转为字典
                msg_dict = msg.model_dump()
            elif hasattr(msg, '__dict__'):
                # 普通对象，转为字典
                msg_dict = msg.__dict__
            else:
                # 已经是字典
                msg_dict = msg

            msg_summary = {
                "index": i,
                "role": msg_dict.get("role", "unknown"),
            }

            content = msg_dict.get("content")
            if isinstance(content, list):
                # 多模态内容：提取类型和大小信息
                content_items = []
                for item in content:
                    if isinstance(item, dict):
                        if "image" in item:
                            # base64 图片数据，只记录长度
                            img_data = item["image"]
                            if isinstance(img_data, str) and len(img_data) > 100:
                                content_items.append({"type": "image", "length": len(img_data)})
                            else:
                                content_items.append({"type": "image", "data": img_data})
                        elif "text" in item:
                            content_items.append({"type": "text", "preview": str(item["text"])[:200]})
                        else:
                            content_items.append(item)
                    else:
                        content_items.append(str(item)[:200])
                msg_summary["content"] = content_items
            elif isinstance(content, str):
                msg_summary["content_preview"] = content[:500] if len(content) > 500 else content

            # 工具调用信息
            tool_calls = msg_dict.get("tool_calls")
            if tool_calls:
                tc_list = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        func = tc.get("function", {})
                        tc_list.append({
                            "id": tc.get("id"),
                            "type": tc.get("type"),
                            "function": func.get("name") if isinstance(func, dict) else str(func)
                        })
                    else:
                        tc_list.append(str(tc)[:100])
                msg_summary["tool_calls"] = tc_list

            message_summaries.append(msg_summary)

        # 工具摘要
        tool_summaries = []
        if tools:
            for tool in tools:
                if isinstance(tool, dict):
                    tool_summaries.append({
                        "type": tool.get("type"),
                        "name": tool.get("function", {}).get("name") if isinstance(tool.get("function"), dict) else str(tool.get("function", "unknown"))
                    })

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "api_request",
            "session_id": session_id,
            "message_count": len(messages),
            "messages": message_summaries,
            "tool_count": len(tools) if tools else 0,
            "tools": tool_summaries,
        }
        self._logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))

    def log_response(self, session_id: str, response_content: str, success: bool, error: str = None, latency_ms: float = None):
        """记录 LLM API 响应

        Args:
            session_id: 会话ID
            response_content: 响应内容
            success: 是否成功
            error: 错误信息（如果失败）
            latency_ms: 延迟（毫秒）
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "api_response",
            "session_id": session_id,
            "success": success,
            "content_preview": response_content[:1000] if response_content else None,
            "content_length": len(response_content) if response_content else 0,
            "error": error,
            "latency_ms": latency_ms,
        }
        self._logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))

    def log_tool_call(self, session_id: str, tool_name: str, arguments: dict, result_success: bool, result_preview: str = None):
        """记录工具调用

        Args:
            session_id: 会话ID
            tool_name: 工具名称
            arguments: 工具参数
            result_success: 是否成功
            result_preview: 结果预览
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "tool_call",
            "session_id": session_id,
            "tool_name": tool_name,
            "arguments_preview": str(arguments)[:500] if arguments else None,
            "success": result_success,
            "result_preview": result_preview[:500] if result_preview else None,
        }
        self._logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))


# 全局 Agent API 记录器实例
_agent_api_logger = AgentAPILogger()


def get_agent_api_logger() -> AgentAPILogger:
    """获取 Agent API 记录器"""
    return _agent_api_logger


# ========== 模式调试日志工具 ==========

class ModeDebugLogger:
    """模式调试日志记录器 - 分别记录三个模式下 Agent 的上下文和 API 调用"""

    _instance = None
    _loggers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_loggers()
        return cls._instance

    def _init_loggers(self):
        """初始化三个模式的日志记录器"""
        self._loggers = {}

        for mode in ["daily", "planning", "working"]:
            logger = logging.getLogger(f"studio.mode_debug.{mode}")
            logger.setLevel(logging.DEBUG)

            # 避免重复添加 handler
            if logger.handlers:
                self._loggers[mode] = logger
                continue

            # 日志文件
            log_dir = Path(__file__).parent.parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"mode_{mode}_{datetime.now().strftime('%Y%m%d')}.log"

            file_handler = logging.FileHandler(
                log_file,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(message)s"))

            logger.addHandler(file_handler)
            self._loggers[mode] = logger

    def _get_mode_name(self, mode) -> str:
        """获取模式名称"""
        if hasattr(mode, 'value'):
            return mode.value
        return str(mode).lower()

    def log_llm_request(self, mode, session_id: str, messages: list, tools: list):
        """记录 LLM 请求

        Args:
            mode: 当前模式 (AgentMode)
            session_id: 会话ID
            messages: 发送的消息列表
            tools: 发送的工具列表
        """
        mode_name = self._get_mode_name(mode)
        logger = self._loggers.get(mode_name)
        if not logger:
            return

        # 构建日志条目
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "LLM_REQUEST",
            "mode": mode_name,
            "session_id": session_id,
            "message_count": len(messages),
            "messages": [],
            "tool_count": len(tools) if tools else 0,
            "tools": [],
        }

        # 提取消息摘要
        for i, msg in enumerate(messages):
            msg_dict = {}
            if hasattr(msg, 'model_dump'):
                msg_dict = msg.model_dump()
            elif hasattr(msg, '__dict__'):
                msg_dict = msg.__dict__
            else:
                msg_dict = msg

            msg_summary = {
                "index": i,
                "role": msg_dict.get("role", "unknown"),
            }

            content = msg_dict.get("content")
            if isinstance(content, str):
                msg_summary["content_preview"] = content[:300] if content else ""
            elif isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            text_parts.append(str(item["text"])[:200])
                        elif "image" in item:
                            text_parts.append("[image]")
                msg_summary["content_preview"] = " | ".join(text_parts)

            tool_calls = msg_dict.get("tool_calls")
            if tool_calls:
                tc_list = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        func = tc.get("function", {})
                        tc_list.append(func.get("name") if isinstance(func, dict) else str(func))
                msg_summary["tool_calls"] = tc_list

            log_entry["messages"].append(msg_summary)

        # 提取工具摘要
        if tools:
            for tool in tools:
                if isinstance(tool, dict):
                    log_entry["tools"].append({
                        "name": tool.get("function", {}).get("name") if isinstance(tool.get("function"), dict) else str(tool.get("function", "unknown"))
                    })

        logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))

    def log_llm_response(self, mode, session_id: str, response_content: str, latency_ms: float = None):
        """记录 LLM 响应

        Args:
            mode: 当前模式
            session_id: 会话ID
            response_content: 响应内容
            latency_ms: 延迟（毫秒）
        """
        mode_name = self._get_mode_name(mode)
        logger = self._loggers.get(mode_name)
        if not logger:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "LLM_RESPONSE",
            "mode": mode_name,
            "session_id": session_id,
            "content_preview": response_content[:500] if response_content else "",
            "content_length": len(response_content) if response_content else 0,
            "latency_ms": latency_ms,
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))

    def log_mode_switch(self, mode, session_id: str, from_mode: str, to_mode: str, reason: str = ""):
        """记录模式切换

        Args:
            mode: 当前模式
            session_id: 会话ID
            from_mode: 原模式
            to_mode: 目标模式
            reason: 切换原因
        """
        mode_name = self._get_mode_name(mode)
        logger = self._loggers.get(mode_name)
        if not logger:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "MODE_SWITCH",
            "mode": mode_name,
            "session_id": session_id,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "reason": reason,
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))

    def log_tool_call(self, mode, session_id: str, tool_name: str, arguments: dict, result: str, success: bool):
        """记录工具调用

        Args:
            mode: 当前模式
            session_id: 会话ID
            tool_name: 工具名称
            arguments: 工具参数
            result: 执行结果
            success: 是否成功
        """
        mode_name = self._get_mode_name(mode)
        logger = self._loggers.get(mode_name)
        if not logger:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "TOOL_CALL",
            "mode": mode_name,
            "session_id": session_id,
            "tool_name": tool_name,
            "arguments_preview": str(arguments)[:300] if arguments else "",
            "result_preview": result[:300] if result else "",
            "success": success,
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))

    def log_system_context(self, mode, session_id: str, context: str):
        """记录系统上下文

        Args:
            mode: 当前模式
            session_id: 会话ID
            context: 上下文内容（system prompt）
        """
        mode_name = self._get_mode_name(mode)
        logger = self._loggers.get(mode_name)
        if not logger:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "SYSTEM_CONTEXT",
            "mode": mode_name,
            "session_id": session_id,
            "context_preview": context[:500] if context else "",
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2))


# 全局模式调试日志记录器实例
_mode_debug_logger = ModeDebugLogger()


def get_mode_debug_logger() -> ModeDebugLogger:
    """获取模式调试日志记录器"""
    return _mode_debug_logger
