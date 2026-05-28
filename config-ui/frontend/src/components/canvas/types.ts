// Tool Types for Canvas

export type BaseTool =
  | 'select'           // 元素选择（点击选中）
  | 'lasso'            // 自由框选（套索）
  | 'rect_select'      // 矩形框选
  | 'pan'              // 画板平移
  | 'text'             // 文本工具
  | 'shape'            // 形状工具
  | 'image'            // 图片工具
  | 'pen'              // 自由绘制
  | 'eraser'           // 橡皮擦
  | 'smart_crop'       // 智能截取
  | 'group_edit';      // 组合编辑（圈住组合解锁编辑）

export type AITool = 'smart_select' | 'ai_generate' | 'ai_edit' | 'ai_transform' | 'ai_suggest';

export type ToolType = BaseTool | AITool;

// Tool category for grouping in toolbar
export interface ToolCategory {
  id: string;
  name: string;
  tools: ToolDefinition[];
}

export interface ToolDefinition {
  id: ToolType;
  icon: string;
  label: string;
  shortcut?: string;
}

// Predefined tool categories
export const TOOL_CATEGORIES: ToolCategory[] = [
  {
    id: 'basic',
    name: '基础工具',
    tools: [
      { id: 'select', icon: 'cursor', label: '选择', shortcut: 'V' },
      { id: 'lasso', icon: 'lasso', label: '套索', shortcut: 'L' },
      { id: 'rect_select', icon: 'rect', label: '矩形选择', shortcut: 'R' },
      { id: 'pan', icon: 'hand', label: '平移', shortcut: 'H' },
      { id: 'group_edit', icon: 'group_edit', label: '组合编辑', shortcut: 'X' },
    ],
  },
  {
    id: 'creation',
    name: '创作工具',
    tools: [
      { id: 'text', icon: 'text', label: '文本', shortcut: 'T' },
      { id: 'shape', icon: 'shape', label: '形状', shortcut: 'S' },
      { id: 'image', icon: 'image', label: '图片', shortcut: 'I' },
      { id: 'pen', icon: 'pen', label: '画笔', shortcut: 'P' },
      { id: 'eraser', icon: 'eraser', label: '橡皮擦', shortcut: 'E' },
    ],
  },
  {
    id: 'ai',
    name: 'AI工具',
    tools: [
      { id: 'smart_select', icon: 'smart', label: '智能选择', shortcut: 'W' },
      { id: 'ai_generate', icon: 'generate', label: 'AI生成', shortcut: 'G' },
      { id: 'ai_edit', icon: 'edit', label: 'AI编辑', shortcut: 'K' },
      { id: 'ai_transform', icon: 'transform', label: 'AI变换', shortcut: 'U' },
      { id: 'ai_suggest', icon: 'suggest', label: 'AI建议', shortcut: 'A' },
      { id: 'smart_crop', icon: 'crop', label: '智能截取', shortcut: 'C' },
    ],
  },
];
