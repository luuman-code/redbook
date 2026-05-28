"""通用 Skill 工具 - 可被所有 Agent 复用"""

import re
from typing import List, Optional

from mini_agent.tools.base import Tool

from .skill_base import SkillSummary
from ..debug_logger import get_logger

logger = get_logger("skills.skill_tools")


class CanvasToolResult:
    """工具执行结果 - 用于 Skill 相关工具"""

    def __init__(self, success: bool, content: str = "", error: str = ""):
        self.success = success
        self.content = content
        self.error = error


class UseSkillTool(Tool):
    """
    所有 Agent 共享的 use_skill 工具

    通过检查对话历史判断技能是否已激活，无需单独的状态管理
    """

    def __init__(self, skill_registry, messages, tool_enforcer=None):
        self.skill_registry = skill_registry
        self.messages = messages  # 对话历史列表
        self.tool_enforcer = tool_enforcer
        # 模式检查回调：接受技能名称，返回是否允许激活
        self._skill_allowed_checker = None

    def set_skill_allowed_checker(self, checker):
        """设置技能允许检查回调

        Args:
            checker: 接受 skill_name 参数，返回 bool 表示是否允许激活
        """
        self._skill_allowed_checker = checker

    @property
    def name(self) -> str:
        return "use_skill"

    @property
    def description(self) -> str:
        return """激活指定技能，使其指令生效。

激活技能后，AI 将严格遵循该技能的指令。
如果技能已激活，会提示已激活状态。

Args:
    name: 技能名称（如 canvas_draw, canvas_understand 等）

使用 use_skill(name) 激活技能后，AI 会获取该技能的完整指令。
如需查看技能概要而非直接激活，请使用 preview_skill(name)。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "技能名称"
                }
            },
            "required": ["name"]
        }

    def _is_skill_active(self, name: str) -> bool:
        """检查技能是否已在历史中激活"""
        for msg in self.messages:
            if msg.role == "tool":
                content = msg.content or ""
                if f"技能 '{name}' 已激活" in content or f"技能 '{name}' 已经在激活状态" in content:
                    return True
        return False

    async def execute(self, name: str) -> CanvasToolResult:
        """执行技能激活"""
        logger.info(f"[UseSkillTool] Attempting to activate skill: {name}")

        # 通过对话历史检查是否已激活
        if self._is_skill_active(name):
            logger.info(f"[UseSkillTool] Skill '{name}' already active in history")
            return CanvasToolResult(
                success=True,
                content=f"技能 '{name}' 已激活，请继续遵循其指令。"
            )

        # 检查技能是否允许激活（模式限制）
        if self._skill_allowed_checker and not self._skill_allowed_checker(name):
            logger.warning(f"[UseSkillTool] Skill '{name}' is not allowed in current mode")
            return CanvasToolResult(
                success=False,
                error=f"技能 '{name}' 在当前模式下不允许激活。在规划模式下只能使用 canvas_understand 和 canvas_planning 技能。"
            )

        # 获取完整 prompt
        prompt = self.skill_registry.get_skill_prompt(name)
        if not prompt:
            # 获取可用技能列表，引导重新选择
            summaries = self.skill_registry.get_all_summaries()
            available = ", ".join([s.name for s in summaries]) if summaries else "无"
            logger.warning(f"[UseSkillTool] Skill '{name}' not found, available: {available}")
            return CanvasToolResult(
                success=False,
                error=f"技能 '{name}' 不存在。可用技能列表：{available}。请从中选择一个正确的技能名称。"
            )

        # 获取 allowed_tools 用于日志
        allowed_tools = self.skill_registry.get_allowed_tools(name)
        logger.info(f"[UseSkillTool] Activating skill '{name}', allowed_tools: {allowed_tools}")

        # 清除工具缓存
        if self.tool_enforcer:
            self.tool_enforcer.invalidate_cache()
            logger.debug(f"[UseSkillTool] ToolEnforcer cache invalidated")

        # 返回完整 prompt（注入一次）
        logger.info(f"[UseSkillTool] Skill '{name}' activated successfully, prompt length: {len(prompt)}")
        return CanvasToolResult(
            success=True,
            content=f"技能 '{name}' 已激活：\n\n{prompt}\n\n请严格遵循以上指令。"
        )


class DeactivateSkillTool(Tool):
    """
    所有 Agent 共享的 deactivate_skill 工具

    通过对话历史判断，无需单独状态
    """

    def __init__(self, skill_registry, messages, tool_enforcer=None):
        self.skill_registry = skill_registry
        self.messages = messages
        self.tool_enforcer = tool_enforcer

    @property
    def name(self) -> str:
        return "deactivate_skill"

    @property
    def description(self) -> str:
        return """卸载指定技能，不再遵循其指令。

