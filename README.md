# Redbook 项目文档

<!--
project:
  name: Redbook
  version: "1.1.0"
  phases:
    - id: 1
      name: 配置管理 UI 服务器
      status: completed
      completed_at: "2026-04-26"
    - id: 2
      name: 模型网关（Model Gateway）
      status: completed
      completed_at: "2026-04-27"
    - id: 3
      name: 小红书内容生成 Agent
      status: completed
      completed_at: "2026-04-27"
    - id: 4
      name: 记忆模块
      status: completed
      completed_at: "2026-04-27"
    - id: 5
      name: 核心功能补全
      status: completed
      completed_at: "2026-04-27"
    - id: 6
      name: 内容持久化与版本回滚
      status: completed
      completed_at: "2026-04-27"
-->

## 项目概述

Redbook 是一个 AI 小红书**创意工坊（Studio）**系统，通过 AI Agent 技术帮助用户自动生成小红书文案、配图、视频、语音等多媒体内容。

### 核心模块

| 模块 | 说明 |
|------|------|
| **Studio 创意工坊** | AI 对话式内容创作，支持多轮迭代优化、版本管理、Canvas 画布 |
| **Agent** | 智能 Agent 系统，包含 BriefParser、Planner、Critic、Iterator |
| **Skills** | 技能系统，支持 Text、Image、Video、Audio 等多模态内容生成 |
| **Memory** | 记忆模块，支持短期/长期记忆，向量检索 |
| **Canvas** | 可视化画布，支持拖拽、框选、快照、AI 辅助编辑 |

### 创意工坊核心能力

| 能力 | 说明 |
|------|------|
| **AI 对话式创作** | 自然语言描述需求，AI 自动解析并生成内容方案 |
| **多模态生成** | 同时生成文案、图片、视频、语音 |
| **迭代优化** | 用户反馈驱动多轮修改，直到满意 |
| **版本管理** | 内容持久化，支持版本回滚 |
| **Canvas 画布** | 可视化编辑和调整内容元素 |
| **智能审核** | 自动检测敏感词和内容质量 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install httpx chromadb numpy
cd C:\Users\LWB\Desktop\redbook\config-ui\frontend
npm install
```

### 2. 配置 API Key

在系统环境变量中设置：
```bash
set OPENAI_API_KEY=your-openai-api-key
set ANTHROPIC_API_KEY=your-anthropic-api-key
```

或在 `config.json` 中配置（参考 Phase 2 部分）。

### 3. 启动服务

```bash
# 方式 1：一键启动
python start_all.py

# 方式 2：分别启动
python start_backend.py   # 后端（端口 8080）
python start_frontend.py  # 前端（端口 3000）
```

### 4. 访问 Studio

打开浏览器访问 **http://localhost:3000**，点击顶部导航进入 **Studio** 页面。

### 5. 创建第一个内容

1. **创建会话** - 输入需求描述（如"推荐一款保湿面膜"）
2. **确认方案** - 查看生成的内容方案，点击"确认"
3. **生成内容** - 自动并行生成文案和配图
4. **迭代修改** - 提交反馈如"标题更吸引人一些"
5. **发布/导出** - 满意后导出素材包

## 目录结构

```
C:\Users\LWB\Desktop\redbook\
├── config.json                 # 统一配置文件（所有环境的模型配置）
├── agent\                     # Agent 模块（Phase 2）
│   ├── config\                # 配置服务
│   ├── models\                # 模型网关
│   ├── providers\             # 提供商基类
│   ├── exceptions\            # 异常定义
│   └── utils\                # 工具函数
├── config-ui\                 # 配置管理 UI（Phase 1）
│   ├── backend\               # FastAPI 后端
│   └── frontend\              # React 前端
├── studio\                    # 内容生成 Studio（Phase 3）
│   ├── core\                  # 核心模块（Orchestrator/BriefParser/Planner/Critic/Iterator）
│   ├── skills\               # Skill 层
│   ├── models\               # 数据模型
│   ├── api\                  # API 接口
│   └── storage\              # 存储层
├── plan\                      # 项目规划文档
└── start_*.py / stop_*.py    # 启动/停止脚本
```

---

## Phase 1: 配置管理 UI 服务器

### 功能说明

提供 Web UI 界面管理 `config.json` 配置文件，支持：
- 多环境配置（development、staging、production）
- 5 种模型配置（llm、vision、image_generation、tts、video）
- 配置导入/导出
- 实时配置预览

### 技术栈

- **后端**: FastAPI (Python)
- **前端**: React 19 + Tailwind CSS 4
- **端口**: 前端 3000，后端 8080

### 启动方式

```bash
# 方式 1：使用启动脚本
python start_all.py

