# Redbook Studio 画板与画板Agent

小红书 AI 创作工作平台的**画板（Canvas）**和**画板Agent（CanvasAgent）**详细文档。

---

## 概述

**Redbook Studio** 的画板系统是一个可视化的内容编辑画布，配合画板Agent实现AI辅助创作。

### 核心组件

| 组件 | 说明 |
|------|------|
| **Canvas 画板** | 可视化编辑画布，管理内容元素（文本、图片、视频等） |
| **CanvasAgent 画板Agent** | AI辅助创作Agent，基于ReAct循环模式 |

### 设计原则

**用户主导，AI辅助**
- 用户是创作者，Agent只是辅助工具
- 所有操作必须等待用户明确指令
- 不主动修改任何内容
- 当用户要求画图时，立即开始绘制直到完成

---

## 画板 Canvas

### 核心职责

1. **状态管理** - 管理画板元素（增删改查）
2. **操作引擎** - 执行操作并记录历史
3. **撤销/重做** - 支持操作回溯
4. **选择管理** - 管理选中区域
5. **快照生成** - 生成画布状态快照

### 元素类型 (ElementType)

| 类型 | 说明 | 支持的操作 |
|------|------|-----------|
| `TEXT` | 文本元素 | 移动、缩放、旋转、文本编辑 |
| `IMAGE` | 图片元素 | 移动、缩放、旋转、裁剪 |
| `VIDEO` | 视频元素 | 移动、缩放、旋转 |
| `AUDIO` | 音频元素 | 移动、缩放 |
| `SHAPE` | 形状元素 | 移动、缩放、旋转、样式 |
| `GROUP` | 组合元素 | 整体移动、缩放、锁定 |
| `DRAWING` | 绘画元素 | SVG路径绘制、变换 |

### 操作类型 (OperationType)

| 操作 | 说明 |
|------|------|
| `CREATE` | 创建新元素 |
| `DELETE` | 删除元素（自动处理组合子元素） |
| `UPDATE` | 更新元素属性 |
| `MOVE` | 移动元素位置 |
| `RESIZE` | 调整元素尺寸 |
| `ROTATE` | 旋转元素 |
| `STYLE` | 修改样式 |
| `GROUP` | 组合多个元素 |
| `UNGROUP` | 取消组合 |
| `DUPLICATE` | 复制元素 |
| `ALIGN` | 对齐元素 |
| `TEXT_EDIT` | 编辑文本内容 |
| `LASSO_SELECT` | 自由框选 |
| `ELEMENT_SELECT` | 元素选择 |

### 数据结构

#### CanvasElement

```python
@dataclass
class CanvasElement:
    id: str                           # 唯一标识符
    type: str                         # 元素类型 (text/image/video/audio/shape/group/drawing)
    position: Dict[str, float]        # 位置 {"x": 0, "y": 0}
    size: Dict[str, float]           # 尺寸 {"width": 100, "height": 100}
    z_index: int = 0                 # 层级（数值越大越靠前）
    locked: bool = False              # 是否锁定
    visible: bool = True              # 是否可见
    metadata: ElementMetadata         # 类型特定元数据
    styles: ElementStyles             # 通用样式
    created_by: str = "user"          # 创建者 (user/agent)
    parent_id: Optional[str] = None   # 父元素ID（组合用）
```

#### ElementMetadata

```python
@dataclass
class ElementMetadata:
    # 文本元素
    text_content: Optional[str] = None
    font_size: Optional[int] = None
    font_family: Optional[str] = None
    text_align: Optional[str] = None

    # 图片/视频元素
    url: Optional[str] = None
    local_path: Optional[str] = None
    duration: Optional[float] = None

    # 绘画专用属性
    stroke_color: Optional[str] = None  # 描边颜色
    stroke_width: Optional[float] = None  # 描边宽度
    fill_color: Optional[str] = None    # 填充颜色
    svg_path: Optional[str] = None      # SVG路径数据

    # 组合元素
    child_ids: Optional[List[str]] = None
```

#### ElementStyles

```python
@dataclass
class ElementStyles:
    # 位置与尺寸
    x: float = 0
    y: float = 0
    width: float = 100
    height: float = 100
    rotation: float = 0  # 旋转角度（度）

    # 外观
    fill: Optional[str] = None       # 填充色
    stroke: Optional[str] = None     # 边框色
    stroke_width: float = 1
    opacity: float = 1
    corner_radius: float = 0        # 圆角

    # 阴影
    shadow_enabled: bool = False
    shadow_color: Optional[str] = None

    # 特效
    blur: float = 0
    brightness: float = 1
    contrast: float = 1
```

#### CanvasSnapshot

```python
@dataclass
class CanvasSnapshot:
    canvas_id: str
    name: str = "Untitled"
    width: float = 1920
    height: float = 1080
    background_color: str = "#ffffff"
    elements: List[CanvasElement] = field(default_factory=list)
    operation_history: List[CanvasOperation] = field(default_factory=list)
    selection: Optional[SelectionRegion] = None
    timestamp: datetime = field(default_factory=datetime.now)
```

---

## 画板Agent CanvasAgent

### 核心原理

