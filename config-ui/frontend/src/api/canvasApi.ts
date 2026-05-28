// Canvas API client - 画板 CRUD 操作

const API_BASE = 'http://localhost:8080/api/canvas';

export interface ElementMetadata {
  text_content?: string;
  font_size?: number;
  font_family?: string;
  text_align?: string;
  line_height?: number;
  url?: string;
  local_path?: string;
  mime_type?: string;
  duration?: number;
  thumbnail_url?: string;
  waveform_data?: number[];
  shape_type?: string;
  // points 支持两种格式：[{x, y}, ...] 或 [[x, y], ...]
  points?: Array<{ x: number; y: number }> | number[][];
  child_ids?: string[];
  extra?: Record<string, any>;
  // 绘画专用属性
  stroke_color?: string;
  stroke_width?: number;
  fill_color?: string;
  drawing_paths?: Array<Record<string, any>>;
}

export interface ElementStyles {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  fill?: string;
  stroke?: string;
  stroke_width: number;
  opacity: number;
  corner_radius: number;
  shadow_enabled: boolean;
  shadow_color?: string;
  shadow_blur: number;
  shadow_offset_x: number;
  shadow_offset_y: number;
  blur: number;
  brightness: number;
  contrast: number;
  color?: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
}

export interface CanvasElement {
  id: string;
  type: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  z_index: number;
  locked: boolean;
  visible: boolean;
  metadata: ElementMetadata;
  styles: ElementStyles;
  created_by: 'user' | 'agent';
  created_at: string;
  updated_at: string;
  parent_id?: string;
}

export interface CanvasOperation {
  id: string;
  type: string;
  target_ids: string[];
  before_state: Record<string, any>;
  after_state: Record<string, any>;
  timestamp: string;
  creator: 'user' | 'agent';
  description: string;
}

export interface SelectionRegion {
  id: string;
  type: 'lasso' | 'rect' | 'element';
  bounds: { x: number; y: number; width: number; height: number };
  element_ids: string[];
  lasso?: {
    id: string;
    type: string;
    points: Array<{ x: number; y: number }>;
    closed: boolean;
  };
}

export interface CanvasSnapshot {
  canvas_id: string;
  elements: CanvasElement[];
  operation_history: CanvasOperation[];
  selection?: SelectionRegion;
  timestamp: string;
}

export interface CanvasSummary {
  canvas_id: string;
  name: string;
  element_count: number;
  thumbnail?: string;
  created_at: string;
  updated_at: string;
  created_by: 'user' | 'agent';
}

export interface CreateCanvasRequest {
  name?: string;
  width?: number;
  height?: number;
  background_color?: string;
}

export interface CreateCanvasResponse {
  success: boolean;
  canvas?: Canvas;
  error?: string;
}

export interface SaveCanvasResponse {
  success: boolean;
  canvas_id: string;
  saved_at: string;
  error?: string;
}

export interface LoadCanvasResponse {
  success: boolean;
  canvas?: Canvas;
  error?: string;
}

export interface ListCanvasesResponse {
  success: boolean;
  canvases: CanvasSummary[];
  total: number;
  error?: string;
}

export interface Canvas {
  canvas_id: string;
  name: string;
  elements: CanvasElement[];
  selection?: SelectionRegion;
  width: number;
  height: number;
  background_color: string;
  created_at: string;
  updated_at: string;
  created_by: 'user' | 'agent';
}

