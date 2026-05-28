"""
Message 数据结构 - 对话消息

用于存储聊天交互中的消息历史
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """
    对话消息

    属性说明：
    - message_id: 唯一标识符
    - role: 角色 (user/assistant/system/tool)
    - content: 消息内容
    - timestamp: 时间戳
    - metadata: 元数据 (可选)
        - suggested_actions: 建议操作列表
        - attachments: 附件列表
        - message_type: 消息类型 ("text" / "plan" / "content")
        - plan_data: 方案数据 (当 message_type 为 "plan" 时)
        - tool_call_id: 工具调用 ID (当 role 为 "tool" 时)
        - name: 工具名称 (当 role 为 "tool" 时)
    """
    message_id: str
    role: str  # "user" / "assistant" / "system" / "tool"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # tool 相关字段
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    @property
    def message_type(self) -> str:
        """获取消息类型，默认 "text" """
        return self.metadata.get("message_type", "text")

    @property
    def plan_data(self) -> Optional[Dict[str, Any]]:
        """获取方案数据（仅当 message_type 为 "plan" 时有效）"""
        if self.message_type == "plan":
            return self.metadata.get("plan_data")
        return None

    def is_plan_message(self) -> bool:
        """判断是否为方案消息"""
        return self.message_type == "plan"

    def is_text_message(self) -> bool:
        """判断是否为文本消息"""
        return self.message_type == "text"

    def with_plan_data(self, plan_data: Dict[str, Any]) -> "Message":
        """创建带有方案数据的副本"""
        new_metadata = self.metadata.copy()
        new_metadata["message_type"] = "plan"
        new_metadata["plan_data"] = plan_data
        return Message(
            message_id=self.message_id,
            role=self.role,
            content=self.content,
            timestamp=self.timestamp,
            metadata=new_metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        # 添加 tool 相关字段
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.name:
            result["name"] = self.name
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典创建"""
        data = data.copy()

        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        return cls(**data)

    def to_web_dict(self) -> Dict[str, Any]:
        """转换为 WebSocket 传输格式"""
        return {
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }