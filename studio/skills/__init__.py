"""
Studio Skills 模块 - 通用 Skill 框架层

与 studio/skills/ 下的 BaseSkill（Phase 2 网关调用）不同，
这是 Agent Skill 框架，用于实现渐进式披露 + 按需加载的技能机制。

设计原则：
1. 对话历史驱动 - 通过检查对话历史判断技能状态
2. 线程安全 - 使用 threading.Lock 保护共享数据
3. 动态注册 - register() 只影响新的激活请求
4. Fail-Fast - 初始化时全量校验
"""

from .skill_base import SkillDefinition, SkillLoadError, SkillSummary
from .skill_registry import SkillRegistry
from .skill_tools import UseSkillTool, DeactivateSkillTool, PreviewSkillTool, CanvasToolResult
from .skill_enforcer import ToolEnforcer

__all__ = [
    # 数据模型
    "SkillDefinition",
    "SkillLoadError",
    "SkillSummary",
    # 核心类
    "SkillRegistry",
    "ToolEnforcer",
    # 工具类
    "UseSkillTool",
    "DeactivateSkillTool",
    "PreviewSkillTool",
    "CanvasToolResult",
]
