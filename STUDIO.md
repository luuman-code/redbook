# Redbook Studio 创意工坊

小红书 AI 内容生成与创作工作平台

---

## 概述

**Redbook Studio** 是 Redbook 项目的核心模块，是一个智能化的**小红书内容创作工作台**。它通过 AI Agent 技术，帮助用户自动生成小红书文案、配图、视频、语音等多媒体内容，并支持多轮迭代优化，最终输出符合小红书平台风格的高质量内容。

### 核心能力

| 能力 | 说明 |
|------|------|
| **AI 对话式创作** | 通过自然语言描述需求，AI 自动解析并生成内容方案 |
| **多模态生成** | 支持文案、图片、视频、语音等多种内容形式 |
| **迭代优化** | 用户反馈驱动多轮修改，直到满意为止 |
| **版本管理** | 内容持久化和版本回滚，不丢失任何创作进度 |
| **智能审核** | 自动检测敏感词和内容质量 |
| **Canvas 画布** | 可视化编辑和调整内容元素 |

---

## 核心概念

### 1. Session（创作会话）

一次完整的创作过程称为一个 **Session**。每个会话包含：

- **Brief** - 需求解析结果
- **ContentPlan** - 内容方案
- **ContentItem[]** - 生成的内容项（文案/图片/视频/语音）
- **Version[]** - 版本历史
- **Message[]** - 对话消息历史

#### 会话状态机

```
CREATED → PLANNING → CONFIRMED → GENERATING → REVIEWING
                                              ↓
                    ITERATING ← ← ← ← ← ← ← ← ←
                         ↓
                      COMPLETED → PUBLISHED
                         ↓
                     CANCELLED
```

| 状态 | 说明 |
|------|------|
| `CREATED` | 会话已创建，等待输入需求 |
| `PLANNING` | 正在解析需求，生成 Brief 和 ContentPlan |
| `CONFIRMED` | 用户已确认方案，待生成 |
| `GENERATING` | 正在生成内容 |
| `REVIEWING` | 内容生成完成，等待用户审核 |
| `ITERATING` | 迭代修改中 |
| `COMPLETED` | 创作完成 |
| `PUBLISHED` | 已发布 |
| `CANCELLED` | 已取消 |

### 2. Brief（需求解析）

Brief 是 AI 解析用户需求后生成的**结构化需求文档**。

```python
@dataclass
class Brief:
    goal: ContentGoal           # 内容目标（种草/测评/教程等）
    style: str                  # 风格（活泼/专业/治愈等）
    keywords: List[str]         # 关键词/卖点
    must_include: List[str]    # 必须包含的元素
    image_style: str           # 配图风格偏好
    need_video: bool           # 是否需要视频
    need_voiceover: bool       # 是否需要配音
    need_text: bool           # 是否需要文案
    need_images: bool          # 是否需要配图
    target_audience: str       # 目标受众
    reference_materials: List[Material]  # 参考素材
    raw_input: str             # 原始用户输入
```

#### ContentGoal 类型

```python
class ContentGoal(Enum):
    PLANT = "plant"        # 种草
    TUTORIAL = "tutorial" # 教程
    REVIEW = "review"      # 测评
    LIFESTYLE = "lifestyle"  # 生活分享
    PRODUCT = "product"    # 产品展示
    OTHER = "other"        # 其他
```

### 3. ContentPlan（内容方案）

在生成内容之前，AI 会先生成一个**内容方案**，包含：

- **标题** - 主标题和副标题
- **TextSection[]** - 文案结构（开头/正文/结尾/标签）
- **ImagePlan** - 配图方案（数量/风格/构图）
- **VideoPlan** - 视频方案（如需要）
- **AudioPlan** - 语音方案（如需要）

### 4. ContentItem（内容项）

生成的具体内容单元：

| 类型 | 说明 |
|------|------|
| `TEXT` | 文案内容 |
| `IMAGE` | 图片内容 |
| `VIDEO` | 视频内容 |
| `AUDIO` | 语音内容 |

每个 ContentItem 包含：
- 内容本身（文本或 URL）
- 元数据（尺寸、时长等）
- 生成状态
- 修改历史

---

## 目录结构

