import React, { useState, useRef, useEffect, useCallback } from 'react';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  imageUrls?: string[];  // 消息中包含的图片URL
}

export interface Material {
  type: 'image' | 'video' | 'audio' | 'text';
  url?: string;
  content?: string;
  name?: string;
}

interface RightPanelProps {
  collapsed: boolean;
  onToggle: () => void;
  messages: ChatMessage[];
  onSendMessage: (message: string, imageUrls?: string[]) => void;
  onStop?: () => void;
  isTyping?: boolean;
}

const RightPanel: React.FC<RightPanelProps> = ({
  collapsed,
  onToggle,
  messages,
  onSendMessage,
  onStop,
  isTyping = false,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // 上传文件到 OSS
  const uploadFile = async (file: File): Promise<Material> => {
    const material: Material = {
      type: file.type.startsWith('image/') ? 'image' :
            file.type.startsWith('video/') ? 'video' :
            file.type.startsWith('audio/') ? 'audio' : 'text',
      name: file.name,
    };

    try {
      const { studioApi } = await import('../../api/studioApi');
      const uploadResult = await studioApi.uploadMaterial(file);
      if (uploadResult.success && uploadResult.url) {
        material.url = uploadResult.url;
        console.log(`图片上传成功: ${uploadResult.url}`);
      } else {
        // 上传失败，回退到 base64
        console.warn(`图片上传失败，回退到 base64`);
        const reader = new FileReader();
        material.content = await new Promise((resolve) => {
          reader.onload = (event) => resolve(event.target?.result as string);
          reader.readAsDataURL(file);
        });
      }
    } catch (error) {
      console.warn(`图片上传异常，回退到 base64: ${error}`);
      const reader = new FileReader();
      material.content = await new Promise((resolve) => {
        reader.onload = (event) => resolve(event.target?.result as string);
        reader.readAsDataURL(file);
      });
    }

    return material;
  };

  // 处理文件选择
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/')) {
        const material = await uploadFile(file);
        setMaterials(prev => [...prev, material]);
      }
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // 处理拖拽事件
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // 只有当离开 drop zone 时才设置 isDragging 为 false
    if (dropZoneRef.current && !dropZoneRef.current.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      if (file.type.startsWith('image/')) {
        const material = await uploadFile(file);
        setMaterials(prev => [...prev, material]);
      }
    }
  }, []);

  // 移除素材
  const removeMaterial = (index: number) => {
    setMaterials(prev => prev.filter((_, i) => i !== index));
  };

  const handleSend = () => {
    if ((inputValue.trim() || materials.length > 0) && !isTyping) {
      const imageUrls = materials
        .filter(m => m.type === 'image')
        .map(m => m.url || m.content)
        .filter(Boolean) as string[];
      onSendMessage(inputValue.trim(), imageUrls);
      setInputValue('');
      setMaterials([]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div
      ref={dropZoneRef}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex flex-col bg-white border-l border-slate-200 transition-all duration-300 relative ${
        collapsed ? 'w-12' : 'w-80'
      } ${isDragging ? 'ring-2 ring-indigo-500 ring-inset' : ''}`}
    >
      {/* Collapse toggle button */}
      <button
        onClick={onToggle}
        className="absolute top-4 -left-3 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-sm z-10 hover:bg-slate-50 transition-colors"
      >
        <svg
          className={`w-3 h-3 text-slate-500 transition-transform ${collapsed ? '' : 'rotate-180'}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-indigo-50 bg-opacity-90 flex items-center justify-center z-50 rounded-none">
          <div className="text-center">
            <svg className="w-12 h-12 mx-auto text-indigo-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <p className="text-indigo-600 font-medium">拖放图片到此处</p>
            <p className="text-indigo-400 text-sm">松开以上传图片作为参考</p>
          </div>
        </div>
      )}

      {!collapsed && (
        <>
          {/* Header */}
          <div className="flex-shrink-0 px-4 py-3 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-800">AI 助手</h3>
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                  <span className="text-xs text-slate-500">在线</span>
                </div>
              </div>
            </div>
          </div>

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="text-center py-8">
                <div className="w-12 h-12 mx-auto mb-3 bg-slate-100 rounded-full flex items-center justify-center">
                  <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <p className="text-sm text-slate-500">
                  描述你想让 AI 帮您做什么
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  或拖拽图片作为参考
                </p>
              </div>
            ) : (
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
                      message.role === 'user'
                        ? 'bg-indigo-500 text-white rounded-br-md'
                        : 'bg-slate-100 text-slate-800 rounded-bl-md'
                    }`}
                  >
                    {/* 显示消息中的图片 */}
                    {message.imageUrls && message.imageUrls.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1">
                        {message.imageUrls.map((url, idx) => (
                          <img
                            key={idx}
                            src={url}
                            alt="参考图"
                            className="max-w-full max-h-32 rounded-lg object-contain"
                          />
                        ))}
                      </div>
                    )}
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                    <p
                      className={`text-xs mt-1 ${
                        message.role === 'user' ? 'text-indigo-200' : 'text-slate-400'
                      }`}
                    >
                      {formatTime(message.timestamp)}
                    </p>
                  </div>
                </div>
              ))
            )}

            {/* Typing indicator */}
            {isTyping && (
              <div className="flex justify-start">
                <div className="bg-slate-100 rounded-2xl rounded-bl-md px-4 py-3">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className="flex-shrink-0 p-4 border-t border-slate-100">
            {/* Materials preview */}
            {materials.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {materials.map((material, index) => (
                  <div
                    key={index}
                    className="relative group"
                  >
                    {material.type === 'image' && material.url && (
                      <img
                        src={material.url || material.content}
                        alt="预览"
                        className="w-16 h-16 object-cover rounded-lg border border-slate-200"
                      />
                    )}
                    <button
                      onClick={() => removeMaterial(index)}
                      className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              {/* Upload button */}
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isTyping}
                className="flex-shrink-0 w-10 h-10 bg-slate-100 hover:bg-slate-200 disabled:bg-slate-100 disabled:opacity-50 text-slate-500 rounded-xl transition-colors flex items-center justify-center"
                title="上传参考图片"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*"
                onChange={handleFileSelect}
                className="hidden"
              />

              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="描述你想让AI帮您做什么..."
                className="flex-1 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 resize-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                rows={2}
                disabled={isTyping}
              />
              {isTyping && onStop ? (
                <button
                  onClick={onStop}
                  className="flex-shrink-0 w-10 h-10 bg-red-500 hover:bg-red-600 text-white rounded-xl transition-colors flex items-center justify-center"
                  title="停止"
                >
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" rx="1" />
                  </svg>
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={(!inputValue.trim() && materials.length === 0) || isTyping}
                  className="flex-shrink-0 w-10 h-10 bg-indigo-500 hover:bg-indigo-600 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-xl transition-colors flex items-center justify-center"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
              )}
            </div>

            {/* Hint text */}
            <div className="mt-2 text-xs text-slate-400 text-center">
              拖拽或点击上传图片作为参考
            </div>
          </div>
        </>
      )}

      {/* Collapsed view */}
      {collapsed && (
        <div className="flex-1 flex flex-col items-center py-4">
          <button
            onClick={onToggle}
            className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-600 hover:bg-slate-50 hover:text-slate-800 transition-colors"
            title="AI 对话"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </button>
          <span className="text-xs text-slate-400 mt-1 writing-mode-vertical" style={{ writingMode: 'vertical-rl' }}>
            AI 对话
          </span>
          {messages.length > 0 && (
            <span className="mt-2 w-5 h-5 bg-indigo-500 text-white text-xs rounded-full flex items-center justify-center">
              {messages.length}
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default RightPanel;
