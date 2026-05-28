# AI 小红书文案生成工作流 - 实现总结

> 最后更新：2026-04-28 (Phase 5 补充)

---

## 一、项目概述

### 1.1 项目目标

开发一条 AI 小红书文案生成工作流（更像是一个 Agent），能够：

1. 接收用户需求及素材（图片、文本等）
2. 分发给各类模型进行处理
3. 汇总分析后给出具体方案（文案内容 + 配图风格）
4. 将方案分发给对应模型（文本/图片/视频/语音）
5. 汇总内容构建完整文案
6. 迭代修改直到用户满意
7. 支持发布或导出

### 1.2 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                               │
│    Web 前端 (Studio UI)          │    配置管理 UI (Config UI)    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Agent 调度核心                               │
│  - Orchestrator (总控Agent)                                    │
│  - Planner (方案规划Agent)                                     │
│  - Critic (审核反馈Agent)                                      │
│  - Iterator (迭代修改Agent)                                    │
│  - Memory (会话/知识记忆)                                      │
└──┬───────┬───────┬───────┬───────┬─────────┬───────────────────┘
   │       │       │       │       │         │
┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──────────────┐
│文本 ││图像 ││视频 ││语音 ││数据  ││需求解析         │
│生成 ││生成 ││生成 ││生成 ││分析  ││Agent            │
└─────┘└─────┘└─────┘└─────┘└─────┘└─────────────────┘
```

---

## 二、目录结构

```
C:\Users\LWB\Desktop\redbook\
├── studio/                          # 核心 Agent 模块
│   ├── core/                        # 核心 Agent
│   │   ├── orchestrator.py         # 总调度 Agent
│   │   ├── brief_parser.py         # 需求解析 Agent
│   │   ├── planner.py              # 方案规划 Agent
│   │   ├── critic.py               # 审核反馈 Agent
│   │   ├── iterator.py             # 迭代修改 Agent
│   │   └── publisher.py            # 发布 Agent
│   ├── models/                     # 数据模型
│   │   ├── brief.py                # Brief 模型
│   │   ├── content_plan.py         # 内容方案模型
│   │   ├── content_item.py         # 内容项模型
│   │   ├── session.py              # 会话模型
│   │   └── version.py              # 版本模型
│   ├── api/                        # API 路由
│   │   ├── routes.py              # Studio API 端点
│   │   └── schemas.py             # Pydantic 模型
│   ├── storage/                    # 存储
│   │   ├── session_store.py        # 会话存储
│   │   ├── version_store.py       # 版本存储
│   │   └── content_store.py       # 内容文件存储（Phase 6 新增）
│   ├── skills/                     # 技能模块
│   │   ├── base_skill.py
│   │   ├── text_skill.py
│   │   ├── image_skill.py
│   │   ├── video_skill.py
│   │   ├── audio_skill.py
│   │   └── analytic_skill.py
│   └── config/
│       └── studio_config.py       # Studio 配置
│
├── memory/                          # Phase 4: 记忆模块
│   ├── core/
│   │   ├── memory_manager.py      # 记忆管理器
│   │   ├── short_term.py          # 短期记忆
│   │   └── long_term.py           # 长期记忆
│   ├── vector/
│   │   ├── chroma_client.py       # Chroma 客户端
│   │   └── embeddings.py          # 向量化工具
│   ├── storage/
│   │   └── sqlite_store.py        # SQLite 存储
│   └── models/
│       ├── memory_item.py
│       ├── memory_type.py
│       └── search_result.py
│
├── config-ui/                      # 配置管理 UI
│   ├── backend/                    # FastAPI 后端
│   │   ├── main.py               # 入口
│   │   ├── config_service.py      # 配置服务
│   │   └── api/
│   │       └── config.py         # 配置 API
│   └── frontend/                  # React 前端
│       └── src/
│           ├── components/
│           │   ├── config/        # 配置组件
│           │   └── studio/        # Studio 组件
│           │       ├── StudioPage.tsx
│           │       ├── PlanDialog.tsx
│           │       ├── ContentPreview.tsx
│           │       ├── FeedbackPanel.tsx
│           │       ├── VersionHistory.tsx
│           │       └── SessionList.tsx
│           └── api/
│               ├── configApi.ts
│               └── studioApi.ts
│
├── agent/                           # 模型网关
│   └── ...
│
├── data/studio/sessions/            # 会话数据目录（Phase 6 新增）
│   └── {session_id}/
│       ├── metadata.json           # 会话元数据
│       ├── brief.json             # Brief 内容
│       ├── plan.json              # 方案内容
│       ├── versions/
│       │   ├── v1/
│       │   │   ├── items.json    # 版本内容快照
│       │   │   └── images/       # 图片文件
│       │   └── v2/
│       └── current/
│           ├── images/            # 当前版本图片
│           ├── videos/            # 视频文件
│           └── audio/             # 音频文件
│
└── plan/                           # 计划文档
    ├── plan.md                     # 原始需求
    ├── idea.md                     # 设计方案
    ├── phase4-memory.md           # Phase 4 计划
    └── IMPLEMENTATION.md           # 本文档