# 方式 2：分别启动
python start_frontend.py  # 启动前端
python start_backend.py   # 启动后端

# 方式 3：手动启动
cd config-ui/frontend && npm run dev    # 前端
cd config-ui/backend && uvicorn main:app --reload --port 8080  # 后端
```

### 访问地址

- 前端 UI: http://localhost:3000
- 后端 API: http://localhost:8080
- API 文档: http://localhost:8080/docs

### 配置文件路径

- 位置: `C:\Users\LWB\Desktop\redbook\config.json`
- 结构: `environments[env].models`

---

## Phase 2: 模型网关（Model Gateway）

### 功能说明

为 5 种模型提供统一的调用封装，支持：
- Primary/Fallback 自动切换
- 断路器模式（Circuit Breaker）
- 环境变量自动解析（`${ENV_VAR}` 语法）
- Streaming 响应支持

### 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    GatewayFactory                        │
│  (单例模式，每个 gateway_type 只创建一个实例)             │
└─────────────────┬───────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┬─────────────┬─────────────┐
    │             │             │             │             │
    ▼             ▼             ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌────────────┐  ┌────────┐  ┌────────┐
│  LLM   │  │  Vision  │  │   Image    │  │  TTS    │  │  Video │
│Gateway │  │ Gateway  │  │ Generation │  │ Gateway │  │Gateway │
└────┬───┘  └────┬─────┘  └──────┬─────┘  └────┬────┘  └───┬────┘
     │            │               │             │            │
     └────────────┴───────────────┴─────────────┴────────────┘
                                │
                    ┌───────────┴───────────┐
                    │      BaseGateway      │
                    │  - Circuit Breaker    │
                    │  - Primary/Fallback   │
                    │  - Retry Logic        │
                    └───────────┬───────────┘
                                │
                    ┌───────────┴───────────┐
                    │    BaseProvider       │
                    │  - HTTP Client        │
                    │  - Retry with backoff  │
                    └───────────────────────┘
```

### 支持的模型类型

| 模型类型 | 网关类 | 请求类 | 主要功能 |
|---------|--------|--------|---------|
| llm | `LLMGateway` | `LLMRequest` | 文本生成、流式输出 |
| vision | `VisionGateway` | `VisionRequest` | 图像理解（URL/base64） |
| image_generation | `ImageGenerationGateway` | `ImageGenerationRequest` | 图像生成（DALL-E） |
| tts | `TTSGateway` | `TTSRequest` | 语音合成 |
| video | `VideoGateway` | `VideoGenerationRequest` | 视频生成（异步+轮询） |

### 快速开始

#### 1. 安装依赖

```bash
pip install httpx
```

#### 2. 配置环境变量

```bash
export OPENAI_API_KEY="your-openai-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

#### 3. 基本使用

```python
import asyncio
from agent import AgentConfigService, GatewayFactory, LLMRequest

async def main():
    # 获取配置服务（单例）
    config = AgentConfigService()

    # 获取 LLM 网关
    llm_gateway = GatewayFactory.get_gateway("llm", config)

    # 发起请求
    response = await llm_gateway.invoke(LLMRequest(
        messages=[
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好！"}
        ],
        temperature=0.7,
        max_tokens=1000
    ))

    # 处理响应
    if response.success:
        content = response.data["content"]
        print(f"生成文本: {content}")
        print(f"使用模型: {response.model_used}")
        print(f"延迟: {response.latency_ms}ms")
    else:
        print(f"错误: {response.error}")

asyncio.run(main())
```

#### 4. 流式响应

```python
async def stream_example():
    config = AgentConfigService()
    llm_gateway = GatewayFactory.get_gateway("llm", config)

    async for chunk in llm_gateway.stream(LLMRequest(
        messages=[{"role": "user", "content": "写一个故事"}],
        stream=True
    )):
        print(chunk.content, end="", flush=True)
        if chunk.done:
            print()  # 换行
```

#### 5. 使用其他网关

```python
# Vision 网关
vision_gateway = GatewayFactory.get_gateway("vision", config)
vision_response = await vision_gateway.invoke(VisionRequest(
    image="https://example.com/image.jpg",
    prompt="描述这张图片"
))

# Image Generation 网关
image_gateway = GatewayFactory.get_gateway("image_generation", config)
image_response = await image_gateway.invoke(ImageGenerationRequest(
    prompt="一只可爱的猫",
    size="1024x1024",
    quality="standard"
))

# TTS 网关
tts_gateway = GatewayFactory.get_gateway("tts", config)
tts_response = await tts_gateway.invoke(TTSRequest(
    input="你好，世界！",
    voice="alloy",
    speed=1.0
))
# tts_response.data["audio"] 包含音频字节

# Video 网关
video_gateway = GatewayFactory.get_gateway("video", config)
video_response = await video_gateway.invoke(VideoGenerationRequest(
    prompt="日出时分的山脉",
    duration=5,
    resolution="1080p"
))
# video_response.data["video_url"] 包含视频 URL
```

### 响应格式

所有网关返回统一的 `GatewayResponse` 对象：

```python
@dataclass
class GatewayResponse:
    success: bool           # 请求是否成功
    data: Any = None       # 响应数据（具体结构因网关而异）
    error: str = None      # 错误信息（如果失败）
    model_used: str = None  # 实际使用的模型名称
    provider: str = None    # 实际使用的提供商
    latency_ms: float = None  # 请求延迟（毫秒）
```

### 网关状态

```python
class GatewayStatus(Enum):
    HEALTHY = "healthy"              # 正常
    DEGRADED = "degraded"            # 降级（部分提供商不可用）
    FALLBACK_ACTIVE = "fallback_active"  # Fallback 激活
    UNAVAILABLE = "unavailable"      # 不可用
```

### 异常类

```python
from agent.exceptions import (
    GatewayError,        # 基类异常
    APIError,            # API 错误（4xx/5xx）
    AuthenticationError,  # 认证失败
    RateLimitError,      # 速率限制
    TimeoutError,        # 请求超时
    CircuitBreakerOpenError  # 断路器开启
)
```

### 配置说明

配置文件 `config.json` 中的模型配置结构：

```json
{
  "environments": {
    "development": {
      "models": {
        "llm": {
          "primary": {
            "provider": "openai",
            "api_url": "https://api.openai.com/v1",
            "model_name": "gpt-4o",
            "api_key": "${OPENAI_API_KEY}",
            "default_params": {
              "temperature": 0.7,
              "max_tokens": 4096
            },
            "timeout": 120,
            "retry_count": 3,
            "enabled": true
          },
          "fallback": { ... }
        }
      }
    }
  },
  "activeEnvironment": "development"
}
```

---

## Phase 3: 小红书内容生成 Agent

### 状态

- [x] 架构设计
- [x] 目录结构创建
- [x] 核心数据模型
- [x] Orchestrator 实现
- [x] 内容规划器实现
- [x] 迭代控制器实现
- [x] API 接口开发
- [x] 前端集成
- [x] 测试验证

### 目标

构建一个智能 Agent 系统，实现小红书文案的自动化生成和迭代优化流程：

1. **需求解析** - 接收用户需求 + 图片/文本等素材
2. **方案规划** - 生成结构化 Brief 和内容方案
3. **多模态生成** - 分发给各模型执行（文本/图片/视频/语音）
4. **结果汇总** - 构建完整文案
5. **迭代优化** - 用户反馈 → 修改 → 循环
6. **发布支持** - 最终内容发布

### 核心架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户交互层                                      │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│   │   Web UI        │    │   终端聊天      │    │   API 接口      │     │
│   │   (React)       │    │   (prompt_toolkit)│  │   (FastAPI)    │     │
│   └────────┬────────┘    └────────┬────────┘    └────────┬────────┘     │
└────────────┼─────────────────────┼─────────────────────┼──────────────┘
             │                     │                     │
┌────────────▼─────────────────────▼─────────────────────▼──────────────┐
│                      Orchestrator (总控 Agent)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ BriefParser │  │PlannerAgent │  │CriticAgent │  │IterController│  │
│  │ (需求解析)   │  │ (方案规划)   │  │ (审核反馈)  │  │ (迭代控制)   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
┌─────────▼─────────────────▼─────────────────▼─────────────────▼─────────┐
│                         Skill 执行层 (与 Phase 2 解耦)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │TextSkill│  │ImageSkill│  │VideoSkill│  │AudioSkill│  │AnalyticSkill││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
└────────┼─────────────┼─────────────┼─────────────┼─────────────┼────────┘
         │            │            │            │            │
┌────────▼────────────▼────────────▼────────────▼────────────▼────────────┐
│                      Model Gateway Layer (Phase 2)                        │
│  ┌────────┐  ┌──────────┐  ┌────────────┐  ┌────────┐  ┌────────┐    │
│  │  LLM   │  │  Vision  │  │   Image    │  │  TTS    │  │  Video │    │
│  │Gateway │  │ Gateway  │  │ Generation │  │ Gateway │  │Gateway │    │
│  └────────┘  └──────────┘  └────────────┘  └────────┘  └────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
C:\Users\LWB\Desktop\redbook\
├── agent\                           # Phase 2: 模型网关（已存在）
│   └── ...                          # 保持不变
│
├── studio\                          # Phase 3: 内容生成 Studio（新建）
│   ├── __init__.py
│   ├── config\                      # Studio 配置
│   │   ├── __init__.py
│   │   └── studio_config.py        # Studio 特定配置
│   │
│   ├── core\                       # 核心模块
│   │   ├── __init__.py
│   │   ├── orchestrator.py        # 总控 Orchestrator
│   │   ├── brief_parser.py         # Brief 解析器
│   │   ├── planner.py             # 内容规划器
│   │   ├── critic.py              # 审核反馈
│   │   ├── iterator.py            # 迭代控制器
│   │   └── publisher.py           # 发布器
│   │
│   ├── skills\                     # Skill 层（调用 Phase 2 网关）
│   │   ├── __init__.py
│   │   ├── base_skill.py          # Skill 基类
│   │   ├── text_skill.py          # 文本生成 Skill
│   │   ├── image_skill.py         # 图像生成 Skill
│   │   ├── video_skill.py         # 视频生成 Skill
│   │   ├── audio_skill.py         # 音频生成 Skill
│   │   └── analytic_skill.py      # 分析 Skill
│   │
│   ├── models\                     # 数据模型
│   │   ├── __init__.py
│   │   ├── brief.py               # Brief 数据结构
│   │   ├── content_plan.py        # 内容方案
│   │   ├── content_item.py        # 内容项（文案/图片/视频）
│   │   ├── session.py             # 创作会话
│   │   └── version.py             # 版本记录
│   │
│   ├── api\                        # API 接口
│   │   ├── __init__.py
│   │   ├── routes.py              # API 路由
│   │   └── schemas.py             # Pydantic schemas
│   │
│   └── storage\                    # 存储层
│       ├── __init__.py
│       ├── session_store.py        # 会话存储
│       └── version_store.py       # 版本存储
```

### 核心数据模型

#### Brief (需求解析结果)

```python
@dataclass
class Brief:
    """用户需求解析结果"""
    id: str
    goal: ContentGoal           # 内容目标（种草/测评/教程等）
    style: str                  # 风格（活泼/专业/治愈等）
    keywords: List[str]          # 关键词/卖点
    must_include: List[str]      # 必须包含的元素
    image_style: str            # 配图风格偏好
    need_video: bool            # 是否需要视频
    need_voiceover: bool        # 是否需要配音
    need_text: bool             # 是否需要文案（默认 True）
    need_images: bool           # 是否需要配图（默认 True）
    target_audience: str        # 目标受众
    reference_materials: List[Material]  # 参考素材
    raw_input: str              # 原始用户输入
    created_at: datetime
```

#### ContentPlan (内容方案)

```python
@dataclass
class ContentPlan:
    """完整内容方案"""
    brief_id: str
    title: str                  # 标题
    text_sections: List[TextSection]  # 文案结构
    image_plan: ImagePlan       # 配图方案
    video_plan: VideoPlan       # 视频方案（可选）
    audio_plan: AudioPlan       # 音频方案（可选）
    estimated_duration: int      # 预计创作时间（分钟）
    version: int                # 方案版本号
```

#### ContentItem (内容项)

```python
@dataclass
class ContentItem:
    """单个内容项"""
    id: str
    item_type: ContentType      # text/image/video/audio
    content: str                # 文本内容或 URL
    metadata: Dict[str, Any]    # 元数据（尺寸、时长等）
    status: ItemStatus          # pending/generating/completed/failed
    generation_prompt: str      # 生成时使用的提示词
    revision_history: List[Revision]  # 修改历史
```

#### Session (创作会话)

```python
@dataclass
class Session:
    """创作会话"""
    id: str
    brief: Brief
    current_plan: ContentPlan
    current_version: int
    items: List[ContentItem]
    status: SessionStatus       # planning/generating/reviewing/published
    created_at: datetime
    updated_at: datetime
    versions: List[Version]     # 版本历史
```

### Agent 协作流程

```
用户输入 ──┐
素材上传 ──┼──► BriefParser ──► Brief
                    │
                    ▼
             PlannerAgent ──► ContentPlan (方案预览)
                    │
                    ▼ (用户确认或修改)
          ┌───────┴───────┐
          │               │
          ▼               ▼
    ┌─────────┐     ┌─────────┐
    │ TextSkill│     │ImageSkill│
    │ (文案生成)│     │ (配图生成)│
    └────┬────┘     └────┬────┘
         │               │
         └───────┬───────┘
                 ▼
          ┌─────────────┐
          │CriticAgent  │
          │ (质量审核)   │
          └──────┬──────┘
                 │
          ┌──────┴──────┐
          │             │
          ▼             ▼
      通过            不通过
       │               │
       ▼               ▼
   ┌─────────┐   IteratorAgent
   │汇总结果  │◄──(修改意见)
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │用户反馈  │◄──(迭代循环)
   └────┬────┘
        │
   ┌────┴────┐
   │         │
   ▼         ▼
 满意    不满意
   │         │
   ▼         ▼
发布    继续迭代
```

### Skill 层设计（与 Phase 2 解耦）

```python
# skills/base_skill.py
class BaseSkill(ABC):
    """Skill 基类，封装 Phase 2 网关调用"""

    def __init__(self, gateway_factory: GatewayFactory):
        self.gateway = gateway_factory.get_gateway(self.gateway_type)

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """执行 Skill"""
        pass

# skills/text_skill.py
class TextSkill(BaseSkill):
    """文本生成 Skill"""
    gateway_type = "llm"

    async def execute(self, context: SkillContext) -> SkillResult:
        # 调用 LLMGateway 生成文案
        # 支持基于上下文的修改
        pass

# skills/image_skill.py
class ImageSkill(BaseSkill):
    """图像生成 Skill"""
    gateway_type = "image_generation"

    async def execute(self, context: SkillContext) -> SkillResult:
        # 调用 ImageGenerationGateway 生成配图
        pass
```

### 实现步骤

#### Step 3.1: 创建目录结构和数据模型

- [x] 创建 `studio/` 目录结构
- [x] 实现 `models/` 中的数据类（Brief, ContentPlan, ContentItem, Session, Version）
- [x] 创建 Pydantic schemas 用于 API

#### Step 3.2: 实现 Skill 层

- [x] 实现 `BaseSkill` 基类
- [x] 实现 `TextSkill`, `ImageSkill`, `VideoSkill`, `AudioSkill`
- [x] 实现 `AnalyticSkill`（用于分析素材）

#### Step 3.3: 实现 Orchestrator

- [x] 实现 `BriefParser` - 解析用户需求
- [x] 实现 `PlannerAgent` - 生成内容方案
- [x] 实现 `CriticAgent` - 质量审核
- [x] 实现 `IteratorAgent` - 迭代控制
- [x] 实现 `Orchestrator` - 总控调度

#### Step 3.4: 实现 API 接口

- [x] 创建会话 API（创建/获取/更新/删除）
- [x] 创建生成 API（开始生成/获取进度/取消）
- [x] 创建迭代 API（提交反馈/修改）
- [x] 创建发布 API

#### Step 3.5: 前端集成

- [x] 创建创作会话 UI
- [x] 实现方案预览组件
- [x] 实现内容编辑器
- [x] 实现迭代反馈 UI

### 依赖说明

```json
{
  "dependencies": {
    "fastapi": "0.110.0",
    "uvicorn": "0.27.0",
    "pydantic": "2.6.0",
    "python-multipart": "0.0.9"
  }
}
```

### 潜在问题及解决方案

| 问题 | 描述 | 解决方案 |
|------|------|----------|
| 模型调用失败 | 网关调用超时或返回错误 | Phase 2 已实现 Fallback 和重试 |
| 内容风格不一致 | 多模态内容风格不统一 | Planner 统一定义风格参数 |
| 迭代版本混乱 | 修改历史难以追踪 | 使用 Version 对象完整记录 |
| 会话状态丢失 | 服务重启后会话丢失 | 接入持久化存储（可选） |

---

## Phase 4: 记忆模块

### 功能说明

- **短期记忆**：会话级 Brief、生成内容、用户反馈
- **长期记忆**：用户风格偏好、品牌资产、成功模板
- **向量存储**：基于 Chroma 的语义检索

### 核心文件

| 文件 | 功能 |
|------|------|
| `memory/core/memory_manager.py` | 记忆管理器 |
| `memory/core/short_term.py` | 短期记忆 |
| `memory/core/long_term.py` | 长期记忆 |
| `memory/vector/chroma_client.py` | Chroma 客户端 |
| `memory/storage/sqlite_store.py` | SQLite 存储 |

### 技术选型

- 向量数据库：Chroma（嵌入式）
- 结构化存储：SQLite

---

## Phase 5: 核心功能补全

### 功能说明

- **按需生成机制**：通过 `need_text` 和 `need_images` 字段控制是否生成文案和配图
- **并行生成**：文案和配图同时生成，多张图片并行生成
- **图文冲突检测**：分析文案与图片是否匹配
- **方案确认流程**：用户确认方案后才开始生成
- **无素材后备机制**：多模态 LLM 从用户文本推断生成指示

### 核心代码

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

### 按需生成机制

| 场景 | need_text | need_images | 行为 |
|------|-----------|-------------|------|
| 只文案 | true | false | 只生成文案，跳过配图 |
| 只配图 | false | true | 只生成配图，跳过文案 |
| 都要 | true | true | 文案和配图都生成（默认） |

### 无素材时的后备机制

当用户没有上传素材但要求生成图片/视频/音频时，系统通过多模态 LLM 从用户文本中推断生成指示：

```
用户输入: "我想推荐一款面膜，要保湿效果好"
素材: 无
需求: need_images=True, need_video=True

         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  多模态 LLM 分析用户文本                                     │
│  → 推断配图风格: "清新护肤风"                              │
│  → 推断画面元素: ["面膜特写", "保湿效果"]                   │
│  → 推断视频场景: "敷面膜的护肤步骤"                         │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Planner 生成方案                                            │
│  ImagePlan: {style, elements, count, color_scheme}         │
│  VideoPlan: {scenes, duration, visual_prompt}              │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  实际模型生成                                                │
│  Image Gateway → 生成配图                                    │
│  Video Gateway → 生成视频                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 6: 内容持久化与版本回滚

### 功能说明

- **本地文件存储**：图片/视频/音频自动保存到本地
- **版本快照**：每次修改创建独立版本快照
- **版本预览**：前端可直接预览历史版本内容
- **版本回滚**：一键恢复历史版本到当前会话
- **用户上传替换**：支持本地文件替换生成的内容

### 存储目录

```
data/studio/sessions/{session_id}/
├── versions/
│   ├── v1/
│   │   ├── items.json    # 版本内容快照
│   │   └── images/       # 图片文件
│   └── v2/
└── current/
    ├── images/           # 当前版本图片
    ├── videos/           # 视频文件
    └── audio/            # 音频文件
```

### API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/studio/sessions/:id/versions/:version/content | 获取版本内容 |
| POST | /api/studio/sessions/:id/restore/:version | 从历史版本恢复 |
| POST | /api/studio/sessions/:id/items/:item_id/upload | 上传替换内容 |

---

## Studio 工作流详解

### 完整用户流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        Studio 工作流                             │
└─────────────────────────────────────────────────────────────────┘

1. 创建会话
   ├── 用户输入需求（文本描述）
   ├── 上传素材（图片/视频/音频）[可选]
   └── 系统解析需求，生成 Brief + ContentPlan

2. 方案确认
   ├── 显示 PlanDialog 弹窗
   ├── 展示 Brief 概要、方案详情
   ├── 用户点击「确认方案」
   └── 状态变为 CONFIRMED，自动开始生成

3. 内容生成
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

6. 版本管理
   ├── 查看版本历史
   ├── 预览历史版本内容
   └── 回滚到历史版本

7. 发布/导出
   ├── 模拟发布（检查格式）
   ├── 导出素材包（ZIP）
   └── 状态变为 PUBLISHED
```

### 状态机

```
CREATED → PLANNING → CONFIRMED → GENERATING → REVIEWING
                                              ↓
                    ITERATING ← ← ← ← ← ← ← ← ←
                         ↓
                      COMPLETED → PUBLISHED
                         ↓
                     CANCELLED
```

### Studio UI 功能

| 组件 | 功能 |
|------|------|
| StudioPage | 主页面，包含会话列表和创作区 |
| PlanDialog | 方案确认弹窗 |
| ContentPreview | 内容预览，支持本地上传替换 |
| FeedbackPanel | 反馈提交面板 |
| VersionHistory | 版本历史，支持预览和回滚 |
| SessionList | 会话列表管理 |

---

## 创意工坊 Studio 详细介绍

> 详细文档请参阅 [STUDIO.md](./STUDIO.md)

### 核心概念

#### Session（创作会话）

一次完整的创作过程，包含：

- **Brief** - AI 解析后的结构化需求
- **ContentPlan** - 内容生成方案
- **ContentItem[]** - 生成的内容项
- **Version[]** - 版本历史
- **Message[]** - 对话消息历史

#### Brief（需求解析）