```
studio/
├── __init__.py
├── agent/                     # Agent 核心
│   ├── agent.py             # Agent 主逻辑
│   ├── tools.py             # Agent 工具定义
│   ├── context_manager.py   # 上下文管理
│   ├── message_store.py     # 消息存储
│   └── canvas_tools.py      # 画布工具
│
├── api/                       # API 接口
│   ├── routes.py            # 路由定义
│   ├── schemas.py           # Pydantic 模型
│   ├── websocket_manager.py # WebSocket 管理
│   ├── auth.py              # 认证
│   └── errors.py            # 错误处理
│
├── canvas/                   # Canvas 画布
│   ├── canvas_core.py       # 画布核心
│   ├── canvas_agent.py      # 画布 Agent
│   ├── canvas_storage.py    # 画布存储
│   ├── canvas_sync.py       # 画布同步
│   ├── selection_extractor.py # 框选提取
│   ├── mode_router.py       # 模式路由
│   └── skills/              # 画布技能
│       ├── canvas_draw.yaml
│       ├── canvas_edit.yaml
│       ├── canvas_undo.yaml
│       └── ...
│
├── config/                   # 配置
│   └── studio_config.py
│
├── core/                     # 核心模块
│   ├── orchestrator.py      # 总控调度
│   ├── brief_parser.py     # 需求解析
│   ├── planner.py           # 方案规划
│   ├── critic.py           # 审核反馈
│   ├── iterator.py          # 迭代控制
│   └── publisher.py         # 发布器
│
├── db/                       # 数据库
│   ├── connection.py
│   └── models.py
│
├── models/                   # 数据模型
│   ├── brief.py
│   ├── content_plan.py
│   ├── content_item.py
│   ├── session.py
│   ├── version.py
│   └── message.py
│
├── services/                # 服务
│   └── auth_service.py
│
├── skills/                   # 技能系统
│   ├── base_skill.py       # 技能基类
│   ├── text_skill.py       # 文本技能
│   ├── image_skill.py      # 图像技能
│   ├── video_skill.py      # 视频技能
│   ├── audio_skill.py      # 语音技能
│   ├── analytic_skill.py   # 分析技能
│   ├── skill_registry.py   # 技能注册
│   └── skill_enforcer.py   # 技能执行
│
└── storage/                 # 存储
    ├── session_store.py
    ├── version_store.py
    ├── content_store.py
    └── db_session_store.py
```

---

## 功能详解

### 1. AI 对话式创作

用户通过自然语言描述创作需求，AI 自动完成：

1. **需求解析** - BriefParser 分析用户输入
2. **方案生成** - Planner 生成内容方案
3. **用户确认** - 用户确认或修改方案
4. **内容生成** - Skill 层调用模型生成实际内容

```python
# 示例对话
用户: "我想推荐一款保湿面膜，要清新自然的风格"
AI: "好的，我来帮你生成。请问需要配图还是只需要文案？"

用户: "要配图"
AI: "了解。我来生成内容方案..."
  → Brief: goal=PLANT, style=清新自然, need_images=True
  → ContentPlan: 标题 + 3段文案 + 2张配图

用户: "确认"
AI: "正在生成文案和配图..."
  → TextSkill → 文案生成完成
  → ImageSkill → 配图生成完成
```

### 2. 多模态生成

支持同时生成多种类型的内容：

| 技能 | 调用模型 | 功能 |
|------|---------|------|
| `TextSkill` | LLM | 生成小红书风格文案 |
| `ImageSkill` | Image Generation | 生成配图 |
| `VideoSkill` | Video Generation | 生成视频 |
| `AudioSkill` | TTS | 生成语音配音 |
| `AnalyticSkill` | Vision | 分析素材图片 |

**按需生成机制**：

```python
# 只生成文案
brief.need_text = True
brief.need_images = False

# 只生成配图
brief.need_text = False
brief.need_images = True

# 都要
brief.need_text = True
brief.need_images = True
```

### 3. 迭代优化

用户可以对生成的内容提出修改意见，AI 会针对性地修改：

```
用户: "标题不够吸引人，能换个更有悬念的吗？"

AI: "好的，我来修改标题..."
  → Iterator 解析反馈：只需修改标题
  → 保持文案正文和配图不变
  → 生成新标题方案
  → 用户确认后更新版本
```