```

---

## 三、已实现功能

### 3.1 Phase 1: 配置管理 UI

| 功能 | 状态 | 文件 |
|------|------|------|
| 模型配置管理 | ✅ | config-ui/backend/api/config.py |
| 多环境支持 | ✅ | ConfigService |
| 配置导入/导出 | ✅ | ConfigService._export_config / _import_config |
| 连接测试 | ✅ | POST /api/config/models/:type/test |
| UI 界面 | ✅ | config-ui/frontend/src/components/config/ |

**技术栈**：
- 后端：FastAPI
- 前端：React 19 + Tailwind CSS 4

### 3.2 Phase 2: 模型网关

| 模型类型 | 功能 | 状态 |
|---------|------|------|
| LLM | 文本生成/调度 | ✅ |
| Vision | 图像理解 | ✅ |
| Image Generation | 图像生成 | ✅ |
| TTS | 语音合成 | ✅ |
| Video | 视频生成 | ✅ |

**网关架构**：
- GatewayFactory 统一创建
- 支持 fallback 策略
- 配置中心驱动

### 3.3 Phase 3: 小红书内容生成 Agent

| Agent | 功能 | 状态 |
|-------|------|------|
| BriefParser | 需求解析 | ✅ |
| Planner | 方案规划 | ✅ |
| Critic | 审核反馈 | ✅ |
| Iterator | 迭代修改 | ✅ |
| Publisher | 发布/导出 | ✅ |
| Orchestrator | 总调度 | ✅ |

**核心流程**：
1. 用户输入 → BriefParser 解析需求
2. Planner 生成内容方案
3. **PlanDialog 确认方案**（Phase 5）
4. **并行生成** 文案和配图（Phase 5）
5. **图文冲突检测**（Phase 5）
6. Critic 审核
7. 用户反馈 → Iterator 迭代
8. Publisher 发布/导出

### 3.4 Phase 4: 记忆模块

| 功能 | 状态 | 文件 |
|------|------|------|
| 短期记忆 | ✅ | memory/core/short_term.py |
| 长期记忆 | ✅ | memory/core/long_term.py |
| 向量存储 | ✅ | memory/vector/chroma_client.py |
| 结构化存储 | ✅ | memory/storage/sqlite_store.py |
| 记忆管理器 | ✅ | memory/core/memory_manager.py |
| 集成到 Orchestrator | ✅ | orchestrator.py 使用 MemoryManager |

**技术选型**：
- 向量数据库：Chroma（嵌入式）
- 结构化存储：SQLite

### 3.5 Phase 5: 核心功能补全

| 功能 | 状态 | 文件 |
|------|------|------|
| 图文匹配检查 | ✅ | critic.py::check_image_text_alignment() |
| 并行生成（多图） | ✅ | orchestrator.py::asyncio.gather |
| 方案确认流程 | ✅ | PlanDialog.tsx + CONFIRMED 状态 |
| confirm-plan API | ✅ | routes.py::/sessions/{id}/confirm-plan |
| **按需生成机制** | ✅ | Brief.need_text / Brief.need_images |
| **无素材后备机制** | ✅ | planner.py::_generate_image_plan/_generate_video_plan |

**按需生成逻辑**：
```python
# 1. 按需生成文案和配图
text_items = []
image_items = []

