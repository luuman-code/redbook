"""Model configuration Pydantic models"""

from pydantic import BaseModel
from typing import Dict, Optional, Any
from enum import Enum


class ModelType(str, Enum):
    """模型类型枚举"""
    LLM = "llm"
    VISION = "vision"
    IMAGE_GENERATION = "image_generation"
    TTS = "tts"
    VIDEO = "video"
    VIDEO_T2V = "video_t2v"
    VIDEO_I2V = "video_i2v"
    VIDEO_R2V = "video_r2v"
    VIDEO_EDIT = "video_edit"


class ModelProviderConfig(BaseModel):
    """模型提供商配置"""
    provider: str
    api_url: str
    model_name: str
    api_key: str
    default_params: Dict[str, Any] = {}
    timeout: int = 60
    retry_count: int = 3
    enabled: bool = True


class ModelConfig(BaseModel):
    """模型配置（包含主配置和备用配置）"""
    primary: ModelProviderConfig
    fallback: Optional[ModelProviderConfig] = None
