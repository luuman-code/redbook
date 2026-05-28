# 小红书内容生成 Agent 系统设计方案

## 一、整体架构设计

采用**多智能体协作架构 + 中心调度器**模式，类似于 AutoGen、CrewAI 或 LangGraph 构建的 Multi-Agent 系统。

### 架构层次

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                               │
│    Web 前端 (对话式界面 + 内容预览)    │    配置管理 UI 服务器    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Agent 调度核心                               │
│  - Orchestrator (总控Agent)                                    │
│  - Planner (方案规划Agent)                                      │
│  - Critic (审核反馈Agent)                                       │
│  - Memory (会话/知识记忆)                                       │
└──┬───────┬───────┬───────┬───────┬─────────┬───────────────────┘
   │       │       │       │       │         │
┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──┐┌──▼──────────────┐
│文本 ││图像 ││视频 ││语音 ││数据  ││需求解析         │
│生成 ││生成 ││生成 ││生成 ││分析  ││Agent            │
│Agent││Agent││Agent││Agent││Agent ││                 │
└──┬──┘└──┬──┘└──┬──┘└──┬──┘└────┘└──────┬─────────┘
   │      │      │      │      │           │
┌──▼──────▼──────▼──────▼──────▼───────────▼─────────────────────┐
│                    模型网关 & API管理层                          │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              模型配置中心 (可配置每个模型的 API/URL)       │   │
│   └─────────────────────────────────────────────────────────┘   │
│   (统一调用各模型的 API，所有 endpoint 从配置读取)               │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    数据与存储层                                  │
│  - 素材库 (用户上传图片/文本/视频)                              │
│  - 版本管理 (文案迭代历史)                                       │
│  - 发布接口 (模拟/真实发布到小红书)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、核心模块详解

### 1. 用户交互与需求输入模块

**多模态输入**：支持文字描述、图片、短视频、参考文案、产品文档等。

**需求解析 Agent**：用 LLM 将用户模糊需求转化为结构化 Brief，提取：

- 文案目标（种草、教程、测评…）
- 风格/人设（活泼、专业、治愈…）
- 必须包含的关键词/卖点
- 参考图片/视频中的视觉元素
- 期望的配图风格（摄影实拍、插画、3D…）
- 是否需要视频、旁白配音、BGM 建议等

---

### 2. 方案规划 Agent (Planner)

接到 Brief 后，输出一份内容实施方案：

```json
{
  "title": "...",
  "text_sections": [
    { "type": "headline", "content_words": "..." },
    ...
  ],
  "image_plan": {
    "style": "日系胶片摄影",
    "elements": [...],
    "count": 4
  },
  "video_plan": {
    "duration": "15s",
    "scenes": [...],
    "voiceover": "温柔女声"
  },
  "audio_plan": {
    "tts_text": "...",
    "bgm_style": "轻快vlog"
  }
}
```

此方案会先展示给用户确认，或直接进入生成。

---

### 3. 多模态生成 Agent 集群

每个 Agent 都是独立的微服务或功能节点，由 Orchestrator 调度。

| Agent 类型 | 功能 | 推荐模型 |
|-----------|------|---------|
| 文本生成 Agent | 标题、正文、话题标签、互动引导语 | 可配置 |
| 图像生成 Agent | 根据文案和风格生成配图 | 可配置 |
| 图像理解 Agent | 分析用户上传的参考图，提取构图、色彩、风格描述 | 可配置 |
| 视频生成 Agent | 将图文转为短视频（口播/图文快剪） | 可配置 |
| 语音生成 Agent | 生成旁白配音 | 可配置 |
| 数据分析 Agent | 处理 Excel/链接中的产品信息 | 可配置 |

**注意**：所有 Agent 的模型配置均为可自定义，详见下方「模型配置中心」章节。

---

### 4. Orchestrator (总调度 Agent)

- 维护一个任务 DAG，根据方案并行/串行调用各 Agent
- 收集所有 Agent 输出，进行冲突检测与融合（如文案里提到的"粉色的花"但图片里没有，需提醒或自动修正）
- 最终组装成小红书完整的笔记数据结构（标题+正文+图片列表+视频文件等），推送到前端预览

---

### 5. 审核与迭代 Agent (Critic)

- 内置小红书内容规范检查（敏感词、夸大词、违禁词）
- 美学评分（图文匹配度、标题吸引力）可依靠 LLM 自评或多模态模型评分

**用户修改流程**：

1. 修改意图识别（改标题、改第3张图、加重卖点语气…）
2. 定位修改范围：只修改受影响的组件，保留其他部分
3. 版本管理：基于上一版增量修改，所有历史版本保留，支持回退

