import React from 'react';

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
    content: string;  // 修复：添加缺失的 content 字段
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
  video_plan?: any;  // 添加完整字段
  audio_plan?: any;
  estimated_duration?: number;
  version?: number;
  metadata?: any;
}

interface ChatBubbleProps {
  message: ChatMessage;
}

const ChatBubble: React.FC<ChatBubbleProps> = ({
  message,
}) => {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  // 提取消息内容中的图片 URL
  const extractImageUrls = (content: string): string[] => {
    const urlRegex = /(https?:\/\/[^\s]+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s]*)?)/gi;
    const urls: string[] = [];
    let match;
    while ((match = urlRegex.exec(content)) !== null) {
      urls.push(match[1]);
    }
    return urls;
  };

  const contentImageUrls = extractImageUrls(message.content);

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[85%] px-4 py-3 rounded-2xl ${
          isUser
            ? 'bg-indigo-500 text-white rounded-tr-sm'
            : isSystem
            ? 'bg-amber-50 text-amber-800 border border-amber-200 rounded-tl-sm'
            : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm'
        }`}
      >
        {/* Role indicator for non-user messages */}
        {!isUser && !isSystem && (
          <div className="text-xs font-medium text-indigo-500 mb-1">AI 助手</div>
        )}

        {/* Message content */}
        <div className="text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>

        {/* Suggested actions */}
        {message.metadata?.suggested_actions && message.metadata.suggested_actions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.metadata.suggested_actions.map((action, index) => (
              <button
                key={index}
                className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-xs font-medium rounded-full transition-colors border border-indigo-200"
              >
                {action}
              </button>
            ))}
          </div>
        )}

        {/* Content images (auto-detected from URL) */}
        {contentImageUrls.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {contentImageUrls.map((url, index) => (
              <img
                key={index}
                src={url}
                alt=""
                className="max-w-full h-auto rounded-lg"
                style={{ maxHeight: '300px' }}
              />
            ))}
          </div>
        )}

        {/* Attachments (images) */}
        {message.metadata?.attachments && message.metadata.attachments.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.metadata.attachments.map((attachment, index) => (
              attachment.type === 'image' && attachment.url ? (
                <img
                  key={index}
                  src={attachment.url}
                  alt=""
                  className="max-w-full h-auto rounded-lg"
                  style={{ maxHeight: '300px' }}
                />
              ) : null
            ))}
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-xs mt-2 ${isUser ? 'text-indigo-200' : 'text-slate-400'}`}>
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
};

export default ChatBubble;