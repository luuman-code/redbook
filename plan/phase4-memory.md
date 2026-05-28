# Phase 4 实现计划：记忆模块 (Memory)

## Context

Phase 1-3 已完成：
- Phase 1: 配置管理 UI 服务器
- Phase 2: 模型网关（LLM/Vision/Image/TTS/Video）
- Phase 3: 小红书内容生成 Agent（Orchestrator + 前端）

Phase 4 需要实现**记忆模块**，支持：
- 短期记忆：当前会话的 Brief、生成历史、用户反馈
- 长期记忆：用户风格偏好、品牌资产、成功文案模型
- 多模态索引：图片/音视频内容的向量存储与检索

**关键技术选型**（参考 plan.md）：
- 向量数据库：**Chroma**（轻量、Python 原生、Embedded 模式）
- 结构化存储：**SQLite**（轻量、可升级为 PostgreSQL）
- 多模态嵌入：使用 Vision 模型生成图片向量

---

## 目录结构

```
C:\Users\LWB\Desktop\redbook\
├── memory\                           # Phase 4: 记忆模块（新建）
│   ├── __init__.py
│   ├── config\
│   │   ├── __init__.py
│   │   └── memory_config.py        # 记忆模块配置
│   │
│   ├── core\                        # 核心记忆管理
│   │   ├── __init__.py
│   │   ├── memory_manager.py      # 记忆管理器（统一入口）
│   │   ├── short_term.py          # 短期记忆（会话级）
│   │   └── long_term.py           # 长期记忆（用户级）
│   │
│   ├── vector\                      # 向量存储（Chroma）
│   │   ├── __init__.py
│   │   ├── chroma_client.py      # Chroma 客户端封装
│   │   └── embeddings.py          # 向量化工具
│   │
│   ├── storage\                     # 结构化存储
│   │   ├── __init__.py
│   │   └── sqlite_store.py        # SQLite 存储
│   │
│   └── models\                      # 记忆数据模型
│       ├── __init__.py
│       ├── memory_item.py         # 记忆条目
│       ├── memory_type.py         # 记忆类型枚举
│       └── search_result.py        # 搜索结果
│
├── data\                            # 数据存储目录
│   ├── studio\                      # 会话数据（已有）
│   └── memory\                      # 记忆数据（新建）
│       ├── chroma\                  # Chroma 向量数据库
│       └── memory.db               # SQLite 数据库
```

---

## 实现步骤

### 步骤 4.1: 创建记忆模块基础结构

**文件：** `memory/__init__.py`
```python
"""
Memory Module - 多模态记忆系统

支持：
- 短期记忆：当前会话的 Brief、生成历史、用户反馈
- 长期记忆：用户风格偏好、品牌资产、成功文案模型
"""

from .core.memory_manager import MemoryManager
from .models.memory_item import MemoryItem
from .models.memory_type import MemoryType

__all__ = [
    "MemoryManager",
    "MemoryItem",
    "MemoryType",
]
```

**文件：** `memory/models/memory_type.py`
```python
from enum import Enum

class MemoryType(str, Enum):
    """记忆类型"""
    # 短期记忆（会话级）
    SESSION_BRIEF = "session_brief"           # Brief 内容
    SESSION_PLAN = "session_plan"            # 内容方案
    SESSION_GENERATED = "session_generated"  # 生成的历史内容
    SESSION_FEEDBACK = "session_feedback"    # 用户反馈

    # 长期记忆（用户级）
    USER_STYLE = "user_style"                # 用户风格偏好
    USER_BRAND = "user_brand"                # 品牌资产
    USER_TEMPLATE = "user_template"           # 成功文案模板
    USER_PREFERENCE = "user_preference"     # 其他偏好
```

**文件：** `memory/models/memory_item.py`
```python
@dataclass
class MemoryItem:
    """记忆条目"""
    id: str
    memory_type: MemoryType
    content: str                    # 文本内容
    vector: Optional[List[float]]   # 向量嵌入（如果有）
    metadata: Dict[str, Any]        # 元数据（来源会话ID、时间戳等）
    created_at: datetime
    updated_at: datetime

    # 多模态资源
    multimodal_resources: List[MultimodalResource] = field(default_factory=list)

    # 检索相关
    importance: float = 1.0        # 重要性评分
    access_count: int = 0         # 访问次数
    last_accessed: Optional[datetime] = None
```

### 步骤 4.2: 实现 Chroma 向量存储

**文件：** `memory/vector/chroma_client.py`

