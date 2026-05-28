"""
MemoryConfig - 记忆模块配置

管理记忆模块的配置参数
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MemoryConfig:
    """记忆模块配置"""

    # Chroma 配置
    chroma_persist_dir: str = "data/memory/chroma"
    chroma_distance_metric: str = "cosine"  # cosine, l2, ip

    # 向量维度配置
    embedding_dimensions: int = 1536  # OpenAI ada-002 默认维度

    # 记忆保留策略
    short_term_retention_days: int = 7  # 短期记忆保留天数
    long_term_retention_days: int = 365  # 长期记忆保留天数

    # 搜索配置
    default_search_limit: int = 5
    max_search_limit: int = 50

    # 迁移配置
    auto_migrate_on_session_end: bool = True
    min_importance_for_migration: float = 0.7

    # 多模态配置
    multimodal_enabled: bool = True
    max_multimodal_size_mb: int = 50

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        """从环境变量加载配置"""
        return cls(
            chroma_persist_dir=os.getenv("MEMORY_CHROMA_DIR", "data/memory/chroma"),
            chroma_distance_metric=os.getenv("MEMORY_DISTANCE_METRIC", "cosine"),
            embedding_dimensions=int(os.getenv("MEMORY_EMBEDDING_DIM", "1536")),
            short_term_retention_days=int(os.getenv("MEMORY_SHORT_TERM_DAYS", "7")),
            long_term_retention_days=int(os.getenv("MEMORY_LONG_TERM_DAYS", "365")),
            default_search_limit=int(os.getenv("MEMORY_SEARCH_LIMIT", "5")),
            max_search_limit=int(os.getenv("MEMORY_MAX_SEARCH", "50")),
            auto_migrate_on_session_end=os.getenv("MEMORY_AUTO_MIGRATE", "true").lower() == "true",
            min_importance_for_migration=float(os.getenv("MEMORY_MIN_IMPORTANCE", "0.7")),
            multimodal_enabled=os.getenv("MEMORY_MULTIMODAL", "true").lower() == "true",
            max_multimodal_size_mb=int(os.getenv("MEMORY_MAX_MULTIMODAL_MB", "50")),
        )


# 全局配置实例
_config: Optional[MemoryConfig] = None


def get_memory_config() -> MemoryConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = MemoryConfig.from_env()
    return _config


def update_memory_config(**kwargs) -> None:
    """更新全局配置"""
    global _config
    if _config is None:
        _config = MemoryConfig.from_env()

    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
