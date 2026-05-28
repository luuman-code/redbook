"""
Version 数据结构 - 版本记录

记录每个版本的完整快照，支持版本回退
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .content_plan import ContentPlan
from .content_item import ContentItem


@dataclass
class Version:
    """
    版本记录

    属性说明：
    - version_id: 版本标识符
    - version_number: 版本号
    - session_id: 关联的会话 ID
    - plan_snapshot: 内容方案快照
    - items_snapshot: 内容项快照
    - change_summary: 版本变更说明
    - created_by: 创建者（user/critic/iterator）
    - created_at: 创建时间
    """
    version_id: str
    version_number: int
    session_id: str
    plan_snapshot: Dict[str, Any]  # ContentPlan 的字典快照
    items_snapshot: List[Dict[str, Any]]  # ContentItem 列表的字典快照
    change_summary: str = ""
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version_id": self.version_id,
            "version_number": self.version_number,
            "session_id": self.session_id,
            "plan_snapshot": self.plan_snapshot,
            "items_snapshot": self.items_snapshot,
            "change_summary": self.change_summary,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Version":
        """从字典创建"""
        data = data.copy()
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)

    @classmethod
    def create_snapshot(
        cls,
        session_id: str,
        version_number: int,
        plan: ContentPlan,
        items: List[ContentItem],
        change_summary: str = "",
        created_by: str = "system",
    ) -> "Version":
        """创建版本快照"""
        return cls(
            version_id=f"{session_id}_v{version_number}",
            version_number=version_number,
            session_id=session_id,
            plan_snapshot=plan.to_dict() if isinstance(plan, ContentPlan) else plan,
            items_snapshot=[
                item.to_dict() if isinstance(item, ContentItem) else item
                for item in items
            ],
            change_summary=change_summary,
            created_by=created_by,
        )


@dataclass
class Revision:
    """
    修改记录（精简版，用于快速追踪）

    与 ContentItem 中的 Revision 的区别：
    - ContentItem.Revision 是内容项级别的修改历史
    - 这个 Revision 是会话级别的修改记录
    """
    revision_id: str
    version_id: str  # 修改后对应的版本
    item_id: str    # 被修改的内容项
    revision_type: str  # modify/delete/replace
    change_summary: str
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "user"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "revision_id": self.revision_id,
            "version_id": self.version_id,
            "item_id": self.item_id,
            "revision_type": self.revision_type,
            "change_summary": self.change_summary,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }
