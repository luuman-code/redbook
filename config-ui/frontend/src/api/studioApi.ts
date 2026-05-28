// Studio API client

const API_BASE = 'http://localhost:8080/api/studio';

export interface Material {
  type: 'image' | 'video' | 'audio' | 'text';
  url?: string;
  content?: string; // base64
}

export interface CreateSessionRequest {
  user_input: string;
  materials: Material[];
  user_context?: Record<string, any>;
  auto_generate?: boolean;
}

export interface ContentItem {
  item_id: string;
  item_type: 'title' | 'headline' | 'text' | 'hashtag' | 'cta' | 'image' | 'video' | 'audio' | 'composite';
  content: string;
  metadata: Record<string, any>;
  status: string;
  generation_prompt: string;
  position: number;
  local_path?: string;
}

export interface Brief {
  id: string;
  goal: string;
  style: string;
  keywords: string[];
  must_include: string[];
  image_style: string;
  need_video: boolean;
  need_voiceover: boolean;
  need_text: boolean;
  need_images: boolean;
  raw_input: string;
}

export interface ContentPlan {
  plan_id: string;
  brief_id: string;
  title: string;
  text_sections: Array<{
    section_id: string;
    section_type: string;
    content: string;
    content_words: number;
    priority: number;
    is_optional?: boolean;
  }>;
  image_plan?: {
    style: string;
    elements: string[];
    count: number;
    aspect_ratio?: string;
    color_scheme?: string;
    reference_image_ids?: string[];
  };
}

export interface Version {
  version_number: number;
  created_at: string;
  created_by: string;
  change_summary: string;
}

export interface Session {
  session_id: string;
  status: string;
  current_version: number;
  brief: Brief;
  plan: ContentPlan;
  items: ContentItem[];
  created_at: string;
  updated_at: string;
  versions: Version[];
  messages: ChatMessage[];
  metadata?: Record<string, any>;
}

export interface ChatMessage {
  message_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  message_type?: 'text' | 'plan' | 'content';
  metadata?: {
    suggested_actions?: string[];
    attachments?: Array<{
      type: string;
      url?: string;
      content?: string;
    }>;
    message_type?: 'text' | 'plan' | 'content';
    plan_data?: PlanData;
  };
}

export interface PlanData {
  plan_id: string;
  title: string;
  text_sections: Array<{
    section_id: string;
    section_type: string;
    content: string;
    content_words: number;
    priority: number;
    is_optional?: boolean;
  }>;
  image_plan?: {
    style: string;
    elements: string[];
    count: number;
    aspect_ratio?: string;
    color_scheme?: string;
    reference_image_ids?: string[];
  };
  video_plan?: any;
  audio_plan?: any;
  estimated_duration?: number;
  version?: number;
  metadata?: any;
}

export interface CreateSessionResponse {
  success: boolean;
  session_id?: string;
  brief_id?: string;
  plan_id?: string;
  messages?: string[];
  error?: string;
}

export interface GenerateResponse {
  success: boolean;
  session_id: string;
  items_count: number;
  messages?: string[];
  error?: string;
}

export interface ReviewResponse {
  passed: boolean;
  score: number;
  issues: Array<{
    type: string;
    severity: string;
    item_id: string;
    message: string;
  }>;
  suggestions: string[];
  overall_comment: string;
}

export interface FeedbackResponse {
  success: boolean;
  session_id: string;
  iteration_count: number;
  modified_items_count: number;
  messages?: string[];
  error?: string;
}