基于 **Mini-Agent** 的 **ReAct循环** 模式：

```
Think → Act → Observe → Think → ...
```

- **Think**: 调用LLM生成响应，决定下一步行动
- **Act**: 执行工具调用
- **Observe**: 观察工具执行结果

### Agent模式

| 模式 | 说明 | 可用工具 |
|------|------|----------|
| `DAILY` | 日常模式，轻松聊天 | canvas_understand |
| `PLANNING` | 规划模式，制定详细计划 | canvas_understand, canvas_planning |
| `WORKING` | 工作模式，执行计划 | 所有画布工具 |

### 模式切换流程

```
                    ┌─────────────┐
                    │   DAILY     │
                    │  (日常模式)  │
                    └──────┬──────┘
                           │
              ML路由检测到明确任务需求 (置信度≥0.7)
                           │
                           ▼
                    ┌─────────────┐
                    │  PLANNING   │
                    │  (规划模式)  │
                    │  制定执行计划 │
                    └──────┬──────┘
                           │
                    用户确认计划 ("好的，执行吧")
                           │
                           ▼
                    ┌─────────────┐
                    │  WORKING   │
                    │  (工作模式)  │
                    │  主动执行计划 │
                    └─────────────┘
```

### 工具集

#### 理解工具

| 工具 | 说明 |
|------|------|
| `CanvasUnderstandTool` | 理解画布状态和元素信息，返回结构化描述 |

#### 编辑工具

| 工具 | 说明 |
|------|------|
| `CanvasEditTool` | 编辑选中元素（位置、尺寸、样式等） |
| `CanvasGlobalEditTool` | 全局编辑操作 |
| `CanvasImageEditTool` | 图片编辑（裁剪、滤镜等） |

#### 绘制工具

| 工具 | 说明 |
|------|------|
| `CanvasDrawTool` | SVG路径绘制（自由曲线） |
| `CanvasShapeTool` | 预定义形状（星星、心形、三角形等） |
| `CanvasTransformTool` | 变换操作（旋转、镜像、缩放、复制） |

#### 操作工具

| 工具 | 说明 |
|------|------|
| `CanvasOperateTool` | 执行画布操作（移动、缩放等） |
| `CanvasSuggestTool` | AI辅助建议 |
| `CanvasUndoTool` | 撤销操作（橡皮擦功能） |
| `CanvasSnapshotTool` | 获取画布视觉快照 |

### 技能系统

基于YAML定义的技能框架，**渐进式披露**：

#### L1 - 目录级概要
```yaml
catalog_instruction: |
  在画板上绘制 SVG 路径图形，包括圆形、矩形、直线、曲线等。
  支持多路径一次性绘制完整图案。
```

#### L2 - 工具级概要
```yaml
# 技能激活后显示
## 工具说明
### canvas_draw
使用 SVG path 命令绘制自定义路径。
- operation: 固定为 "brush"
- params.path_data: SVG path 命令字符串
...
```

#### L3 - 完整指令
```yaml
prompt: |
  # canvas_draw 技能指令
  ## 坐标系统
  - y=0 在画布上方
  - 路径坐标基于选择区域边界
  ...
```

#### 内置技能

| 技能 | 说明 | 允许的工具 |
|------|------|------------|
| `canvas_understand` | 理解画布状态 | canvas_understand |
| `canvas_draw` | SVG自由曲线绘制 | canvas_draw, canvas_shape, canvas_transform, canvas_undo, canvas_snapshot, canvas_understand |
| `canvas_edit` | 编辑选中/框选内容 | canvas_edit, canvas_understand, canvas_snapshot |
| `canvas_undo` | 回撤绘制 | canvas_undo, canvas_snapshot, canvas_understand |
| `canvas_snapshot` | 获取画布视觉快照 | canvas_snapshot, canvas_understand |
| `canvas_planning` | 规划模式专用 | canvas_understand |

### 上下文构建

CanvasAgent通过`CANVAS_CONTEXT_TEMPLATE`构建上下文：

```python
CANVAS_CONTEXT_TEMPLATE = """
## 当前画板状态
- 画板ID: {canvas_id}
- 元素数量: {element_count}
- 当前选中: {selection_info}
- 可用操作: {available_operations}

## 选择区域边界（重要！）
绘制图案时，所有元素必须完全在以下边界内：
- X轴范围: {selection_x_start} 到 {selection_x_end}
- Y轴范围: {selection_y_start} 到 {selection_y_end}

## 行为准则
1. 等待指令：始终等待用户的明确指令
2. 确认理解：在执行操作前先确认理解是否正确
3. 简洁回复：用简洁的语言回复
4. 用户主导：如果用户只是随意操作，不要干预
"""
```

---

## 目录结构

