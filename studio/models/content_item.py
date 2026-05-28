"""
ContentItem 数据结构 - 内容项

每个生成单位（标题、段落、每张图片）视为独立模块，拥有唯一 ID
参考 plan.md 中的设计理念
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ContentType(Enum):
    """内容项类型"""
    TITLE = "title"
    HEADLINE = "headline"
    TEXT = "text"           # 正文段落
    HASHTAG = "hashtag"     # 话题标签
    CALL_TO_ACTION = "cta"  # 互动引导
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    COMPOSITE = "composite"  # 组合内容（图文组合等）


class ItemStatus(Enum):
    """内容项状态"""
    PENDING = "pending"       # 待生成
    GENERATING = "generating" # 生成中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 生成失败
    SKIPPED = "skipped"       # 跳过（可选内容）


@dataclass
class Revision:
    """修改记录"""
    revision_id: str
    revised_at: datetime
    revised_by: str  # user/critic/iterator
    change_summary: str  # 修改摘要
    previous_content: str = ""
    new_content: str = ""
    affected_fields: List[str] = field(default_factory=list)


@dataclass
class ContentItem:
    """
    单个内容项

    属性说明：
    - item_id: 唯一标识符
    - item_type: 内容类型
    - content: 文本内容或 URL
    - metadata: 元数据（尺寸、时长等）
    - status: 状态
    - generation_prompt: 生成时使用的提示词
    - revision_history: 修改历史
    """
    item_id: str
    item_type: ContentType
    content: str = ""  # 文本内容或 URL/base64
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: ItemStatus = ItemStatus.PENDING
    generation_prompt: str = ""
    revision_history: List[Revision] = field(default_factory=list)
    parent_id: Optional[str] = None  # 父内容项 ID（如某段落下的图片）
    position: int = 0  # 位置顺序
    error_message: Optional[str] = None
    local_path: Optional[str] = None  # 本地文件路径

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "status": self.status.value,
            "generation_prompt": self.generation_prompt,
            "revision_history": [
                {
                    "revision_id": r.revision_id,
                    "revised_at": r.revised_at.isoformat() if hasattr(r.revised_at, 'isoformat') else r.revised_at,
                    "revised_by": r.revised_by,
                    "change_summary": r.change_summary,
                    "previous_content": r.previous_content,
                    "new_content": r.new_content,
                    "affected_fields": r.affected_fields,
                }
                for r in self.revision_history
            ],
            "parent_id": self.parent_id,
            "position": self.position,
            "error_message": self.error_message,
            "local_path": self.local_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentItem":
        """从字典创建"""
        data = data.copy()
        if "item_type" in data and isinstance(data["item_type"], str):
            data["item_type"] = ContentType(data["item_type"])
        if "status" in data and isinstance(data["status"], str):
            data["status"] = ItemStatus(data["status"])
        if "revision_history" in data:
            data["revision_history"] = [
                Revision(**r) if isinstance(r, dict) else r
                for r in data["revision_history"]
            ]
        return cls(**data)

    def add_revision(self, revised_by: str, change_summary: str, new_content: str) -> Revision:
        """添加修改记录"""
        revision = Revision(
            revision_id=f"{self.item_id}_rev_{len(self.revision_history) + 1}",
            revised_at=datetime.now(),
            revised_by=revised_by,
            change_summary=change_summary,
            previous_content=self.content,
            new_content=new_content,
            affected_fields=["content"],
        )
        self.revision_history.append(revision)
        self.content = new_content
        return revision