### 4. 版本管理

每次修改都会创建新版本，保留完整历史：

```
版本 v1: 初始生成
版本 v2: 修改标题
版本 v3: 调整配图风格
版本 v4: 最终版本
```

**版本操作**：
- `GET /api/studio/sessions/:id/versions` - 获取版本列表
- `GET /api/studio/sessions/:id/versions/:version/content` - 获取版本内容
- `POST /api/studio/sessions/:id/restore/:version` - 回滚到指定版本

### 5. Canvas 画布

Canvas 提供可视化编辑能力：

**功能**：
- 拖拽文件（图片/视频）到画布
- 框选内容元素
- 元素对齐和分布
- 画布快照和回溯
- AI 辅助编辑建议

**操作类型**：
```python
class OperationType(Enum):
    ADD_ELEMENT = "add_element"
    MOVE_ELEMENT = "move_element"
    RESIZE_ELEMENT = "resize_element"
    DELETE_ELEMENT = "delete_element"
    STYLE_CHANGE = "style_change"
    LAYER_CHANGE = "layer_change"
    UNDO = "undo"
    REDO = "redo"
```

### 6. 技能系统（Skill）

基于 YAML 定义的技能框架，支持动态加载和执行：

```yaml
# skills/canvas_draw.yaml
name: canvas_draw
description: 在画布上绘制元素
parameters:
  - name: element_type
    type: string
    required: true
  - name: position
    type: object
    required: true
```

**内置画布技能**：
- `canvas_draw` - 绘制元素
- `canvas_edit` - 编辑元素
- `canvas_undo` - 撤销操作
- `canvas_snapshot` - 快照管理
- `canvas_understand` - 理解画布内容
- `canvas_planning` - 规划编辑

---

## 使用指南

### 1. 启动服务

```bash
# 方式一：一键启动
python start_all.py

# 方式二：分别启动
python start_backend.py   # 后端 8080
python start_frontend.py  # 前端 3000
```

### 2. 访问 Studio

打开浏览器访问 **http://localhost:3000**，点击顶部导航进入 **Studio** 页面。

### 3. 创建会话

1. 点击「新建会话」
2. 输入内容需求（如：「推荐一款保湿面膜」）
3. 可上传参考素材（图片/文案模板）
4. 等待 AI 解析生成 Brief 和 ContentPlan

### 4. 确认方案

1. 查看 AI 生成的方案预览
2. 可选择修改：
   - 调整内容目标
   - 修改风格偏好
   - 增删素材
3. 点击「确认方案」开始生成

### 5. 生成内容

- 文案和配图会**并行生成**
- 可实时查看生成进度
- 生成完成后进入审核状态

### 6. 迭代修改

1. 查看生成的内容
2. 如需修改，点击「反馈」按钮
3. 输入修改意见（如：「标题更吸引人一些」）
4. AI 会针对性修改
5. 重复直到满意

### 7. 发布/导出

1. 点击「发布」或「导出」
2. 系统会进行最终审核
3. 生成素材包（ZIP）
4. 可直接发布到小红书或保存备用

---

## API 接口

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/studio/sessions` | 创建会话 |
| `GET` | `/api/studio/sessions` | 获取会话列表 |
| `GET` | `/api/studio/sessions/:id` | 获取会话详情 |
| `DELETE` | `/api/studio/sessions/:id` | 删除会话 |

### 内容生成

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/studio/sessions/:id/confirm` | 确认方案，开始生成 |
| `GET` | `/api/studio/sessions/:id/generate` | 获取生成进度 |
| `POST` | `/api/studio/sessions/:id/feedback` | 提交反馈 |
| `POST` | `/api/studio/sessions/:id/publish` | 发布内容 |

### 版本管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/studio/sessions/:id/versions` | 获取版本列表 |
| `GET` | `/api/studio/sessions/:id/versions/:v/content` | 获取版本内容 |
| `POST` | `/api/studio/sessions/:id/restore/:v` | 回滚到版本 |

### Canvas

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/canvas` | 创建画布 |
| `GET` | `/api/canvas/:id` | 获取画布 |
| `POST` | `/api/canvas/:id/operations` | 执行操作 |
| `GET` | `/api/canvas/:id/snapshot` | 获取快照 |

---

## 数据存储

### 会话数据

```
data/studio/sessions/{session_id}/
├── versions/
│   ├── v1/
│   │   ├── items.json
│   │   └── images/
│   └── v2/
└── current/
    ├── images/
    ├── videos/
    └── audio/
