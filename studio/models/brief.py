"""
Brief 数据结构 - 用户需求解析结果

参考 plan.md 中的 Brief 结构设计
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ContentGoal(Enum):
    """内容目标类型"""
    PLANT = "plant"       # 种草
    TUTORIAL = "tutorial" # 教程
    REVIEW = "review"     # 测评
    LIFESTYLE = "lifestyle"  # 生活分享
    PRODUCT = "product"   # 产品展示
    OTHER = "other"       # 其他


@dataclass
class Material:
    """参考素材"""
    material_id: str
    material_type: str  # image, video, text, url
    url: Optional[str] = None
    content: Optional[str] = None  # base64 for images
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Brief:
    """
    用户需求解析结果

    属性说明：
    - goal: 内容目标（种草/测评/教程等）
    - style: 风格（活泼/专业/治愈等）
    - keywords: 关键词/卖点
    - must_include: 必须包含的元素
    - image_style: 配图风格偏好
    - need_video: 是否需要视频
    - need_voiceover: 是否需要配音
    - target_audience: 目标受众
    - reference_materials: 参考素材
    - raw_input: 原始用户输入
    """
    id: str
    goal: ContentGoal
    style: str
    keywords: List[str] = field(default_factory=list)
    must_include: List[str] = field(default_factory=list)
    image_style: str = "摄影实拍"  # 摄影实拍/插画/3D
    need_video: bool = False
    need_voiceover: bool = False
    need_text: bool = True      # 是否需要文案
    need_images: bool = True    # 是否需要配图
    need_bgm: bool = False
    bgm_preference: str = "轻快"  # 轻快/舒缓
    target_audience: str = ""
    reference_materials: List[Material] = field(default_factory=list)
    raw_input: str = ""
    extracted_product_info: Dict[str, Any] = field(default_factory=dict)  # 从参考图提取的产品信息
    template_image_url: Optional[str] = None  # 文案模板图片 URL
    template_analysis: List[Dict[str, Any]] = field(default_factory=list)  # 模板分析结果
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "goal": self.goal.value,
            "style": self.style,
            "keywords": self.keywords,
            "must_include": self.must_include,
            "image_style": self.image_style,
            "need_video": self.need_video,
            "need_voiceover": self.need_voiceover,
            "need_text": self.need_text,
            "need_images": self.need_images,
            "need_bgm": self.need_bgm,
            "bgm_preference": self.bgm_preference,
            "target_audience": self.target_audience,
            "reference_materials": [
                {
                    "material_id": m.material_id,
                    "material_type": m.material_type,
                    "url": m.url,
                    "content": m.content,  # 保留 base64 图片内容
                    "description": m.description,
                }
                for m in self.reference_materials
            ],
            "raw_input": self.raw_input,
            "extracted_product_info": self.extracted_product_info,
            "template_image_url": self.template_image_url,
            "template_analysis": self.template_analysis,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Brief":
        """从字典创建"""
        data = data.copy()
        if "goal" in data and isinstance(data["goal"], str):
            data["goal"] = ContentGoal(data["goal"])
        if "reference_materials" in data:
            data["reference_materials"] = [
                Material(**m) if isinstance(m, dict) else m
                for m in data["reference_materials"]
            ]
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
