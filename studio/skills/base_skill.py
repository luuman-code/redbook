"""
BaseSkill - Skill 基类

封装 Phase 2 网关调用，提供统一的 Skill 接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.content_item import ContentItem


@dataclass
class SkillContext:
    """
    Skill 执行上下文

    包含执行 Skill 所需的所有信息
    """
    brief_id: str
    session_id: str
    version: int
    previous_items: List[ContentItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def get_previous_content(self, item_type: str) -> Optional[str]:
        """获取之前同类内容"""
        for item in self.previous_items:
            if item.item_type.value == item_type and item.content:
                return item.content
        return None


@dataclass
class SkillResult:
    """
    Skill 执行结果

    标准化的 Skill 返回格式
    """
    success: bool
    items: List[ContentItem] = field(default_factory=list)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0


class BaseSkill(ABC):
    """
    Skill 基类

    所有 Skill 必须继承此类并实现 execute 方法
    """

    # Skill 类型标识
    SKILL_TYPE: str = "base"

    def __init__(self, gateway_factory=None):
        """
        初始化 Skill

        Args:
            gateway_factory: GatewayFactory 实例（Phase 2）
        """
        self.gateway_factory = gateway_factory
        self._gateway = None

    @property
    @abstractmethod
    def gateway_type(self) -> str:
        """返回关联的网关类型"""
        pass

    @property
    def gateway(self):
        """获取网关实例（懒加载）"""
        if self._gateway is None and self.gateway_factory:
            self._gateway = self.gateway_factory.get_gateway(self.gateway_type)
        return self._gateway

    @gateway.setter
    def gateway(self, value):
        """直接设置网关实例"""
        self._gateway = value

    @abstractmethod
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """
        执行 Skill

        Args:
            context: Skill 上下文
            **kwargs: Skill 特定参数

        Returns:
            SkillResult
        """
        pass

    def validate_context(self, context: SkillContext) -> Optional[str]:
        """
        验证上下文

        Args:
            context: Skill 上下文

        Returns:
            如果验证失败，返回错误信息
        """
        if not context.brief_id:
            return "brief_id 不能为空"
        if not context.session_id:
            return "session_id 不能为空"
        return None

    def create_error_result(self, error: str) -> SkillResult:
        """创建错误结果"""
        return SkillResult(
            success=False,
            error=error,
        )

    def create_success_result(
        self,
        items: List[ContentItem] = None,
        warnings: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> SkillResult:
        """创建成功结果"""
        return SkillResult(
            success=True,
            items=items or [],
            warnings=warnings or [],
            metadata=metadata or {},
        )
