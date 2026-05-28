"""
MemoryType - 记忆类型枚举
"""

from enum import Enum


class MemoryType(str, Enum):
    """记忆类型"""

    # 短期记忆（会话级）
    SESSION_BRIEF = "session_brief"  # Brief 内容
    SESSION_PLAN = "session_plan"  # 内容方案
    SESSION_GENERATED = "session_generated"  # 生成的历史内容
    SESSION_FEEDBACK = "session_feedback"  # 用户反馈
    SESSION_REVIEW = "session_review"  # 审核结果

    # 长期记忆（用户级）
    USER_STYLE = "user_style"  # 用户风格偏好
    USER_BRAND = "user_brand"  # 品牌资产
    USER_TEMPLATE = "user_template"  # 成功文案模板
    USER_PREFERENCE = "user_preference"  # 其他偏好

    # 多模态记忆
    MULTIMODAL_IMAGE = "multimodal_image"  # 图片记忆
    MULTIMODAL_VIDEO = "multimodal_video"  # 视频记忆
    MULTIMODAL_AUDIO = "multimodal_audio"  # 音频记忆

    # 归档记忆
    ARCHIVED_MESSAGE = "archived_message"  # 归档的工作窗口消息

    @property
    def is_short_term(self) -> bool:
        """是否为短期记忆"""
        return self.name.startswith("SESSION_")

    @property
    def is_long_term(self) -> bool:
        """是否为长期记忆"""
        return self.name.startswith("USER_")

    @property
    def is_multimodal(self) -> bool:
        """是否为多模态记忆"""
        return self.name.startswith("MULTIMODAL_")
