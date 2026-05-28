"""
API Schemas - Pydantic 模型定义
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MaterialInput(BaseModel):
    """素材输入"""
    type: str = Field(..., description="素材类型: image/video/audio/text")
    url: Optional[str] = Field(None, description="素材 URL")
    content: Optional[str] = Field(None, description="base64 编码内容")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    user_input: str = Field(..., description="用户输入")
    materials: List[MaterialInput] = Field(default_factory=list, description="素材列表")
    user_context: Dict[str, Any] = Field(default_factory=dict, description="用户上下文")
    auto_generate: bool = Field(default=False, description="是否自动生成内容（跳过方案确认步骤）")


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    success: bool
    session_id: Optional[str] = None
    brief_id: Optional[str] = None
    plan_id: Optional[str] = None
    messages: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class GenerateRequest(BaseModel):
    """生成请求"""
    session_id: str = Field(..., description="会话 ID")


class GenerateResponse(BaseModel):
    """生成响应"""
    success: bool
    session_id: str
    items_count: int = 0
    messages: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class FeedbackRequest(BaseModel):
    """反馈请求"""
    session_id: str = Field(..., description="会话 ID")
    user_feedback: str = Field(..., description="用户反馈")


class FeedbackResponse(BaseModel):
    """反馈响应"""
    success: bool
    session_id: str
    iteration_count: int = 0
    modified_items_count: int = 0
    messages: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class PublishRequest(BaseModel):
    """发布请求"""
    session_id: str = Field(..., description="会话 ID")
    method: str = Field("simulate", description="发布方式: simulate/export/api")


class PublishResponse(BaseModel):
    """发布响应"""
    success: bool
    session_id: str
    method: str
    messages: List[str] = Field(default_factory=list)
    exported_content: Optional[str] = Field(None, description="导出包路径")
    error: Optional[str] = None


class ContentItemSchema(BaseModel):
    """内容项 schema"""
    item_id: str
    item_type: str
    content: str = ""
    metadata: Dict[str, Any] = {}
    status: str
    generation_prompt: str = ""
    position: int = 0
    local_path: Optional[str] = None


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    status: str
    current_version: int
    brief: Dict[str, Any] = {}
    plan: Optional[Dict[str, Any]] = None
    items: List[ContentItemSchema] = []
    created_at: datetime
    updated_at: datetime
    versions: List[Dict[str, Any]] = []
    messages: List[Dict[str, Any]] = []
    metadata: Optional[Dict[str, Any]] = {}


class ReviewResponse(BaseModel):
    """审核响应"""
    passed: bool
    score: float
    issues: List[Dict[str, Any]] = []
    suggestions: List[str] = []
    overall_comment: str


class GeneratePlansRequest(BaseModel):
    """生成多方案请求"""
    session_id: str = Field(..., description="会话 ID")
    plan_count: int = Field(3, description="生成的方案数量")
    style_variations: Optional[List[str]] = Field(None, description="风格变体列表")


class GeneratePlansResponse(BaseModel):
    """生成多方案响应"""
    success: bool
    session_id: str
    plans: List[Dict[str, Any]] = Field(default_factory=list, description="方案列表")
    messages: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class ChatRequest(BaseModel):
    """聊天消息请求"""
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户消息")
    materials: List[MaterialInput] = Field(default_factory=list, description="素材列表")


class ChatResponse(BaseModel):
    """聊天消息响应"""
    success: bool
    session_id: str
    message_id: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    plan_data: Optional[Dict[str, Any]] = None  # 方案数据
    error: Optional[str] = None


class AgentChatRequest(BaseModel):
    """Agent 专用聊天请求（无需预先创建会话）"""
    message: str = Field(..., description="用户消息")
    materials: List[MaterialInput] = Field(default_factory=list, description="素材列表")


class AgentChatResponse(BaseModel):
    """Agent 专用聊天响应"""
    success: bool
    session_id: Optional[str] = None
    messages: List[str] = Field(default_factory=list)
    plan_data: Optional[Dict[str, Any]] = None  # 完整方案数据，与前端 UI 一致
    preview_image_url: Optional[str] = None  # Agent 生成的预览图 URL
    preview_title: Optional[str] = None  # Agent 生成的预览标题
    preview_text_sections: Optional[List[Dict[str, Any]]] = None  # Agent 生成的预览文本
    error: Optional[str] = None


class TextSectionPreview(BaseModel):
    """文案片段预览"""
    section_id: str
    section_type: str
    content: str = ""
    content_words: int = 0


class PreviewTextResponse(BaseModel):
    """预览文案响应"""
    success: bool
    title: str = ""
    text_sections: List[TextSectionPreview] = Field(default_factory=list)
    error: Optional[str] = None


class PreviewTemplateResponse(BaseModel):
    """预览模板响应"""
    success: bool
    preview_image_url: Optional[str] = None
    error: Optional[str] = None