tasks = []
if session.brief.need_text:
    tasks.append(self._generate_text(session))
if session.brief.need_images:
    tasks.append(self._generate_images(session))

if tasks:
    results = await asyncio.gather(*tasks)
    for i, result in enumerate(results):
        if session.brief.need_text and i < len(results):
            text_items = results[i]
        if session.brief.need_images and i < len(results):
            image_items = results[i]

# 2. 图文冲突检测（仅当两者都生成时）
if text_items and image_items:
    alignment_issues = await self.critic.check_image_text_alignment(brief, text_items + image_items)
```

**无素材后备机制**：
```python
# _generate_image_plan / _generate_video_plan 中，prompt 包含用户原始需求
prompt = f"""根据以下 Brief 生成配图方案。

用户需求描述：
{user_description}

Brief:
- 产品/内容风格: {brief.image_style}
- 必须包含的元素: {', '.join(brief.must_include) if brief.must_include else '无特定要求'}

请根据"用户需求描述"推断应该生成什么样的配图，并生成 JSON...
"""
```

**按需生成场景**：
| 场景 | need_text | need_images | 行为 |
|------|-----------|-------------|------|
| 只文案 | true | false | 只生成文案，跳过配图 |
| 只配图 | false | true | 只生成配图，跳过文案 |
| 都要 | true | true | 文案和配图都生成（默认） |

### 3.6 Phase 6: 内容持久化与版本回滚

| 功能 | 状态 | 文件 |
|------|------|------|
| 内容本地持久化 | ✅ | storage/content_store.py |
| 版本快照文件存储 | ✅ | storage/content_store.py |
| 恢复历史版本 | ✅ | routes.py::restore_version |
| 预览历史版本内容 | ✅ | VersionHistory.tsx 预览弹窗 |
| 用户上传替换内容 | ✅ | routes.py::upload_item_content + ContentPreview.tsx |
| 前端本地路径展示 | ✅ | ContentPreview.tsx::getMediaSrc() |

**ContentStore 核心方法**：
```python
class ContentStore:
    def get_session_dir(self, session_id: str, version: int = None) -> Path:
        """获取会话目录（version 为 None 时返回 current 目录）"""

    async def save_content(self, session_id, item_id, content, content_type, version=None):
        """保存内容到本地文件（支持 URL 下载和 base64）"""

    def save_items_snapshot(self, session_id, items_data, version):
        """保存版本快照到文件"""

    def save_plan_snapshot(self, session_id, plan_data, version):
        """保存方案快照到文件"""
```

**数据持久化流程**：
```
生成阶段:
  Orchestrator.generate() → ContentStore.save_content() → 本地文件
                                          ↓
                        data/studio/sessions/{session_id}/current/images/{item_id}.png

版本快照:
  Version.create_snapshot() → items_snapshot 包含 local_path
                            → data/studio/sessions/{session_id}/versions/v{n}/items.json

回滚阶段:
  用户点击"加载 V1 版本"
    → GET /sessions/{id}/versions/{version}/content (预览)
    → POST /sessions/{id}/restore/{version} (恢复)
```

---

## 四、数据结构

### 4.1 Brief（需求结构）

```python
@dataclass
class Brief:
    id: str
    goal: str                           # 目标：种草/教程/测评
    style: str                         # 风格：活泼/专业/治愈
    keywords: List[str]                # 关键词
    must_include: List[str]             # 必须包含的卖点
    image_style: str                   # 配图风格
    need_video: bool                   # 是否需要视频
    need_voiceover: bool               # 是否需要配音
    need_text: bool                    # 是否需要文案（默认 True）
    need_images: bool                  # 是否需要配图（默认 True）
    raw_input: str                     # 原始输入
    extracted_product_info: Dict        # 提取的产品信息
```

### 4.2 ContentPlan（内容方案）

```python
@dataclass
class ContentPlan:
    plan_id: str
    brief_id: str
    title: str
    text_sections: List[TextSection]   # 文案结构
    image_plan: ImagePlan              # 配图计划
    video_plan: VideoPlan              # 视频计划
    audio_plan: AudioPlan              # 音频计划