Args:
    name: 技能名称

注意：如需重新激活技能，在后续对话中使用 use_skill(name)。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "技能名称"
                }
            },
            "required": ["name"]
        }

    async def execute(self, name: str) -> CanvasToolResult:
        """执行技能卸载"""
        logger.info(f"[DeactivateSkillTool] Deactivating skill: {name}")

        # 清除工具缓存
        if self.tool_enforcer:
            self.tool_enforcer.invalidate_cache()
            logger.debug(f"[DeactivateSkillTool] ToolEnforcer cache invalidated")

        return CanvasToolResult(
            success=True,
            content=f"技能 '{name}' 已卸载，不再遵循其指令。（如需重新激活，请在后续对话中使用 use_skill）"
        )


class PreviewSkillTool(Tool):
    """
    所有 Agent 共享的 preview_skill 工具

    第二级渐进式披露：返回 catalog_instruction 而非完整 prompt
    用于 Agent 犹豫或不确定是否需要激活时，获取技能概要
    """

    def __init__(self, skill_registry, messages):
        self.skill_registry = skill_registry
        self.messages = messages

    @property
    def name(self) -> str:
        return "preview_skill"

    @property
    def description(self) -> str:
        return """预览技能概要（第二级披露），不激活技能。

返回技能的 catalog_instruction，用于在激活前了解技能用途。
如果技能已激活，返回提示信息。

Args:
    name: 技能名称

使用 preview_skill(name) 可以查看技能概要而非直接激活。
如需激活技能，请使用 use_skill(name)。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "技能名称"
                }
            },
            "required": ["name"]
        }

    def _is_skill_active(self, name: str) -> bool:
        """检查技能是否已在历史中激活"""
        for msg in self.messages:
            if msg.role == "tool":
                content = msg.content or ""
                if f"技能 '{name}' 已激活" in content or f"技能 '{name}' 已经在激活状态" in content:
                    return True
        return False

    async def execute(self, name: str) -> CanvasToolResult:
        """执行技能预览"""
        logger.info(f"[PreviewSkillTool] Previewing skill: {name}")

        # 检查是否已激活
        if self._is_skill_active(name):
            logger.info(f"[PreviewSkillTool] Skill '{name}' already active")
            return CanvasToolResult(
                success=True,
                content=f"技能 '{name}' 已激活，请直接使用。如需完整指令请再次调用 use_skill('{name}')。"
            )

        # 获取 catalog_instruction（第二级披露）
        catalog_instruction = self.skill_registry.get_skill_catalog_instruction(name)
        if not catalog_instruction:
            # 获取可用技能列表，引导重新选择
            summaries = self.skill_registry.get_all_summaries()
            available = ", ".join([s.name for s in summaries]) if summaries else "无"
            logger.warning(f"[PreviewSkillTool] Skill '{name}' has no catalog_instruction, available: {available}")
            return CanvasToolResult(
                success=False,
                error=f"技能 '{name}' 不存在或未定义 catalog_instruction。可用技能：{available}。请选择一个正确的技能名称。"
            )

        logger.info(f"[PreviewSkillTool] Returning catalog for skill '{name}': {catalog_instruction[:100]}...")
        return CanvasToolResult(
            success=True,
            content=f"【技能概要】{name}：\n\n{catalog_instruction}\n\n如需完整指令，请调用 use_skill('{name}')。"
        )