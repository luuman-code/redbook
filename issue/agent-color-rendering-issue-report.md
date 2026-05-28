# Agent 绘制图案颜色异常问题调查报告

**日期**: 2026-05-22
**问题**: Agent 绘制完成后颜色显示为灰色，但控制台日志显示颜色参数正确

---

## 1. 问题概述

### 1.1 现象描述
- **流式绘制时**: 图案颜色显示正常（绿色 #228B22）
- **绘制完成后**: 图案颜色显示为灰色 (#7F7F7F)
- **控制台日志**: 所有颜色参数（metadata.fill_color, styles.fill）均为正确值 #228B22

### 1.2 关键发现
通过浏览器开发者工具检查：
- DOM 属性 `fill="#228B22"` ✓ 正确
- Computputed Style `fill: rgb(34, 139, 34)` ✓ 正确
- 截图拾取实际像素颜色 `rgb(127, 127, 127)` ✗ 灰色

**结论**: DOM 和 computed style 均正确，但实际渲染结果错误。

---

## 2. 数据流分析

### 2.1 后端绘制流程

```
execute_streaming()
  ├── 创建 CanvasElement，设置 colors
  │     ├── metadata.stroke_color = stroke_color
  │     ├── metadata.fill_color = fill_color
  │     ├── styles.stroke = stroke_color
  │     └── styles.fill = fill_color  ← 正确值
  │
  ├── send_complete() 发送 DRAW_COMPLETE
  │     └── 前端 onDrawComplete 收到正确数据
  │
  └── add_element() 添加到后端存储
        └── 问题可能在此阶段颜色被覆盖
```

### 2.2 前端渲染流程

```
DRAW_COMPLETE 消息
  └── setElements([...]) 添加元素
        └── React 重新渲染 CanvasElement 组件

CANVAS_UPDATE 消息 (auto-save 触发)
  └── setElements(data.elements) 覆盖整个数组
        └── 问题：后端返回的数据中 fill 可能已被修改
```

### 2.3 关键代码位置

| 文件 | 行号 | 代码 |
|-----|------|-----|
| canvas_tools.py | 1613 | `fill=fill_color` 设置 |
| canvas_tools.py | 1795 | `send_complete()` 发送 |
| canvas_routes.py | 713-722 | CANVAS_UPDATE 广播 |
| CanvasWorkspace.tsx | 85 | `setElements(data.elements)` 覆盖 |
| CanvasElement.tsx | 402 | SVG path 渲染 `fill={metadata.fill_color \|\| fill \|\| 'none'}` |

---

## 3. 前端渲染组件对比

### 3.1 流式绘制渲染 (CanvasWorkspace.tsx:1380-1403)

```tsx
<svg
  className="absolute pointer-events-none"
  style={{ left: data.x, top: data.y, overflow: 'visible' }}
>
  <path
    fill={data.fill_color || 'none'}
    stroke={data.stroke_color}
    opacity={0.9}
  />
</svg>
```

**特点**:
- 无 viewBox，使用绝对坐标
- 直接定位在画布上

### 3.2 CanvasElement 渲染 (CanvasElement.tsx:395-411)

```tsx
<svg
  width="100%"
  height="100%"
  viewBox={`0 0 ${size.width} ${size.height}`}
  style={{ overflow: 'visible' }}
>
  <path
    fill={metadata.fill_color || fill || 'none'}
    stroke={metadata.stroke_color || stroke}
  />
</svg>
```

**特点**:
- 有 viewBox，使用缩放坐标
- 坐标受 viewBox 裁切影响

### 3.3 两者核心差异

| 特性 | 流式绘制 | CanvasElement |
|-----|---------|--------------|
| viewBox | 无 | 有 |
| 坐标系统 | 绝对坐标 | viewBox 缩放 |
| opacity | 0.9 | 无 |

---

## 4. 调试日志位置

### 4.1 后端日志文件

| 文件 | 路径 | 内容 |
|-----|------|-----|
| studio_debug_20260522.log | data/logs/ | 运行时日志 |
| color_debug.log | data/logs/ | 颜色调试日志 |

### 4.2 前端控制台日志

| 前缀 | 来源 | 触发时机 |
|-----|------|---------|
| `[CanvasWS]` | CanvasWorkspace.tsx | WebSocket 消息 |
| `[Canvas]` | CanvasWorkspace.tsx | DRAW_COMPLETE 回调 |
| `[CanvasElement]` | CanvasElement.tsx | 组件渲染 |

---

## 5. 已执行的修复

### 5.1 Canvas 2D 填充修复

**文件**: `config-ui/frontend/src/pages/CanvasWorkspace.tsx`

**问题**: 绘制完成时使用 Canvas 2D 渲染，但没有调用 `ctx.fill()`

**修复**:
```typescript
// 修改前
ctx.stroke();

// 修改后
ctx.stroke();
if (fill && fill !== 'none') {
  ctx.fill();
}
```

### 5.2 fill 默认值修复

**文件**: `config-ui/frontend/src/pages/CanvasWorkspace.tsx`

**问题**: `fill` 变量没有默认值，可能导致渲染异常

**修复**:
```typescript
// 修改前
const fill = element.styles.fill;

// 修改后
const fill = element.styles.fill || 'none';
```

### 5.3 调试日志增强

**文件**: `config-ui/frontend/src/components/canvas/CanvasElement.tsx`

**添加日志**:
```typescript
console.log('[CanvasElement] position:', element.position);
console.log('[CanvasElement] size:', element.size);
```

---

## 6. 待排查问题

### 6.1 CANVAS_UPDATE 覆盖问题

**现象**: `handleCanvasUpdate` 中的 `setElements(data.elements)` 可能用后端数据覆盖前端正确数据

**排查方向**:
1. 后端 `canvas.elements` 存储的元素 `styles.fill` 值是否为 #000000？
2. `add_element` 到 `CANVAS_UPDATE` 广播之间发生了什么？

**建议**: 在 `handleCanvasUpdate` 中添加详细日志：
```typescript
if (data?.elements) {
    console.log('[CanvasWS] handleCanvasUpdate - 1st element styles.fill:',
        data.elements[0]?.styles?.fill);
    setElements(data.elements);
}
```

### 6.2 浏览器渲染异常

**现象**: DOM 和 computed style 均正确，但实际像素显示灰色

**可能原因**:
1. GPU 加速导致 SVG 渲染合成错误
2. CSS 样式覆盖（需检查是否有 CSS 规则影响）
3. SVG filter 或 mask 影响

**建议排查**:
1. 禁用浏览器 GPU 加速测试
2. 检查是否有 CSS 规则覆盖 fill 属性
3. 在 Elements 面板的 Styles 面板中检查完整样式来源

---

## 7. 测试建议

### 7.1 复现步骤

1. 启动前后端服务器
2. 打开前端画布页面
3. 使用 Agent 发送绘制指令
4. 在绘制过程中观察 `streamingElements` 渲染
5. 绘制完成后立即检查控制台日志

### 7.2 检查清单

- [ ] `[Canvas]` 日志中 `styles.fill` 值
- [ ] `[CanvasElement]` 日志中 `metadata.fill_color` 值
- [ ] DOM 中 path 元素的 `fill` 属性
- [ ] Computed style 中 `fill` 值
- [ ] 实际截图像素颜色
- [ ] SVG 元素的 `viewBox` 和 path 坐标是否匹配

### 7.3 快速验证命令

```javascript
// 检查所有 path 的 fill 属性
document.querySelectorAll('svg path').forEach(p => {
    const fill = p.getAttribute('fill');
    const computed = window.getComputedStyle(p).fill;
    console.log('fill:', fill, 'computed:', computed);
});

// 检查 SVG 及其父元素样式
document.querySelectorAll('svg path').forEach(p => {
    let el = p;
    while (el && el.tagName !== 'BODY') {
        const style = window.getComputedStyle(el);
        console.log(el.tagName, 'filter:', style.filter);
        el = el.parentElement;
    }
});
```

---

## 8. 总结

### 8.1 问题定位

当前证据表明：
1. **数据层面**: 前后端传递的 `fill` 值是正确的 #228B22
2. **DOM 层面**: path 元素的 `fill` 属性和 computed style 均正确
3. **渲染层面**: 实际像素显示灰色

**可能结论**: 这是浏览器渲染层面的问题，不是代码逻辑问题。

### 8.2 下一步行动

1. **优先**: 在 `handleCanvasUpdate` 中添加日志，确认 CANVAS_UPDATE 是否覆盖了正确数据
2. **备选**: 禁用 GPU 加速测试，确认是否是浏览器合成问题
3. **备选**: 检查是否有 CSS 规则影响 SVG 渲染

---

**报告生成时间**: 2026-05-22