---

### 6. 记忆模块 (Memory)

- **短期记忆**：当前会话的 Brief、中间方案、生成历史、用户反馈
- **长期记忆**：用户过往的风格偏好、品牌资产（Logo、常用配色）、成功文案模型

**实现**：向量数据库（Chroma / Milvus）+ 结构化存储（PostgreSQL）

---

## 三、模型配置中心

### 设计目标

所有调用外部模型 API 的地方均从配置文件读取，支持：

- **API Endpoint（URL）**：可配置为官方 API、自建代理、第三方转发等
- **API Key**：支持多平台密钥管理
- **模型名称**：同一类型可切换不同模型（如 GPT-4o / Claude 3.5 / DeepSeek）
- **请求参数**：温度、最大 token、采样策略等
- **Fallback 策略**：主模型失败时自动切换备用模型

### 配置数据结构

```json
{
  "models": {
    "llm": {
      "primary": {
        "provider": "openai",
        "api_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "api_key": "${OPENAI_API_KEY}",
        "default_params": {
          "temperature": 0.7,
          "max_tokens": 4096,
          "top_p": 1.0
        }
      },
      "fallback": {
        "provider": "anthropic",
        "api_url": "https://api.anthropic.com/v1",
        "model_name": "claude-3-5-sonnet-latest",
        "api_key": "${ANTHROPIC_API_KEY}",
        "default_params": {
          "temperature": 0.7,
          "max_tokens": 4096
        }
      }
    },
    "vision": {
      "primary": {
        "provider": "openai",
        "api_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "api_key": "${OPENAI_API_KEY}"
      },
      "fallback": {
        "provider": "anthropic",
        "api_url": "https://api.anthropic.com/v1",
        "model_name": "claude-3-5-sonnet-latest",
        "api_key": "${ANTHROPIC_API_KEY}"
      }
    },
    "image_generation": {
      "primary": {
        "provider": "openai",
        "api_url": "https://api.openai.com/v1",
        "model_name": "dall-e-3",
        "api_key": "${OPENAI_API_KEY}",
        "default_params": {
          "size": "1024x1024",
          "quality": "standard"
        }
      },
      "fallback": {
        "provider": "stability",
        "api_url": "https://api.stability.ai/v1",
        "model_name": "stable-diffusion-xl-1024-v1-0",
        "api_key": "${STABILITY_API_KEY}"
      }
    },
    "tts": {
      "primary": {
        "provider": "elevenlabs",
        "api_url": "https://api.elevenlabs.io/v1",
        "model_name": "eleven_multilingual_v2",
        "api_key": "${ELEVENLABS_API_KEY}",
        "default_params": {
          "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
          }
        }
      },
      "fallback": {
        "provider": "azure",
        "api_url": "https://${AZURE_REGION}.tts.speech.microsoft.com",
        "model_name": "zh-CN-XiaoxiaoNeural",
        "api_key": "${AZURE_SPEECH_KEY}"
      }
    },
    "video": {
      "primary": {
        "provider": "runway",
        "api_url": "https://api.runwayml.com/v1",
        "model_name": "gen3_alpha_generate",
        "api_key": "${RUNWAY_API_KEY}"
      },
      "fallback": {
        "provider": "pika",
        "api_url": "https://api.pika.art/v1",
        "model_name": "pika-2.0",
        "api_key": "${PIKA_API_KEY}"
      }
    }
  }
}
```

### 模型类型与用途

| 模型类型 | 用途 | 在系统中的应用 |
|---------|------|---------------|
| `llm` | 大语言模型 | Orchestrator 调度、Planner 规划、Critic 审核、文本生成 |
| `vision` | 视觉理解模型 | 图像理解 Agent、分析参考图 |
| `image_generation` | 图像生成模型 | 图像生成 Agent |
| `tts` | 语音合成模型 | 语音生成 Agent |
| `video` | 视频生成模型 | 视频生成 Agent |

---

## 四、配置管理 UI 服务器

### 概述

独立部署的配置管理服务器，提供 Web UI 界面供用户管理所有模型配置。

### 技术选型

| 组件 | 技术栈 | 说明 |
|------|--------|------|
| 后端服务 | FastAPI | 提供 RESTful API |
| 前端界面 | React 19 + Tailwind CSS 4 | 配置管理界面 |
| 配置文件存储 | JSON 文件 / PostgreSQL | 持久化配置 |
| 环境变量管理 | 支持 `${ENV_VAR}` 语法 | API Key 安全管理 |

### 功能特性

