"""
Session 数据结构 - 创作会话

管理整个创作流程的状态和历史
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .brief import Brief
from .content_plan import ContentPlan
from .content_item import ContentItem
from .version import Version
from .message import Message


class SessionStatus(Enum):
    """会话状态"""
    CREATED = "created"           # 已创建
    PLANNING = "planning"         # 规划中
    GENERATING = "generating"      # 生成中
    REVIEWING = "reviewing"        # 审核中
    ITERATING = "iterating"        # 迭代中
    COMPLETED = "completed"        # 完成
    PUBLISHED = "published"        # 已发布
    CANCELLED = "cancelled"       # 已取消
    CONFIRMED = "confirmed"  # 方案已确认，待生成


@dataclass
class Session:
    """
    创作会话

    属性说明：
    - session_id: 唯一标识符
    - brief: 需求解析结果
    - current_plan: 当前内容方案
    - current_version: 当前版本号
    - items: 内容项列表
    - status: 会话状态
    - created_at: 创建时间
    - updated_at: 更新时间
    - versions: 版本历史
    """
    session_id: str
    brief: Brief
    current_plan: ContentPlan
    current_version: int = 1
    items: List[ContentItem] = field(default_factory=list)
    status: SessionStatus = SessionStatus.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    versions: List[Version] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)  # 对话消息历史

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "brief": self.brief.to_dict() if isinstance(self.brief, Brief) else self.brief,
            "current_plan": self.current_plan.to_dict() if isinstance(self.current_plan, ContentPlan) else self.current_plan,
            "current_version": self.current_version,
            "items": [item.to_dict() if isinstance(item, ContentItem) else item for item in self.items],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "versions": [v.to_dict() if isinstance(v, Version) else v for v in self.versions],
            "metadata": self.metadata,
            "messages": [msg.to_dict() if isinstance(msg, Message) else msg for msg in self.messages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """从字典创建"""
        data = data.copy()

        if "brief" in data and isinstance(data["brief"], dict):
            data["brief"] = Brief.from_dict(data["brief"])

        if "current_plan" in data and isinstance(data["current_plan"], dict):
            data["current_plan"] = ContentPlan.from_dict(data["current_plan"])

        if "items" in data:
            data["items"] = [
                ContentItem.from_dict(item) if isinstance(item, dict) else item
                for item in data["items"]
            ]

        if "status" in data and isinstance(data["status"], str):
            data["status"] = SessionStatus(data["status"])

        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])

        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        if "versions" in data:
            data["versions"] = [
                Version.from_dict(v) if isinstance(v, dict) else v
                for v in data["versions"]
            ]

        if "messages" in data:
            data["messages"] = [
                Message.from_dict(m) if isinstance(m, dict) else m
                for m in data["messages"]
            ]

        return cls(**data)

    def get_item(self, item_id: str) -> Optional[ContentItem]:
        """根据 ID 获取内容项"""
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def get_items_by_type(self, item_type) -> List[ContentItem]:
        """根据类型获取内容项"""
        from .content_item import ContentType
        if isinstance(item_type, str):
            item_type = ContentType(item_type)
        return [item for item in self.items if item.item_type == item_type]

    def update_status(self, status: SessionStatus) -> None:
        """更新会话状态"""
        self.status = status
        self.updated_at = datetime.now()

    def touch(self) -> None:
        """更新会话时间戳"""
        self.updated_at = datetime.now()
