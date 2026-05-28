"""
ContentPlan 数据结构 - 内容方案

参考 plan.md 中的 ContentPlan 结构设计
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TextSection:
    """文案段落"""
    section_id: str
    section_type: str  # headline/title/paragraph/hashtag/call_to_action
    content: str = ""
    content_words: Optional[int] = None  # 目标字数
    priority: int = 1  # 生成优先级
    is_optional: bool = False


@dataclass
class ImagePlan:
    """配图方案"""
    style: str  # 日系胶片摄影/插画/3D/CG等
    elements: List[str] = field(default_factory=list)  # 画面元素描述
    count: int = 1  # 配图数量
    aspect_ratio: str = "1:1"  # 宽高比
    color_scheme: Optional[str] = None  # 色调偏好
    reference_image_ids: List[str] = field(default_factory=list)  # 参考图片ID


@dataclass
class VideoPlan:
    """视频方案"""
    duration: int = 15  # 秒
    scenes: List[Dict[str, Any]] = field(default_factory=list)  # 场景描述
    voiceover: str = ""  # 旁白要求
    voice_type: str = "温柔女声"  # 声音类型
    style: str = "生活记录"  # 视频风格
    has_bgm: bool = True
    bgm_style: str = "轻快vlog"
    model_type: str = "t2v"  # 视频模型类型: t2v(文生视频), i2v(图生视频), r2v(图文视频), video-edit(视频剪辑)
    ratio: str = "16:9"  # 视频比例: 16:9(横屏), 9:16(竖屏), 1:1(方形)


@dataclass
class AudioPlan:
    """音频方案"""
    tts_text: str = ""  # TTS 文本
    voice: str = "alloy"  # 音色
    speed: float = 1.0  # 语速
    bgm_style: Optional[str] = None  # BGM 风格


@dataclass
class ContentPlan:
    """
    完整内容方案

    属性说明：
    - brief_id: 关联的 Brief ID
    - title: 标题
    - text_sections: 文案结构
    - image_plan: 配图方案
    - video_plan: 视频方案（可选）
    - audio_plan: 音频方案（可选）
    - estimated_duration: 预计创作时间（分钟）
    - version: 方案版本号
    """
    plan_id: str
    brief_id: str
    title: str = ""
    text_sections: List[TextSection] = field(default_factory=list)
    image_plan: Optional[ImagePlan] = None
    video_plan: Optional[VideoPlan] = None
    audio_plan: Optional[AudioPlan] = None
    estimated_duration: int = 30  # 分钟
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "plan_id": self.plan_id,
            "brief_id": self.brief_id,
            "title": self.title,
            "text_sections": [
                {
                    "section_id": s.section_id,
                    "section_type": s.section_type,
                    "content": s.content,
                    "content_words": s.content_words,
                    "priority": s.priority,
                    "is_optional": s.is_optional,
                }
                for s in self.text_sections
            ],
            "image_plan": {
                "style": self.image_plan.style if self.image_plan else "",
                "elements": self.image_plan.elements if self.image_plan else [],
                "count": self.image_plan.count if self.image_plan else 0,
                "aspect_ratio": self.image_plan.aspect_ratio if self.image_plan else "1:1",
                "color_scheme": self.image_plan.color_scheme if self.image_plan else None,
                "reference_image_ids": self.image_plan.reference_image_ids if self.image_plan else [],
            } if self.image_plan else None,
            "video_plan": {
                "duration": self.video_plan.duration if self.video_plan else 0,
                "scenes": self.video_plan.scenes if self.video_plan else [],
                "voiceover": self.video_plan.voiceover if self.video_plan else "",
                "voice_type": self.video_plan.voice_type if self.video_plan else "",
                "style": self.video_plan.style if self.video_plan else "",
            } if self.video_plan else None,
            "audio_plan": {
                "tts_text": self.audio_plan.tts_text if self.audio_plan else "",
                "voice": self.audio_plan.voice if self.audio_plan else "",
                "speed": self.audio_plan.speed if self.audio_plan else 1.0,
                "bgm_style": self.audio_plan.bgm_style if self.audio_plan else None,
            } if self.audio_plan else None,
            "estimated_duration": self.estimated_duration,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentPlan":
        """从字典创建"""
        data = data.copy()

        if "text_sections" in data:
            data["text_sections"] = [
                TextSection(**s) if isinstance(s, dict) else s
                for s in data["text_sections"]
            ]

        if "image_plan" in data and data["image_plan"]:
            data["image_plan"] = ImagePlan(**data["image_plan"])

        if "video_plan" in data and data["video_plan"]:
            data["video_plan"] = VideoPlan(**data["video_plan"])

        if "audio_plan" in data and data["audio_plan"]:
            data["audio_plan"] = AudioPlan(**data["audio_plan"])

        return cls(**data)