#### 1. 模型配置管理

- **列表展示**：所有模型配置以卡片/表格形式展示
- **新增配置**：选择 Provider，自动填充默认 URL 和参数
- **编辑配置**：修改 API URL、模型名称、请求参数
- **删除配置**：二次确认后删除
- **启用/禁用**：快速开关某项配置

#### 2. 多环境支持

- **环境切换**：开发环境 / 测试环境 / 生产环境
- **环境隔离**：每套环境独立的 API Key 和参数
- **配置导入/导出**：JSON 格式批量导入导出

#### 3. 连接测试

- **API 连通性检测**：配置保存前测试 Endpoint 是否可达
- **认证检测**：验证 API Key 是否有效
- **模型可用性检测**：确认该模型是否在账户中可用

#### 4. 密钥管理

- **安全存储**：API Key 加密存储，支持环境变量引用
- **密钥轮换**：支持更新 API Key 而不中断服务
- **密钥隔离**：不同模型使用不同 Key，降低泄露风险

### API 接口设计

```
GET    /api/config                    # 获取所有配置
GET    /api/config/models             # 获取模型配置
GET    /api/config/models/:type       # 获取指定类型模型配置
PUT    /api/config/models/:type       # 更新模型配置
POST   /api/config/models/:type/test  # 测试模型连接
GET    /api/config/environments       # 获取所有环境
PUT    /api/config/environments/:env  # 切换当前环境
POST   /api/config/export             # 导出配置
POST   /api/config/import             # 导入配置
```

### 界面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  配置管理平台                                    [环境: 生产环境 ▼] │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │   LLM      │ │   Vision   │ │   Image    │ │    TTS     │    │
│  │  GPT-4o    │ │  GPT-4V    │ │  DALL·E 3  │ │ ElevenLabs │    │
│  │  ● 在线    │ │  ● 在线    │ │  ● 在线    │ │  ● 在线    │    │
│  │  [配置]    │ │  [配置]    │ │  [配置]    │ │  [配置]    │    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
│                                                                   │
│  ┌────────────┐ ┌────────────┐                                   │
│  │   Video    │ │  Database  │                                   │
│  │  Runway    │ │  PostgreSQL│                                   │
│  │  ● 在线    │ │  ● 在线    │                                   │
│  │  [配置]    │ │  [配置]    │                                   │
│  └────────────┘ └────────────┘                                   │
├──────────────────────────────────────────────────────────────────┤
│  [导入配置]  [导出配置]  [添加模型]  [环境设置]                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 五、详细工作流程

### 第一阶段：需求解析与方案设计

**用户输入示例**：
> "我想写一篇关于防晒霜的小红书，有这三张产品图，要夏日清新风，突出肤感轻薄不油腻。"

**处理步骤**：

1. 图像理解 Agent（使用配置的 Vision 模型）分析三张图，提取产品包装视觉、使用场景
2. 文本理解 Agent（使用配置的 LLM 模型）提炼关键需求
3. Planner 生成内容方案（推送给用户可选确认）：
   - 标题备选
   - 正文大纲
   - 配图计划：产品图×1、成分特写×1、使用场景摆拍×1、前后对比示意×1
   - 风格调性参考描述

---

### 第二阶段：多模态并行生成

Orchestrator 拆解任务，并行调用：

1. 文本 Agent（使用配置的 LLM 模型）写多个标题和正文
2. 图像 Agent（使用配置的 Image 模型）根据方案和参考图风格，生成 3 张配图（用文生图+图生图 ControlNet 维持产品一致性）
3. 若需视频，将文案转为视频脚本，生成 15 秒护肤品展示视频，并调用语音 Agent（使用配置的 TTS 模型）生成旁白
4. 所有产物返回后，融合组装为完整笔记

---

### 第三阶段：反馈与迭代

**用户反馈示例**：
> "第三张图改成卡通风格，标题不够吸引人，正文里'清爽'提到 3 次有点多。"

**Critic 解析反馈**：

1. 只调度图像 Agent 重新生成第三张图，保持其他不变
2. 只调度文本 Agent 修改标题（基于前两个标题进行变异），并在正文中降低"清爽"频率
3. 其余内容原样保留

再次组装展示，直到用户满意。

---

### 第四阶段：发布/导出

用户点击发布，可选：
- 模拟发布流程（检查格式、尺寸）
- 直接通过小红书开放 API（若未来有）发布
- 导出素材包供手动上传

---

## 六、技术选型建议

