"""
Studio 配置

定义 Studio 级别的配置，与 Phase 2 的 agent/config/config_service.py 解耦
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StudioConfig:
    """
    Studio 配置类

    管理：
    - 最大迭代次数
    - 默认语言
    - Prompt 模板路径
    - 存储路径等
    """

    # 迭代控制
    max_iterations: int = 5  # 最大修改轮次
    iteration_timeout: int = 300  # 迭代超时（秒）

    # 内容规范
    prohibited_words: List[str] = field(default_factory=list)  # 违禁词列表
    sensitivity_threshold: float = 0.8  # 敏感词检测阈值

    # 成本控制
    max_tokens_per_iteration: int = 8000  # 每次迭代最大 token 数
    cheap_model_for_revisions: bool = True  # 修改时切换到更便宜的模型

    # Prompt 模板
    prompt_template_dir: str = ""  # Prompt 模板目录
    default_language: str = "zh-CN"  # 默认语言

    # 存储
    storage_dir: str = ""  # 存储目录
    session_ttl: int = 86400 * 7  # 会话 TTL（秒），默认 7 天

    # 发布配置
    publish_enabled: bool = False  # 是否启用发布功能
    xiaohongshu_api_enabled: bool = False  # 小红书 API 发布

    # 评分配置
    quality_score_threshold: float = 0.7  # 质量分数阈值

    def __post_init__(self):
        """初始化默认值"""
        if not self.prompt_template_dir:
            self.prompt_template_dir = str(
                Path(__file__).parent.parent / "prompts"
            )
        if not self.storage_dir:
            self.storage_dir = str(
                Path(__file__).parent.parent.parent / "data" / "studio"
            )

        # 确保目录存在
        Path(self.storage_dir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudioConfig":
        """从字典创建"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "max_iterations": self.max_iterations,
            "iteration_timeout": self.iteration_timeout,
            "prohibited_words": self.prohibited_words,
            "sensitivity_threshold": self.sensitivity_threshold,
            "max_tokens_per_iteration": self.max_tokens_per_iteration,
            "cheap_model_for_revisions": self.cheap_model_for_revisions,
            "prompt_template_dir": self.prompt_template_dir,
            "default_language": self.default_language,
            "storage_dir": self.storage_dir,
            "session_ttl": self.session_ttl,
            "publish_enabled": self.publish_enabled,
            "xiaohongshu_api_enabled": self.xiaohongshu_api_enabled,
            "quality_score_threshold": self.quality_score_threshold,
        }


# 全局配置实例
_studio_config: Optional[StudioConfig] = None


def get_studio_config() -> StudioConfig:
    """获取全局配置实例"""
    global _studio_config
    if _studio_config is None:
        _studio_config = StudioConfig()
    return _studio_config


def set_studio_config(config: StudioConfig) -> None:
    """设置全局配置实例"""
    global _studio_config
    _studio_config = config
