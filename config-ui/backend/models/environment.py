"""Environment configuration models"""

from pydantic import BaseModel
from typing import Dict
from .model_config import ModelConfig, ModelType


class EnvironmentConfig(BaseModel):
    """环境配置"""
    name: str
    description: str = ""
    is_active: bool = False
    models: Dict[ModelType, ModelConfig] = {}


class AppConfig(BaseModel):
    """应用配置"""
    environments: Dict[str, EnvironmentConfig]
    active_environment: str