```python
import chromadb
from chromadb.config import Settings

class ChromaMemoryClient:
    """Chroma 向量数据库客户端"""

    def __init__(self, persist_dir: str = "data/memory/chroma"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        #  collections
        self.short_term = self.client.get_or_create_collection(
            "short_term_memory",
            metadata={"description": "短期记忆"}
        )
        self.long_term = self.client.get_or_create_collection(
            "long_term_memory",
            metadata={"description": "长期记忆"}
        )
        self.multimodal = self.client.get_or_create_collection(
            "multimodal_memory",
            metadata={"description": "多模态记忆（图片/音视频）"}
        )

    def add(self, collection: str, item: MemoryItem):
        """添加记忆"""
        ...

    def search(self, collection: str, query_vector: List[float], n: int = 5) -> List[MemoryItem]:
        """向量相似性搜索"""
        ...

    def delete(self, collection: str, item_id: str):
        """删除记忆"""
        ...
```

### 步骤 4.3: 实现短期记忆

**文件：** `memory/core/short_term.py`

```python
class ShortTermMemory:
    """短期记忆 - 会话级"""

    def __init__(self, session_id: str, chroma_client: ChromaMemoryClient):
        self.session_id = session_id
        self.chroma = chroma_client
        self.redis_client = redis_client  # 可选：使用 Redis 缓存

    async def save_brief(self, brief: Brief):
        """保存 Brief 到记忆"""
        item = MemoryItem(
            id=f"{self.session_id}_brief",
            memory_type=MemoryType.SESSION_BRIEF,
            content=brief.to_text(),  # 转为文本
            metadata={"session_id": self.session_id}
        )
        await self.chroma.add("short_term", item)

    async def save_generated_content(self, items: List[ContentItem]):
        """保存生成的内容"""
        for item in items:
            item = MemoryItem(
                id=f"{self.session_id}_gen_{item.item_id}",
                memory_type=MemoryType.SESSION_GENERATED,
                content=item.content,
                metadata={"item_type": item.item_type, "session_id": self.session_id}
            )
            await self.chroma.add("short_term", item)

    async def save_feedback(self, feedback: str):
        """保存用户反馈"""
        item = MemoryItem(
            id=f"{self.session_id}_fb_{uuid.uuid4()}",
            memory_type=MemoryType.SESSION_FEEDBACK,
            content=feedback,
            metadata={"session_id": self.session_id}
        )
        await self.chroma.add("short_term", item)

    async def get_session_context(self) -> str:
        """获取当前会话的所有记忆上下文（用于 LLM 提示）"""
        results = await self.chroma.search("short_term", session_id=self.session_id)
        return "\n".join([r.content for r in results])

    async def clear_session(self):
        """清除会话记忆（会话结束后调用）"""
        # 将重要记忆迁移到长期记忆
        await self.migrate_to_long_term()
        # 删除短期记忆
        await self.chroma.delete_by_session(self.session_id)
```

### 步骤 4.4: 实现长期记忆

**文件：** `memory/core/long_term.py`

```python
class LongTermMemory:
    """长期记忆 - 用户级"""

    def __init__(self, user_id: str, chroma_client: ChromaMemoryClient):
        self.user_id = user_id
        self.chroma = chroma_client

    async def save_style_preference(self, style: str, description: str = ""):
        """保存用户风格偏好"""
        item = MemoryItem(
            id=f"{self.user_id}_style_{uuid.uuid4()}",
            memory_type=MemoryType.USER_STYLE,
            content=f"风格: {style}\n描述: {description}",
            importance=0.8
        )
        await self.chroma.add("long_term", item)

    async def save_brand_asset(self, brand_name: str, asset_type: str, content: str):
        """保存品牌资产（Logo、配色等）"""
        item = MemoryItem(
            id=f"{self.user_id}_brand_{uuid.uuid4()}",
            memory_type=MemoryType.USER_BRAND,
            content=content,
            metadata={"brand_name": brand_name, "asset_type": asset_type}
        )
        await self.chroma.add("long_term", item)

    async def save_successful_template(self, template: str, context: str):
        """保存成功的文案模板"""
        item = MemoryItem(
            id=f"{self.user_id}_template_{uuid.uuid4()}",
            memory_type=MemoryType.USER_TEMPLATE,
            content=template,
            metadata={"context": context},
            importance=0.9
        )
        await self.chroma.add("long_term", item)

    async def search_similar(self, query: str, n: int = 5) -> List[MemoryItem]:
        """搜索相似记忆"""
        # 生成查询向量
        query_vector = await generate_embedding(query)
        return await self.chroma.search("long_term", query_vector, n=n)

    async def get_style_preferences(self) -> List[str]:
        """获取用户的所有风格偏好"""
        results = await self.chroma.get_by_type("long_term", MemoryType.USER_STYLE)
        return [r.content for r in results]
```

### 步骤 4.5: 实现记忆管理器（统一入口）