export const studioApi = {
  // 列出所有会话
  async listSessions(): Promise<{
    sessions: Array<{
      session_id: string;
      status: string;
      current_version: number;
      brief: Brief;
      created_at: string;
      updated_at: string;
    }>;
    total: number;
  }> {
    const res = await fetch(`${API_BASE}/sessions`);
    return res.json();
  },

  // 创建新会话
  async createSession(request: CreateSessionRequest): Promise<CreateSessionResponse> {
    const res = await fetch(`${API_BASE}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return res.json();
  },

  // 确认方案
  async confirmPlan(sessionId: string): Promise<{
    success: boolean;
    session_id: string;
    messages?: string[];
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/confirm-plan`, {
      method: 'POST',
    });
    return res.json();
  },

  // 获取会话
  async getSession(sessionId: string): Promise<Session> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
    return res.json();
  },

  // 生成内容
  async generate(sessionId: string): Promise<GenerateResponse> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/generate`, {
      method: 'POST',
    });
    return res.json();
  },

  // 生成多个备选方案
  async generatePlans(
    sessionId: string,
    planCount: number = 3,
    styleVariations?: string[]
  ): Promise<{
    success: boolean;
    session_id: string;
    plans: ContentPlan[];
    messages: string[];
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/generate-plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        plan_count: planCount,
        style_variations: styleVariations,
      }),
    });
    return res.json();
  },

  // 审核内容
  async review(sessionId: string): Promise<ReviewResponse> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/review`);
    return res.json();
  },

  // 提交反馈
  async submitFeedback(sessionId: string, feedback: string): Promise<FeedbackResponse> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, user_feedback: feedback }),
    });
    return res.json();
  },

  // 发布
  async publish(sessionId: string, method: 'simulate' | 'export' | 'api' = 'simulate'): Promise<{
    success: boolean;
    session_id: string;
    method: string;
    messages: string[];
    exported_content?: string;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method }),
    });
    return res.json();
  },

  // 导出素材包
  async exportPackage(sessionId: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/export`);
    return res.blob();
  },

  // 获取版本历史
  async getVersionHistory(sessionId: string): Promise<{
    session_id: string;
    current_version: number;
    versions: Version[];
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/versions`);
    return res.json();
  },

  // 回退版本
  async rollback(sessionId: string, version: number): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/rollback/${version}`, {
      method: 'POST',
    });
    return res.json();
  },

  // 删除会话
  async deleteSession(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    return res.json();
  },

  // 获取指定版本的内容
  async getVersionContent(sessionId: string, version: number): Promise<{
    session_id: string;
    version_number: number;
    items: ContentItem[];
    plan: ContentPlan;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/versions/${version}/content`);
    return res.json();
  },

  // 从指定版本恢复
  async restoreVersion(sessionId: string, version: number): Promise<{
    success: boolean;
    session_id: string;
    restored_from_version: number;
    current_version: number;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/restore/${version}`, {
      method: 'POST',
    });
    return res.json();
  },

  // 上传文件替换内容项
  async uploadItemContent(
    sessionId: string,
    itemId: string,
    file: File
  ): Promise<{
    success: boolean;
    item_id: string;
    local_path: string;
    content: string;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(
      `${API_BASE}/sessions/${sessionId}/items/${itemId}/upload`,
      {
        method: 'POST',
        body: formData,
      }
    );
    return res.json();
  },

  // 上传素材文件（图片、视频、音频）
  async uploadMaterial(
    file: File
  ): Promise<{
    success: boolean;
    filename: string;
    url: string;
    content_type: string;
    size: number;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/materials/upload`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  // 更新内容项文本
  async updateItemContent(
    sessionId: string,
    itemId: string,
    content: string
  ): Promise<{
    success: boolean;
    item_id: string;
    content: string;
  }> {
    const res = await fetch(
      `${API_BASE}/sessions/${sessionId}/items/${itemId}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      }
    );
    return res.json();
  },

  // 发送聊天消息
  async chat(sessionId: string, message: string, materials?: Material[]): Promise<{
    success: boolean;
    session_id: string;
    message_id?: string;
    messages: any[];
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, materials }),
    });
    return res.json();
  },

  // 获取消息历史
  async getMessages(sessionId: string): Promise<{
    session_id: string;
    messages: ChatMessage[];
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
    return res.json();
  },

  // 直接与 Agent 对话（无需预创建会话）
  async agentChatNoSession(message: string, materials?: Material[]): Promise<{
    success: boolean;
    session_id?: string;
    messages: string[];
    plan_data?: PlanData;
    preview_image_url?: string;
    preview_title?: string;
    preview_text_sections?: any[];
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, materials }),
    });
    return res.json();
  },

  // 预览文案生成
  async previewText(
    sessionId: string,
    planData: any
  ): Promise<{
    success: boolean;
    title: string;
    text_sections: Array<{
      section_id: string;
      section_type: string;
      content: string;
      content_words: number;
    }>;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/preview-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_data: planData }),
    });
    return res.json();
  },

  // 预览模板渲染
  async previewTemplate(
    sessionId: string,
    textItems: any[],
    templateUrl: string
  ): Promise<{
    success: boolean;
    preview_image_url?: string;
    error?: string;
  }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/preview-template`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_items: textItems,
        template_url: templateUrl,
      }),
    });
    return res.json();
  },
};
