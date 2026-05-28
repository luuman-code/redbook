"""
SearchResult - 搜索结果模型
"""

from dataclasses import dataclass
from typing import Optional

from .memory_item import MemoryItem


@dataclass
class SearchResult:
    """记忆搜索结果"""
    item: MemoryItem
    score: float  # 相似度分数 (0.0 - 1.0)
    rank: Optional[int] = None  # 排名

    def __repr__(self) -> str:
        return f"SearchResult(item={self.item.id}, score={self.score:.3f}, rank={self.rank})"
