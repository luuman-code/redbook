"""
MemoryItem - 记忆条目数据模型
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MultimodalResource:
    """多模态资源"""
    resource_type: str  # image, video, audio
    url: Optional[str] = None
    base64_content: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryItem:
    """记忆条目"""

    # 基本信息
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: str = ""  # MemoryType enum value

    # 内容
    content: str = ""  # 文本内容

    # 向量嵌入（可选，用于向量搜索）
    vector: Optional[List[float]] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 多模态资源
    multimodal_resources: List[MultimodalResource] = field(default_factory=list)

    # 关联信息
    session_id: Optional[str] = None
    user_id: Optional[str] = "default"

    # 重要性与访问
    importance: float = 1.0  # 0.0 - 1.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "vector": self.vector,
            "metadata": self.metadata,
            "multimodal_resources": [
                {
                    "resource_type": r.resource_type,
                    "url": r.url,
                    "description": r.description,
                }
                for r in self.multimodal_resources
            ],
            "session_id": self.session_id,
            "user_id": self.user_id,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """从字典创建"""
        multimodal_resources = []
        for r in data.get("multimodal_resources", []):
            multimodal_resources.append(MultimodalResource(
                resource_type=r.get("resource_type", ""),
                url=r.get("url"),
                description=r.get("description"),
            ))

        last_accessed = None
        if data.get("last_accessed"):
            last_accessed = datetime.fromisoformat(data["last_accessed"])

        created_at = datetime.now()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        updated_at = datetime.now()
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            memory_type=data.get("memory_type", ""),
            content=data.get("content", ""),
            vector=data.get("vector"),
            metadata=data.get("metadata", {}),
            multimodal_resources=multimodal_resources,
            session_id=data.get("session_id"),
            user_id=data.get("user_id", "default"),
            importance=data.get("importance", 1.0),
            access_count=data.get("access_count", 0),
            last_accessed=last_accessed,
            created_at=created_at,
            updated_at=updated_at,
        )

    def to_text(self) -> str:
        """转为纯文本（用于 LLM 上下文）"""
        parts = [f"[{self.memory_type}]"]
        parts.append(self.content)

        if self.metadata:
            meta_str = ", ".join([f"{k}: {v}" for k, v in self.metadata.items()])
            parts.append(f"元数据: {meta_str}")

        return "\n".join(parts)

    def record_access(self):
        """记录一次访问"""
        self.access_count += 1
        self.last_accessed = datetime.now()
