# Canvas Agent 绘制定位问题分析

## 问题现象
Agent 绘制小猪佩奇时，各图形组合没有意义，位置不正确。

## 问题分析

### 从日志提取的关键数据

**选择区域**：中心点在 `x=756.5, y=447.3`
- 区域范围: x=481, y=125, width=551, height=644

**Agent 绘制调用记录**：
| 步骤 | 操作 | offset参数 | 实际位置 |
|------|------|-----------|----------|
| 1 | 身体 (ellipse) | offset_y: 0.2 | y: 382.93 |
| 2 | 头部 (ellipse) | offset_y: -0.35 | y: 60.93 |
| 3 | 左眼 (circle) | offset_x: -0.15, offset_y: -0.2 | x: 651.81, y: 296.49 |
| 4 | 右眼 (circle) | offset_x: 0.15, offset_y: -0.2 | x: 817.11, y: 296.49 |

### 核心问题

**offset 是相对于"选择区域中心"计算的，不是相对于"上一个元素"！**

```
选择区域中心: x=756.5, y=447.3
      ↓
Agent 说 offset_x: -0.15 (左眼)
      ↓
实际计算: 756.5 + 551*(-0.15) = 756.5 - 82.65 = 673.85 ≈ 651.81 (相对于选择区域)
      ↓
但头部实际位置: x=618.75
所以眼睛并没有在头部上！
```

Agent 制定的计划是正确的（先画身体、再画头部、最后画眼睛），但 offset 的计算基准错误，导致各元素无法正确组合。

---

## 解决方案对比

| 方案 | 准确性 | 复杂度 | 说明 |
|------|--------|--------|------|
| 1. Agent计算绝对坐标 | 中 | 低 | Agent需理解复杂换算，仍易出错 |
| 2. 工具支持绝对定位 | 高 | 低 | Agent直接指定位置，不依赖offset |
| 3. 相对定位（参考元素） | 最高 | 中 | "画在xxx上方"比"y坐标减100"更直观 |

### 推荐方案：方案2 + 方案3 混合

**新增参数**：
```python
# 绝对定位（可选）
position_x: float  # 元素左上角 X 坐标
position_y: float  # 元素左上角 Y 坐标

# 或相对定位（推荐）
reference_element_id: str  # 参考元素 ID
relative_position: str     # "above" | "below" | "left_of" | "right_of" | "centered_on"
offset_x: float           # 额外微调
offset_y: float
```

**Agent 使用示例**：
```
步骤1: 画身体 → 返回 {element_id: "body", bounds: {x: 591, y: 382, width: 330, height: 386}}
步骤2: 画头部 → reference_element_id: "body", relative_position: "above", scale: 0.5
步骤3: 画左眼 → reference_element_id: "head", relative_position: "left_of", offset_x: -0.15
```

**工具内部处理逻辑**：
1. 如果指定了 `position_x`, `position_y`，直接使用绝对坐标
2. 如果指定了 `reference_element_id`，从 `_recent_elements` 查找该元素
3. 根据 `relative_position` 计算相对于参考元素的位置
4. 应用 `offset_x`, `offset_y` 进行微调

**优点**：
1. Agent 不需要计算复杂的绝对坐标
2. 语义化定位："画在头部上方"比"y=60"更直观
3. 自动处理位置计算，减少 Agent 出错可能

---

## 其他可能问题

日志显示 Agent 的 offset 计算已经比较对称（眼睛 x: 651 vs x: 817，大致对称）。

**可能的其他问题**：
1. Agent 制定的"小猪佩奇"绘制计划本身不正确
2. 它可能不理解小猪佩奇各部分的位置关系
3. 需要优化 Agent 的绘图策略 prompt

---

## 待办事项

- [ ] 实现相对定位功能（reference_element_id + relative_position）
- [ ] 更新 canvas_draw 工具描述，引导 Agent 使用相对定位
- [ ] 考虑优化 Agent 的绘图策略 prompt
