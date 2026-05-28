"""工具过滤执行器 - 关键安全机制"""

import re
from typing import List, Optional, Set

from .skill_registry import SkillRegistry
from ..debug_logger import get_logger

logger = get_logger("skills.skill_enforcer")


class ToolEnforcer:
    """
    工具执行过滤器

    根据当前激活的技能，动态过滤可调用的工具列表。
    通过对话历史获取激活技能，天然持久化。
    """

    def __init__(self, all_tools: List, skill_registry: SkillRegistry, messages: list):
        """
        初始化 ToolEnforcer

        Args:
            all_tools: 所有可用工具列表
            skill_registry: 技能注册表
            messages: 对话历史列表
        """
        self.all_tools = all_tools
        self.skill_registry = skill_registry
        self.messages = messages
        self._allowed_names_cache: Optional[Set[str]] = None
        self._tool_name_map: Optional[dict] = None

    def _build_tool_name_map(self) -> dict:
        """构建工具名称映射"""
        if self._tool_name_map is None:
            self._tool_name_map = {t.name: t for t in self.all_tools}
        return self._tool_name_map

    def _get_active_skills_from_history(self) -> Set[str]:
        """从对话历史中解析已激活的技能"""
        active = set()
        for msg in self.messages:
            if msg.role == "tool":
                content = msg.content or ""
                # 匹配 "技能 'xxx' 已激活" 或 "技能 'xxx' 已经在激活状态"
                matches = re.findall(r"技能 '([^']+)' 已激活", content)
                active.update(matches)

        if active:
            logger.debug(f"[ToolEnforcer] Active skills from history: {active}")
        return active

    def get_allowed_tools(self) -> List:
        """获取当前允许调用的工具列表"""
        allowed_names = self._get_allowed_names()
        if not allowed_names:
            # 空集合表示全部允许
            logger.debug(f"[ToolEnforcer] No active skills, allowing all {len(self.all_tools)} tools")
            return self.all_tools

        tool_map = self._build_tool_name_map()
        allowed = [tool_map[name] for name in allowed_names if name in tool_map]
        logger.debug(f"[ToolEnforcer] Allowing {len(allowed)} tools: {allowed_names}")
        return allowed

    def is_tool_allowed(self, tool_name: str) -> bool:
        """检查工具是否在当前允许列表中"""
        allowed_names = self._get_allowed_names()
        if not allowed_names:
            # 空集合表示全部允许
            return True
        allowed = tool_name in allowed_names
        if not allowed:
            logger.warning(f"[ToolEnforcer] Tool '{tool_name}' NOT allowed, active skills restrict to: {allowed_names}")
        return allowed

    def _get_allowed_names(self) -> Set[str]:
        """获取允许的工具名称集合（带缓存）"""
        active = self._get_active_skills_from_history()
        if not active:
            return set()  # 空集合表示全部允许

        # 缓存有效，无需每次重新计算
        if self._allowed_names_cache is not None:
            logger.debug(f"[ToolEnforcer] Using cached allowed names: {self._allowed_names_cache}")
            return self._allowed_names_cache

        allowed_names: Set[str] = set()
        for skill_name in active:
            allowed = self.skill_registry.get_allowed_tools(skill_name)
            logger.debug(f"[ToolEnforcer] Skill '{skill_name}' allowed_tools: {allowed}")
            if allowed:
                allowed_names.update(allowed)
            else:
                # 技能无 allowed_tools 限制，返回空集合（表示全部允许）
                logger.info(f"[ToolEnforcer] Skill '{skill_name}' has no tool restrictions, allowing all tools")
                self._allowed_names_cache = set()
                return set()

        logger.info(f"[ToolEnforcer] Computed allowed names: {allowed_names}")
        self._allowed_names_cache = allowed_names
        return allowed_names

    def invalidate_cache(self):
        """清除缓存（技能状态变化时调用）"""
        logger.debug(f"[ToolEnforcer] Cache invalidated")
        self._allowed_names_cache = None