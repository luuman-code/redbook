import React, { useState, useRef, KeyboardEvent, useEffect } from 'react';

export interface Material {
  type: 'image' | 'video' | 'audio' | 'text';
  url?: string;
  content?: string;
  name?: string;
}

interface ChatInputProps {
  onSend: (message: string, materials?: Material[]) => void;
  onStop?: () => void;
  disabled?: boolean;
  placeholder?: string;
  // 外部管理的 materials 状态（可选）
  materials?: Material[];
  setMaterials?: (materials: Material[]) => void;
}

const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onStop,
  disabled = false,
  placeholder = '输入你的需求或问题...',
  materials: externalMaterials,
  setMaterials: externalSetMaterials,
}) => {
  const [input, setInput] = useState('');
  const [localMaterials, setLocalMaterials] = useState<Material[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 如果外部提供了 materials 状态，使用外部的；否则使用本地状态
  const materials = externalMaterials !== undefined ? externalMaterials : localMaterials;
  const setMaterials = externalSetMaterials || setLocalMaterials;

  const handleSend = () => {
    const trimmed = input.trim();
    if ((trimmed || materials.length > 0) && !disabled) {
      onSend(trimmed, materials);
      setInput('');
      // 不再自动清空 materials，让它们在父组件中保持持久化
      if (!externalSetMaterials) {
        setLocalMaterials([]);
      }
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Send on Enter without Shift (Shift+Enter for new line)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    // 动态导入 studioApi
    const { studioApi } = await import('../../api/studioApi');

    for (const file of Array.from(files)) {
      const material: Material = {
        type: file.type.startsWith('image/') ? 'image' :
              file.type.startsWith('video/') ? 'video' :
              file.type.startsWith('audio/') ? 'audio' : 'text',
        name: file.name,
      };

      try {
        // 优先上传到服务器获取 URL
        const uploadResult = await studioApi.uploadMaterial(file);
        if (uploadResult.success && uploadResult.url) {
          material.url = uploadResult.url;
          material.content = undefined; // 不再使用 base64
          console.log(`素材上传成功: ${uploadResult.filename}, URL: ${uploadResult.url}`);
        } else {
          // 上传失败，回退到 base64
          console.warn(`素材上传失败，回退到 base64: ${uploadResult}`);
          const reader = new FileReader();
          reader.onload = (event) => {
            const base64 = event.target?.result as string;
            material.content = base64;
          };
          reader.readAsDataURL(file);
        }
      } catch (error) {
        // 上传出错，回退到 base64
        console.warn(`素材上传异常，回退到 base64: ${error}`);
        const reader = new FileReader();
        reader.onload = (event) => {
          const base64 = event.target?.result as string;
          material.content = base64;
        };
        reader.readAsDataURL(file);
      }

      setMaterials(prev => [...prev, material]);
    }

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeMaterial = (index: number) => {
    setMaterials(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-3">
      {/* Materials preview */}
      {materials.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {materials.map((material, index) => (
            <div
              key={index}
              className="flex items-center gap-1 bg-slate-100 rounded-lg px-2 py-1 text-xs"
            >
              {material.type === 'image' && (
                <span className="text-indigo-500">📷</span>
              )}
              {material.type === 'video' && (
                <span className="text-pink-500">🎬</span>
              )}
              {material.type === 'audio' && (
                <span className="text-amber-500">🎵</span>
              )}
              {material.type === 'text' && (
                <span className="text-slate-500">📄</span>
              )}
              <span className="text-slate-600 truncate max-w-20">
                {material.name || '素材'}
              </span>
              <button
                onClick={() => removeMaterial(index)}
                className="text-slate-400 hover:text-red-500"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-3">
        {/* Upload button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="flex-shrink-0 w-10 h-10 bg-slate-100 hover:bg-slate-200 disabled:bg-slate-100 disabled:opacity-50 text-slate-500 rounded-xl transition-colors flex items-center justify-center"
          title="上传素材"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,video/*,audio/*,.txt,.doc,.docx,.pdf"
          onChange={handleFileSelect}
          className="hidden"
        />

        {/* Text input area */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm resize-none outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed placeholder-slate-400"
            style={{ maxHeight: '120px' }}
          />
        </div>

        {/* Send button or Stop button */}
        {disabled && onStop ? (
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
            disabled={(!input.trim() && materials.length === 0) || disabled}
            className="flex-shrink-0 w-10 h-10 bg-indigo-500 hover:bg-indigo-600 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-xl transition-colors flex items-center justify-center"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Hint text */}
      <div className="mt-2 text-xs text-slate-400 text-center">
        按 Enter 发送，Shift + Enter 换行
      </div>
    </div>
  );
};

export default ChatInput;