```

### Canvas 数据

```
data/studio/canvases/
├── canvases/
│   └── {canvas_id}.json
└── metadata/
    └── index.json
```

### 素材数据

```
data/studio/materials/
├── {material_id}.png
└── {material_id}.webp
```

---

## 技术架构

### 分层架构

```
┌─────────────────────────────────────────┐
│           用户交互层 (Web UI)            │
├─────────────────────────────────────────┤
│           API 接口层 (FastAPI)           │
├─────────────────────────────────────────┤
│           Agent 核心层                   │
│  ┌─────────┬─────────┬─────────┐     │
│  │BriefParser│ Planner │ Critic  │     │
│  └─────────┴─────────┴─────────┘     │
├─────────────────────────────────────────┤
│           Skill 执行层                   │
│  ┌────┬────┬────┬────┬────┐         │
│  │Text│Image│Video│Audio│Analytic│     │
│  └────┴────┴────┴────┴────┘         │
├─────────────────────────────────────────┤
│         Model Gateway 层 (Phase 2)      │
│  ┌────┬────┬────┬────┬────┐         │
│  │ LLM│Vision│Image│ TTS │Video│     │
│  └────┴────┴────┴────┴────┘         │
└─────────────────────────────────────────┘
```

### WebSocket 实时通信

支持实时推送生成进度：

```javascript
// 前端连接
const ws = new WebSocket('ws://localhost:8080/ws/session/{session_id}');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'progress') {
    updateProgress(data.percent, data.message);
  } else if (data.type === 'content') {
    appendContent(data.item);
  }
};
```

---

## 最佳实践

### 1. 需求描述技巧

| 好的描述 | 不好的描述 |
|---------|-----------|
| 「推荐一款保湿面膜，要清新自然的风格，适合学生党」 | 「推荐面膜」 |
| 「分享我最近在用的护肤品，要有使用前后对比」 | 「护肤品分享」 |
| 「教程：如何正确清洁面部」 | 「教护肤」 |

### 2. 反馈修改技巧

| 场景 | 建议的反馈方式 |
|------|--------------|
| 标题不够好 | 「标题太普通，换个更有悬念的」 |
| 配图风格不对 | 「配图风格太正式了，换成更生活化的」 |
| 正文太长 | 「精简到 500 字以内」 |
| 需要调整结构 | 「把使用步骤放到最前面」 |

### 3. 版本回滚建议

- 重要修改前先确认当前版本
- 回滚后不满意可以再次生成
- 保持 3-5 个版本以便对比

---

## 常见问题

### Q: 如何添加新的 Skill？

1. 在 `studio/skills/` 下创建新的 Skill 类
2. 继承 `BaseSkill`
3. 实现 `execute` 方法
4. 在 `skill_registry.py` 中注册

### Q: 支持哪些 AI 模型？

通过配置 `config.json` 可以使用：
- **LLM**: OpenAI GPT、Claude、Qwen 等
- **Image**: DALL-E、Stable Diffusion、Qwen Image 等
- **TTS**: OpenAI TTS、MiniMax TTS 等
- **Video**: Sora、MiniMax Video 等

### Q: 如何实现断路器？

Model Gateway 层内置断路器：
- 连续失败 5 次后自动开启
- 60 秒后自动尝试恢复
- 可在配置中调整阈值

---

## 更新日志

- [2026-04-28] v1.1.0 - 支持按需生成机制和图文冲突检测
- [2026-04-27] v1.0.0 - 完成 Canvas 画布和版本管理功能
- [2026-04-27] v0.9.0 - 完成 Skill 技能系统
- [2026-04-27] v0.8.0 - 完成 Agent 对话和迭代优化
- [2026-04-26] v0.5.0 - 完成基础会话管理

---

## 贡献指南

欢迎贡献代码！请遵循以下规范：

1. 代码风格遵循 PEP 8
2. 新功能添加测试用例
3. 更新相关文档
4. 提交前运行 `python -m pytest tests/`

---

*Last updated: 2026-04-28*