```

### 4.3 ContentItem（内容项）

```python
@dataclass
class ContentItem:
    item_id: str
    item_type: ContentType            # title/headline/text/hashtag/cta/image/video/audio
    content: str                       # 内容
    status: ItemStatus                 # pending/generating/completed/failed
    position: int                      # 位置
    metadata: Dict                     # 元数据
    generation_prompt: str             # 生成时的 prompt
    error_message: str                # 错误信息
    local_path: Optional[str] = None   # 本地文件路径（Phase 6 新增）
```

### 4.4 Session（会话）

```python
@dataclass
class Session:
    session_id: str
    brief: Brief
    current_plan: ContentPlan
    current_version: int = 1
    items: List[ContentItem]          # 生成的内容
    status: SessionStatus              # created/planning/confirmed/generating/reviewing/iterating/completed/published/cancelled
    created_at: datetime
    updated_at: datetime
    versions: List[Version]           # 版本历史
    metadata: Dict                    # 元数据（如 alignment_issues）
```

### 4.5 Version（版本）

```python
@dataclass
class Version:
    version_number: int
    created_at: datetime
    created_by: str
    change_summary: str
    plan_snapshot: Dict
    items_snapshot: List[Dict]
```

---

## 五、API 端点

### 5.1 配置管理 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/config | 获取所有配置 |
| GET | /api/config/models | 获取模型配置 |
| PUT | /api/config/models/:type | 更新模型配置 |
| POST | /api/config/models/:type/test | 测试连接 |
| POST | /api/config/import | 导入配置 |
| POST | /api/config/export | 导出配置 |

### 5.2 Studio API

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/studio/sessions | 创建会话 |
| GET | /api/studio/sessions/:id | 获取会话 |
| POST | /api/studio/sessions/:id/confirm-plan | **确认方案** |
| POST | /api/studio/sessions/:id/generate | 生成内容 |
| POST | /api/studio/sessions/:id/review | 审核内容 |
| POST | /api/studio/sessions/:id/feedback | 提交反馈 |
| POST | /api/studio/sessions/:id/publish | 发布内容 |
| GET | /api/studio/sessions/:id/export | 导出素材包 |
| GET | /api/studio/sessions/:id/versions | 版本历史 |
| POST | /api/studio/sessions/:id/rollback/:version | 回退版本 |
| GET | /api/studio/sessions/:id/versions/:version/content | **获取版本内容**（Phase 6） |
| POST | /api/studio/sessions/:id/restore/:version | **从历史版本恢复**（Phase 6） |
| POST | /api/studio/sessions/:id/items/:item_id/upload | **上传替换内容**（Phase 6） |
| DELETE | /api/studio/sessions/:id | 删除会话 |

---

## 六、用户交互流程

### 6.1 完整工作流

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互流程                               │
└─────────────────────────────────────────────────────────────────┘

1. 创建会话
   ├── 用户输入需求（文本描述）
   ├── 上传素材（图片/视频/音频）[可选]
   └── 系统解析需求，生成 Brief + ContentPlan

2. 方案确认 [Phase 5 新增]
   ├── 显示 PlanDialog 弹窗
   ├── 展示 Brief 概要、方案详情
   ├── 用户点击「确认方案」
   └── 状态变为 CONFIRMED，自动开始生成

3. 内容生成 [Phase 5 优化]
   ├── 按需生成（need_text/need_images 控制）
   ├── 并行生成文案和配图（如都需要）
   ├── 多张图片同时生成
   ├── 图文冲突检测（仅当两者都生成时）
   ├── 无素材时：LLM 从文本推断生成指示
   └── 状态变为 REVIEWING

4. 审核反馈
   ├── Critic 审核（敏感词/质量评分）
   ├── 用户查看生成结果
   └── 用户可选择：
       ├── 满意 → 发布
       └── 不满意 → 反馈修改

5. 迭代修改
   ├── 用户提交反馈（如"标题不够吸引人"）
   ├── Iterator 解析意图，只修改指定部分
   ├── 生成新版本
   └── 重复审核直到满意

6. 内容持久化 [Phase 6 新增]
   ├── 生成的图片/视频/音频自动保存到本地
   ├── data/studio/sessions/{session_id}/current/ 目录
   ├── 每次版本变更保存快照到 versions/v{n}/ 目录

7. 版本回滚 [Phase 6 新增]
   ├── 打开版本历史面板
   ├── 点击任意版本的"预览"查看历史内容
   ├── 点击"加载此版本"恢复历史内容到当前
   └── 可继续迭代修改

8. 用户上传替换 [Phase 6 新增]
   ├── 在图片/视频上悬停显示"替换"按钮
   ├── 选择本地文件上传
   ├── 自动更新 item.content 和 local_path
   └── 刷新页面后仍能显示（从本地加载）

9. 发布/导出
   ├── 模拟发布（检查格式）
   ├── 导出素材包（ZIP）
   └── 状态变为 PUBLISHED
```