export const canvasApi = {
  // 创建画板
  async createCanvas(name: string = 'Untitled', width: number = 1920, height: number = 1080): Promise<CreateCanvasResponse> {
    const res = await fetch(`${API_BASE}/canvases`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        width,
        height,
      }),
    });
    return res.json();
  },

  // 保存画板
  async saveCanvas(canvasId: string): Promise<SaveCanvasResponse> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
    });
    return res.json();
  },

  // 加载画板
  async loadCanvas(canvasId: string): Promise<LoadCanvasResponse> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}`);
    if (!res.ok) {
      return {
        success: false,
        error: `Failed to load canvas: ${res.status}`,
      };
    }
    return res.json();
  },

  // 列出画板
  async listCanvases(limit: number = 100, offset: number = 0): Promise<ListCanvasesResponse> {
    const res = await fetch(`${API_BASE}/canvases?limit=${limit}&offset=${offset}`);
    return res.json();
  },

  // 删除画板
  async deleteCanvas(canvasId: string): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}`, {
      method: 'DELETE',
    });
    return res.json();
  },

  // 重命名画板
  async renameCanvas(canvasId: string, newName: string): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/rename`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    });
    return res.json();
  },

  // 复制画板
  async duplicateCanvas(canvasId: string): Promise<{ success: boolean; canvas?: Canvas; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/duplicate`, {
      method: 'POST',
    });
    return res.json();
  },

  // 导出画板
  async exportCanvas(canvasId: string, format: 'json' | 'png' | 'svg' = 'json'): Promise<Blob> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/export?format=${format}`);
    return res.blob();
  },

  // 添加元素
  async addElement(
    canvasId: string,
    element: Omit<CanvasElement, 'id' | 'created_at' | 'updated_at'>
  ): Promise<{ success: boolean; element?: CanvasElement; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/elements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(element),
    });
    return res.json();
  },

  // 更新元素
  async updateElement(
    canvasId: string,
    elementId: string,
    updates: Partial<CanvasElement>
  ): Promise<{ success: boolean; element?: CanvasElement; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/elements/${elementId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    return res.json();
  },

  // 删除元素
  async deleteElements(
    canvasId: string,
    elementIds: string[]
  ): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/elements`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ element_ids: elementIds }),
    });
    return res.json();
  },

  // 批量保存元素（轻量级保存）
  async saveElements(
    canvasId: string,
    elements: CanvasElement[]
  ): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/elements/batch`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ elements }),
    });
    return res.json();
  },

  // 获取版本历史
  async getVersionHistory(
    canvasId: string
  ): Promise<{
    success: boolean;
    versions: Array<{ version: number; created_at: string; description: string }>;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/versions`);
    return res.json();
  },

  // 恢复到指定版本
  async restoreVersion(
    canvasId: string,
    version: number
  ): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/restore/${version}`, {
      method: 'POST',
    });
    return res.json();
  },

  // AI 聊天
  async chat(
    canvasId: string,
    message: string,
    messages: Array<{ role: string; content: string; timestamp?: string }> = [],
    selection?: {
      type: string;
      bounds?: { x: number; y: number; width: number; height: number };
      element_ids?: string[];
      lasso?: {
        id: string;
        type: string;
        points: Array<{ x: number; y: number }>;
        closed: boolean;
      };
    },
    sessionId?: string,
    imageUrls?: string[]
  ): Promise<{
    success: boolean;
    message?: string;
    actions?: Array<any>;
    elements?: CanvasElement[];
    session_id?: string;
    agent_mode?: string;  // agent 当前模式: daily, planning, working
    needs_confirm?: boolean;  // 是否需要用户确认模式切换
    confirm_type?: string;  // 确认类型: planning, working
    route_confidence?: number;  // 路由置信度
    route_reason?: string;  // 路由原因
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, messages, selection, session_id: sessionId, image_urls: imageUrls }),
    });
    return res.json();
  },

  // 确认模式切换
  async confirmModeSwitch(
    canvasId: string,
    sessionId: string,
    targetMode: string  // "planning" | "working"
  ): Promise<{
    success: boolean;
    agent_mode?: string;
    message?: string;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/confirm-mode-switch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, target_mode: targetMode }),
    });
    return res.json();
  },

  // 上传图片到 OSS（用于获取公开 URL）
  async uploadImage(file: File): Promise<{
    success: boolean;
    filename: string;
    url: string;
    content_type: string;
    size: number;
    error?: string;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('http://localhost:8080/api/studio/materials/upload', {
        method: 'POST',
        body: formData,
      });
      return res.json();
    } catch (error) {
      return {
        success: false,
        filename: '',
        url: '',
        content_type: '',
        size: 0,
        error: String(error),
      };
    }
  },

  // 清理画板 - 归档工具记录并清空短期存储
  async cleanupCanvas(canvasId: string, archiveAll: boolean = true): Promise<{
    success: boolean;
    archive_paths?: string[];
    record_count?: number;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/cleanup?archive_all=${archiveAll}`, {
      method: 'POST',
    });
    return res.json();
  },

  // 重置绘图会话
  async resetDrawingSession(canvasId: string): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/drawing-session/reset`, {
      method: 'POST',
    });
    return res.json();
  },

  // 获取画板的归档历史列表
  async listCanvasArchives(canvasId: string): Promise<{
    success: boolean;
    archives: Array<{
      archive_path: string;
      archive_name: string;
      record_count: number;
      drawing_session_id?: string;
    }>;
    total: number;
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/archives`);
    return res.json();
  },

  // 获取指定图案会话的完整绘制数据
  async getDrawingBySession(canvasId: string, drawingSessionId: string): Promise<{
    success: boolean;
    records: any[];
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/drawings/${drawingSessionId}`);
    return res.json();
  },

  // 从归档恢复指定图案到当前会话
  async restoreDrawing(canvasId: string, drawingSessionId: string, archivePath: string): Promise<{
    success: boolean;
    record_count?: number;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/canvases/${canvasId}/drawings/${drawingSessionId}/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archive_path: archivePath }),
    });
    return res.json();
  },
};