```python
@dataclass
class Brief:
    goal: ContentGoal           # 种草/测评/教程/生活分享/产品展示
    style: str                # 活泼/专业/治愈等
    keywords: List[str]        # 关键词/卖点
    must_include: List[str]    # 必须包含的元素
    image_style: str          # 配图风格（摄影实拍/插画/3D）
    need_text: bool          # 是否需要文案
    need_images: bool         # 是否需要配图
    need_video: bool          # 是否需要视频
    need_voiceover: bool     # 是否需要配音
    target_audience: str     # 目标受众
```

### 技能系统（Skills）

| 技能 | 调用模型 | 功能 |
|------|---------|------|
| `TextSkill` | LLM | 生成小红书风格文案 |
| `ImageSkill` | Image Generation | 生成配图 |
| `VideoSkill` | Video Generation | 生成视频 |
| `AudioSkill` | TTS | 生成语音配音 |
| `AnalyticSkill` | Vision | 分析素材图片 |

### Canvas 画布功能

**功能**：
- 拖拽文件（图片/视频）到画布
- 框选内容元素
- 元素对齐和分布
- 画布快照和回溯
- AI 辅助编辑建议

**操作类型**：
- `ADD_ELEMENT` - 添加元素
- `MOVE_ELEMENT` - 移动元素
- `RESIZE_ELEMENT` - 调整大小
- `DELETE_ELEMENT` - 删除元素
- `STYLE_CHANGE` - 样式修改
- `UNDO` / `REDO` - 撤销/重做

### 数据存储

```
data/studio/
├── sessions/{session_id}/
│   ├── versions/v1/items.json  # 版本快照
│   └── current/images/        # 当前版本文件
├── canvases/
│   └── {canvas_id}.json       # 画布数据
└── materials/                  # 素材文件
```

### 快速使用

```bash
# 1. 启动服务
python start_all.py

# 2. 访问 http://localhost:3000

# 3. 创建会话 → 输入需求 → 确认方案 → 生成内容 → 迭代优化 → 发布
```

---

## 更新日志

<!--
格式：
- [YYYY-MM-DD] [Phase X]: [描述]
-->

- [2026-05-28] 添加 Studio 创意工坊详细介绍文档和 README 更新
- [2026-04-28] Phase 5: 添加按需生成机制（need_text/need_images）和无素材后备机制
- [2026-04-27] Phase 6: 完成内容持久化与版本回滚功能
- [2026-04-27] Phase 5: 完成并行生成、图文冲突检测、方案确认流程
- [2026-04-27] Phase 4: 完成记忆模块（短期/长期记忆 + 向量存储）
- [2026-04-27] Phase 3: 完成小红书内容生成 Agent 系统实现（Orchestrator + 前端集成）
- [2026-04-27] Phase 2: 完成模型网关实现，支持 5 种模型统一调用
- [2026-04-26] Phase 1: 完成配置管理 UI 服务器

---

## 常见问题

### Q: 如何添加新的模型提供商？

A: 需要实现 `BaseProvider` 接口并创建对应的 Gateway：

```python
# 1. 在 providers/ 下创建新的 Provider 类
class CustomProvider(BaseProvider):
    async def chat_completions(self, messages, **kwargs):
        # 实现 API 调用
        pass

    async def chat_completions_stream(self, messages, **kwargs):
        # 实现流式调用
        pass

# 2. 在对应 Gateway 的 _create_provider 方法中返回实例
class CustomGateway(BaseGateway):
    def _create_provider(self, config):
        return CustomProvider(config)
```

### Q: 如何添加新的模型类型？

A: 在 `agent/models/` 下创建新的网关文件，并更新 `gateway_factory.py` 的 `gateway_map`。

### Q: 断路器如何工作？

A: 当失败次数达到阈值（默认 5 次），断路器会打开并阻止后续请求 60 秒。之后自动尝试恢复。

---

## 贡献指南

1. 每个 Phase 独立开发，完成后更新本 README
2. 使用清晰的 commit 消息
3. 更新本文件的更新日志部分