### 6.2 状态机

```
CREATED → PLANNING → CONFIRMED → GENERATING → REVIEWING
                                              ↓
                    ITERATING ← ← ← ← ← ← ← ← ←
                         ↓
                      COMPLETED → PUBLISHED
                         ↓
                     CANCELLED
```

### 6.3 内容持久化与版本回滚流程 [Phase 6]

```
┌─────────────────────────────────────────────────────────────────┐
│                      内容存储与回滚流程                            │
└─────────────────────────────────────────────────────────────────┘

1. 生成阶段
   Orchestrator.generate()
       │
       ├── 生成 ContentItem
       │
       ├── ContentStore.save_content() → 本地文件
       │       │
       │       └── data/studio/sessions/{session_id}/current/images/{item_id}.png
       │
       └── Session.items 更新 metadata.local_path

2. 版本快照
   Version.create_snapshot()
       │
       └── items_snapshot 包含 ContentItem 字典
               └── 含 local_path 字段

3. SessionStore.save()
       │
       └── data/studio/sessions/{session_id}/metadata.json
       └── data/studio/sessions/{session_id}/versions/v{n}/items.json

4. 回滚阶段
   用户点击"加载 V1 版本"
       │
       ├── GET /sessions/{id}/versions/{version}/content
       │       └── 返回 items_snapshot
       │
       └── POST /sessions/{id}/restore/{version}
               └── 恢复 items 到 session.items
               └── 状态变为 ITERATING
               └── 用户可继续迭代

5. 用户上传替换
   用户点击"替换"按钮选择本地文件
       │
       ├── POST /sessions/{id}/items/{item_id}/upload
       │       └── 文件保存到本地
       │       └── 更新 item.content (base64)
       │       └── 更新 item.metadata.local_path
       │
       └── 刷新 session，前端展示新内容

6. 前端展示
   ContentPreview
       │
       ├── 优先使用 item.metadata.local_path
       └── file://{local_path}
```

---

## 七、技术亮点

### 7.1 按需生成机制

通过 `Brief.need_text` 和 `Brief.need_images` 字段控制内容生成：
- **只文案**：`need_text=true, need_images=false` → 只生成文案
- **只配图**：`need_text=false, need_images=true` → 只生成配图
- **都要**：`need_text=true, need_images=true` → 文案和配图都生成

使用 `asyncio.gather` 实现按需并行生成，显著提升效率。

### 7.2 无素材后备机制

当用户没有上传素材时，多模态 LLM 从用户文本中推断生成指示：
- `_generate_image_plan`：从用户需求描述推断配图风格、元素、颜色
- `_generate_video_plan`：从用户需求描述推断视频场景、视觉提示词
- `_generate_audio_plan`：从 `must_include` 和 `goal` 生成配音文本

