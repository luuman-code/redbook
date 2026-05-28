"""
Memory Module - 多模态记忆系统

支持：
- 短期记忆：当前会话的 Brief、生成历史、用户反馈
- 长期记忆：用户风格偏好、品牌资产、成功文案模型
- 多模态记忆：图片/音视频的向量存储与检索
"""

from .core.memory_manager import MemoryManager
from .core.short_term import ShortTermMemory
from .core.long_term import LongTermMemory
from .models.memory_item import MemoryItem, MultimodalResource
from .models.memory_type import MemoryType
from .models.search_result import SearchResult
from .vector.chroma_client import ChromaMemoryClient
from .vector.embeddings import EmbeddingsGenerator, generate_embedding

__all__ = [
    # Core
    "MemoryManager",
    "ShortTermMemory",
    "LongTermMemory",
    # Models
    "MemoryItem",
    "MultimodalResource",
    "MemoryType",
    "SearchResult",
    # Vector
    "ChromaMemoryClient",
    "EmbeddingsGenerator",
    "generate_embedding",
]