| 层面 | 工具/框架 | 理由 |
|------|----------|------|
| Agent 编排 | LangGraph (Python/JS) | 支持有状态图、人机交互、版本管理，非常适合循环迭代 |
| 后端框架 | FastAPI + Celery | 异步任务队列处理音视频生成等长耗时任务 |
| 配置 UI 后端 | FastAPI | 提供配置管理 RESTful API |
| 配置 UI 前端 | React 19 + Tailwind CSS 4 | 配置管理界面 |
| LLM 基座 | 可配置（GPT-4o / Claude / DeepSeek 等） | 通过配置中心灵活切换 |
| 图像模型 | 可配置（DALL·E 3 / SDXL / Adobe Firefly 等） | 通过配置中心灵活切换 |
| 语音 | 可配置（ElevenLabs / Azure TTS / MiniMax 等） | 通过配置中心灵活切换 |
| 视频生成 | 可配置（Runway / Pika / 自研等） | 通过配置中心灵活切换 |
| 向量&记忆 | Chroma + PostgreSQL | 轻量易集成 |
| 前端 | Next.js + WebSocket | 对话式 UI + 多版本卡片预览 |

---

## 七、关键难点与解决方案

### Q1: 如何保证修改时只动局部，不影响整体？

**方案**：
- 将每个生成单位（标题、段落、每张图片）视为独立模块，拥有唯一 ID
- 修改指令解析到具体模块 ID，只重新生成该模块，并替换

---

### Q2: 多图片/视频中产品外观保持一致性

**方案**：
- 先用图像理解 Agent 提取产品核心视觉描述（颜色、形状、Logo），作为固定 prompt 贯穿所有图像生成任务
- 可用 IP-Adapter / InstantID 后的产品一致性方案，将产品图作为参考图嵌入

---

### Q3: 迭代次数过多导致 Token 成本高

**方案**：
- 设置最大修改轮次（如 5 轮）
- 优化 prompt 缓存，系统指令和风格要求可以固定前缀缓存
- 对非核心生成任务切换到更便宜的模型（通过配置中心调整）

---

### Q4: 多 Agent 并发调度的状态管理

**方案**：
- LangGraph 天然支持带状态的图，每一步的输出都可以持久化到数据库
- 任务失败可重试某个节点而不影响整体

---

### Q5: 如何实现模型配置的可扩展性？

**方案**：
- 配置中心采用插件化设计，新增模型只需在配置中添加 Provider 定义
- 支持自定义 Provider（需提供 API URL 模板和认证方式）
- 配置界面动态渲染表单，支持自定义参数

---

## 八、部署与扩展性

- 所有 Agent 可作为可插拔模块，通过一个注册中心管理，方便后续接入新模型（如 Sora 正式版）
- **模型网关层**做统一鉴权、限流、成本监控、Fallback 策略（配置中心定义的 fallback 自动生效）
- 前端提供"版本历史"功能，用户可随时找回之前的某一版文案
- 配置管理 UI 支持多租户隔离，可为不同用户/团队配置不同的模型组合

---

## 九、数据结构

### Brief (需求结构)

```json
{
  "goal": "种草/教程/测评",
  "style": "活泼/专业/治愈",
  "keywords": ["关键词1", "关键词2"],
  "reference_images": ["url1", "url2"],
  "image_style": "摄影实拍/插画/3D",
  "need_video": true,
  "need_voiceover": true,
  "bgm_preference": "轻快/舒缓"
}
```

### Note (最终笔记结构)

```json
{
  "title": "标题",
  "sections": [
    { "id": "s1", "type": "headline", "content": "..." },
    { "id": "s2", "type": "paragraph", "content": "..." }
  ],
  "images": [
    { "id": "img1", "url": "...", "description": "..." },
    { "id": "img2", "url": "...", "description": "..." }
  ],
  "video": { "url": "...", "duration": "15s" },
  "audio": { "url": "...", "voice": "温柔女声" },
  "tags": ["#标签1", "#标签2"],
  "version": 1
}
```

### ModelConfig (模型配置结构)

```json
{
  "provider": "openai",
  "api_url": "https://api.openai.com/v1",
  "model_name": "gpt-4o",
  "api_key": "${OPENAI_API_KEY}",
  "enabled": true,
  "is_primary": true,
  "default_params": {
    "temperature": 0.7,
    "max_tokens": 4096,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
  },
  "timeout": 60,
  "retry_count": 3
}
```

### EnvironmentConfig (环境配置结构)

```json
{
  "name": "production",
  "description": "生产环境",
  "is_active": true,
  "models": {
    "llm": { ... },
    "vision": { ... },
    "image_generation": { ... },
    "tts": { ... },
    "video": { ... }
  }
}
```