```
用户输入: "我想推荐一款面膜，要保湿效果好"
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  多模态 LLM 分析用户文本                                     │
│  → 推断配图风格、元素、颜色                                 │
│  → 推断视频场景、视觉提示词                                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  ImagePlan / VideoPlan / AudioPlan                          │
│  → 包含 LLM 推断的生成指示                                  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Image Gateway / Video Gateway / TTS Gateway               │
│  → 根据推断的指示生成实际内容                               │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 图文冲突检测

LLM 驱动的图文一致性检查：
- 分析文案描述与图片是否匹配
- 检测产品特征（颜色、形状、数量）
- 风格描述一致性
- 返回问题列表和建议

### 7.4 版本管理

- 每次修改创建版本快照
- 支持回滚到任意版本
- 保留完整历史记录

### 7.5 记忆模块

- 短期记忆：会话级 Brief、生成内容、用户反馈
- 长期记忆：用户风格偏好、品牌资产、成功模板
- 向量搜索：基于 Chroma 的语义检索

### 7.6 内容持久化与版本管理 [Phase 6]

- **本地文件存储**：图片/视频/音频自动保存到 data/studio/sessions/
- **版本快照**：每次修改创建独立版本快照（items.json + 媒体文件）
- **版本预览**：前端可直接预览历史版本内容
- **版本回滚**：一键恢复历史版本到当前会话
- **用户上传替换**：支持本地文件替换生成的内容

---

## 八、运行命令

### 8.1 启动后端

```bash
cd C:\Users\LWB\Desktop\redbook\config-ui\backend
python -m uvicorn main:app --reload --port 8080
```

### 8.2 启动前端（配置 UI）

```bash
cd C:\Users\LWB\Desktop\redbook\config-ui\frontend
npm run dev
```

### 8.3 访问地址

- 配置管理 UI：http://localhost:5173
- Studio UI：http://localhost:5173（导航到 Studio）
- API 文档：http://localhost:8080/docs

---

## 九、依赖项

```
# 后端
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0

# 记忆模块
chromadb>=0.4.0
numpy>=1.24.0

# 前端
react>=19.0.0
tailwindcss>=4.0.0
typescript>=5.0.0
```

---

## 十、后续优化建议

1. **真实 API 集成**：接入真实的小红书/抖音 API 实现自动发布
2. **产品一致性**：多图片生成时使用 IP-Adapter/InstantID 保持产品外观一致
3. **成本优化**：设置最大迭代轮次，切换便宜模型处理非核心任务
4. **多租户支持**：配置管理 UI 支持多用户/团队隔离
5. **实时预览**：WebSocket 实现生成过程实时推送

---

## 十一、文件清单

### 后端核心文件

| 文件 | 行数 | 功能 |
|------|------|------|
| studio/core/orchestrator.py | ~800 | 总调度 Agent |
| studio/core/brief_parser.py | ~200 | 需求解析 |
| studio/core/planner.py | ~250 | 方案规划 |
| studio/core/critic.py | ~350 | 审核反馈 + 图文检查 |
| studio/core/iterator.py | ~300 | 迭代修改 |
| studio/models/session.py | ~130 | 会话模型 |
| studio/storage/content_store.py | ~250 | 内容文件存储（Phase 6） |
| studio/api/routes.py | ~600 | API 端点（含 Phase 6 新API） |

### 前端核心文件

| 文件 | 功能 |
|------|------|
| StudioPage.tsx | Studio 主页面 |
| PlanDialog.tsx | 方案确认弹窗（Phase 5） |
| ContentPreview.tsx | 内容预览 + 本地上传替换（Phase 6） |
| FeedbackPanel.tsx | 反馈面板 |
| VersionHistory.tsx | 版本历史 + 预览/恢复（Phase 6） |
| studioApi.ts | Studio API 客户端（含 Phase 6 API） |

### 记忆模块文件

| 文件 | 功能 |
|------|------|
| memory/core/memory_manager.py | 记忆管理器 |
| memory/core/short_term.py | 短期记忆 |
| memory/core/long_term.py | 长期记忆 |
| memory/vector/chroma_client.py | Chroma 客户端 |

### 存储模块文件 [Phase 6]

| 文件 | 功能 |
|------|------|
| studio/storage/content_store.py | 内容文件存储（图片/视频/音频本地持久化） |
| studio/storage/session_store.py | 会话存储（启用文件持久化） |

---

**文档版本**：1.2 (Phase 5 补充：按需生成机制 + 无素材后备机制)
**维护者**：AI Development Team
**项目状态**：核心功能已完成，持续迭代中