**文件：** `memory/core/memory_manager.py`

```python
class MemoryManager:
    """记忆管理器 - 统一入口"""

    def __init__(
        self,
        user_id: str = "default",
        session_id: str = None,
        chroma_persist_dir: str = "data/memory/chroma",
        sqlite_path: str = "data/memory/memory.db"
    ):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())

        # 初始化存储
        self.chroma = ChromaMemoryClient(chroma_persist_dir)
        self.sqlite = SQLiteStore(sqlite_path)

        # 初始化记忆
        self.short_term = ShortTermMemory(self.session_id, self.chroma)
        self.long_term = LongTermMemory(self.user_id, self.chroma)

    async def initialize_session(self, brief: Brief):
        """初始化新会话记忆"""
        await self.short_term.save_brief(brief)

    async def add_generated_content(self, items: List[ContentItem]):
        """添加生成的内容到记忆"""
        await self.short_term.save_generated_content(items)

    async def add_feedback(self, feedback: str):
        """添加用户反馈到记忆"""
        await self.short_term.save_feedback(feedback)

    async def get_context_for_llm(self) -> str:
        """获取 LLM 上下文（短期 + 相关长期）"""
        # 获取当前会话记忆
        session_context = await self.short_term.get_session_context()

        # 获取相关的长期记忆
        recent_items = await self.short_term.get_recent_items(limit=3)
        query = " ".join([item.content for item in recent_items])
        long_term_context = await self.long_term.search_similar(query, n=3)

        return f"""## 当前会话背景
{session_context}

## 相关历史记忆
{long_term_context}"""

    async def conclude_session(self, final_version: int):
        """结束会话 - 将重要记忆迁移到长期"""
        await self.short_term.migrate_to_long_term(final_version)
        await self.short_term.clear_session()

    async def search_memories(self, query: str, memory_type: MemoryType = None) -> List[SearchResult]:
        """跨记忆搜索"""
        query_vector = await generate_embedding(query)
        return await self.chroma.hybrid_search(query, query_vector, filter_type=memory_type)
```

### 步骤 4.6: 集成到 Orchestrator

**修改文件：** `studio/core/orchestrator.py`

```python
from memory import MemoryManager

class Orchestrator:
    def __init__(self, ...):
        # 现有初始化...
        self.memory = MemoryManager(
            user_id="default",  # 可从用户上下文获取
            session_id=self.session_id
        )

    async def create_session(self, ...):
        # 初始化记忆
        await self.memory.initialize_session(brief)
        # 后续生成内容时自动添加到记忆

    async def iterate(self, session, feedback):
        # 获取记忆上下文
        context = await self.memory.get_context_for_llm()

        # 使用上下文调用 LLM
        ...
```

### 步骤 4.7: 添加依赖

**文件：** `requirements.txt` 添加
```
chromadb>=0.4.0
numpy>=1.24.0
```

---

## 验证方式

1. **基础验证**：
```python
from memory import MemoryManager

manager = MemoryManager()

# 初始化会话
await manager.initialize_session(brief)

# 添加生成内容
await manager.add_generated_content(items)

# 获取上下文
context = await manager.get_context_for_llm()
print(context)
```

2. **向量搜索验证**：
```python
# 搜索相似记忆
results = await manager.search_memories("防晒霜 清新风格")
for result in results:
    print(f"类型: {result.item.memory_type}")
    print(f"内容: {result.item.content}")
    print(f"相似度: {result.score}")
```

3. **端到端验证**：
```bash
# 1. 创建会话（上传图片 + 文本）
# 2. 生成内容
# 3. 用户反馈："标题不够吸引人"
# 4. 再次生成时，系统应能参考之前的风格

# 查看记忆数据库
ls data/memory/chroma/
ls data/memory/memory.db
```

---

## Chroma 简介

Chroma 是一个开源的向量数据库，专为 LLM 应用设计：

**特点**：
- 轻量级，可嵌入式运行（不需要单独服务器）
- Python 原生，易于集成
- 支持元数据过滤
- 支持多模态（图片、音频可通过嵌入模型转为向量）

**安装**：
```bash
pip install chromadb
```

**使用**：
```python
import chromadb
client = chromadb.PersistentClient(path="./chroma_data")
collection = client.get_or_create_collection("my_collection")
collection.add(
    documents=["文本1", "文本2"],
    ids=["id1", "id2"],
    metadatas=[{"source": "doc1"}, {"source": "doc2"}]
)
results = collection.query(
    query_texts=["搜索文本"],
    n_results=2
)
```

---

## 更新计划文件

完成后需要更新：
1. `README.md` - 添加 Phase 4 状态和说明
2. `plan/plan.md` - 标记记忆模块已完成