```
studio/canvas/
├── __init__.py
├── canvas_agent.py          # CanvasAgent主逻辑
│                           # - ReAct循环 (think/act/observe)
│                           # - 模式切换 (DAILY/PLANNING/WORKING)
│                           # - 技能调度
├── canvas_core.py          # 画布核心
│                           # - 元素管理 (增删改查)
│                           # - 操作执行 (CREATE/DELETE/MOVE/...)
│                           # - 撤销/重做
├── canvas_prompt.py         # 系统提示词
│                           # - CANVAS_SYSTEM_PROMPT
│                           # - DAILY_SYSTEM_PROMPT
│                           # - PLANNING_SYSTEM_PROMPT
│                           # - WORKING_SYSTEM_PROMPT
├── mode_router.py          # ML+LLM混合路由
│                           # - 模式自动切换判断
├── canvas_storage.py        # 画布持久化
├── canvas_sync.py          # 画布同步
├── selection_extractor.py   # 框选提取
│                           # - LassoSelection
│                           # - SelectionRegion
│                           # - ExtractedContent
├── canvas_tools.py         # 工具定义
│                           # - CanvasUnderstandTool
│                           # - CanvasEditTool
│                           # - CanvasDrawTool
│                           # - ...
├── canvas_tool_result_store.py  # 工具结果存储
└── skills/                  # 技能系统
    ├── _registry.yaml       # 技能注册表
    ├── canvas_understand.yaml
    ├── canvas_draw.yaml     # SVG绘制技能
    ├── canvas_edit.yaml     # 编辑技能
    ├── canvas_undo.yaml     # 撤销技能
    ├── canvas_snapshot.yaml # 快照技能
    └── canvas_planning.yaml # 规划技能
```

---

## API接口

### 画布操作

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/canvas` | 创建画布 |
| `GET` | `/api/canvas/:id` | 获取画布 |
| `POST` | `/api/canvas/:id/operations` | 执行操作 |
| `GET` | `/api/canvas/:id/snapshot` | 获取快照 |
| `POST` | `/api/canvas/:id/undo` | 撤销 |
| `POST` | `/api/canvas/:id/redo` | 重做 |

### 画布Agent

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/canvas/:id/chat` | 与画布Agent对话 |
| `POST` | `/api/canvas/:id/mode` | 切换模式 |
| `GET` | `/api/canvas/:id/history` | 获取历史消息 |

---

## 数据存储

### 画布数据

```
data/studio/canvases/
├── canvases/
│   └── {canvas_id}.json   # 画布快照
└── metadata/
    └── index.json          # 元数据索引
```

### 工具结果归档

```
data/canvas_tool_results/
└── {canvas_id}/
    └── {timestamp}_{tool_name}.json  # 工具调用结果
```

### 画布元素JSON结构

```json
{
  "canvas_id": "canvas_001",
  "name": "我的画布",
  "width": 1920,
  "height": 1080,
  "background_color": "#ffffff",
  "elements": [
    {
      "id": "elem_001",
      "type": "text",
      "position": {"x": 100, "y": 200},
      "size": {"width": 300, "height": 50},
      "z_index": 1,
      "locked": false,
      "visible": true,
      "metadata": {
        "text_content": "Hello World",
        "font_size": 24,
        "color": "#333333"
      },
      "styles": {
        "fill": "#ffffff",
        "stroke": "#cccccc",
        "opacity": 1.0
      },
      "created_by": "user"
    }
  ],
  "selection": {
    "id": "sel_001",
    "type": "element",
    "bounds": {"x": 100, "y": 200, "width": 300, "height": 50},
    "element_ids": ["elem_001"]
  }
}
```

---

## 使用示例

### 1. 创建画布并添加元素

```python
from studio.canvas.canvas_core import CanvasCore, CanvasElement, ElementMetadata, ElementStyles

# 创建画布
canvas = CanvasCore(
    canvas_id="my_canvas",
    width=1920,
    height=1080
)

# 创建文本元素
text_elem = CanvasElement(
    id="text_001",
    type="text",
    position={"x": 100, "y": 100},
    size={"width": 300, "height": 50},
    metadata=ElementMetadata(text_content="Hello"),
    styles=ElementStyles(color="#333333", font_size=24),
    created_by="user"
)

# 添加到画布
await canvas.add_element(text_elem)
```

### 2. 执行画布操作

```python
from studio.canvas.canvas_core import CanvasOperation, OperationType

# 创建移动操作
op = CanvasOperation(
    id="op_001",
    type=OperationType.MOVE.value,
    target_ids=["text_001"],
    after_state={"delta": {"x": 50, "y": 0}}
)

# 执行操作
result = await canvas.execute_operation(op)
```

### 3. 使用CanvasAgent

```python
from studio.canvas.canvas_agent import CanvasAgent, CanvasSession

# 创建会话
session = CanvasSession(
    session_id="sess_001",
    canvas_id="my_canvas",
    user_id="user_001"
)

# 与Agent对话
result = await agent.chat(
    session=session,
    user_message="帮我画一个圆形"
)

print(result["message"])  # Agent的回复
print(result["agent_mode"])  # 当前模式
```

---

## 更新日志

- [2026-04-28] v1.1.0 - 完成画板Agent的ML+LLM混合路由
- [2026-04-27] v1.0.0 - 完成Canvas画布核心功能
- [2026-04-27] v0.9.0 - 完成Skill技能系统
- [2026-04-26] v0.5.0 - 完成CanvasAgent基础实现

---

*Last updated: 2026-05-28*
