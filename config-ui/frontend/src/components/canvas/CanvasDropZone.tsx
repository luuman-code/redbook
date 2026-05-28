import React, { useState, useCallback, DragEvent } from 'react';

interface CanvasDropZoneProps {
  children: React.ReactNode;
  onFileDrop: (files: File[], position: { x: number; y: number }) => void;
  disabled?: boolean;
}

// Supported file types and their对应的 element types
const SUPPORTED_FILE_TYPES = {
  // 文本文件 -> text
  'text/plain': { extensions: ['.txt', '.md'], elementType: 'text' },
  'text/markdown': { extensions: ['.md'], elementType: 'text' },
  // 图片文件 -> image
  'image/png': { extensions: ['.png'], elementType: 'image' },
  'image/jpeg': { extensions: ['.jpg', '.jpeg'], elementType: 'image' },
  'image/gif': { extensions: ['.gif'], elementType: 'image' },
  'image/webp': { extensions: ['.webp'], elementType: 'image' },
  // 视频文件 -> video
  'video/mp4': { extensions: ['.mp4'], elementType: 'video' },
  'video/webm': { extensions: ['.webm'], elementType: 'video' },
  // 音频文件 -> audio
  'audio/mpeg': { extensions: ['.mp3'], elementType: 'audio' },
  'audio/wav': { extensions: ['.wav'], elementType: 'audio' },
  'audio/ogg': { extensions: ['.ogg'], elementType: 'audio' },
};

const getFileInfo = (file: File): { elementType: string; extension: string } | null => {
  const mimeType = file.type;
  const fileInfo = SUPPORTED_FILE_TYPES[mimeType as keyof typeof SUPPORTED_FILE_TYPES];

  if (fileInfo) {
    return {
      elementType: fileInfo.elementType,
      extension: file.name.substring(file.name.lastIndexOf('.')),
    };
  }

  // Fallback: check by extension
  const extension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (['.txt', '.md'].includes(extension)) return { elementType: 'text', extension };
  if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(extension)) return { elementType: 'image', extension };
  if (['.mp4', '.webm'].includes(extension)) return { elementType: 'video', extension };
  if (['.mp3', '.wav', '.ogg'].includes(extension)) return { elementType: 'audio', extension };

  return null;
};

const CanvasDropZone: React.FC<CanvasDropZoneProps> = ({
  children,
  onFileDrop,
  disabled = false,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [dragCounter, setDragCounter] = useState(0);

  const handleDragEnter = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    dragCounter === 0 && setIsDragging(true);
    setDragCounter(prev => prev + 1);
  }, [disabled, dragCounter]);

  const handleDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    setDragCounter(prev => {
      const newCounter = prev - 1;
      if (newCounter === 0) {
        setIsDragging(false);
      }
      return newCounter;
    });
  }, [disabled]);

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    // Set drop effect to copy
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy';
    }
  }, [disabled]);

  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    setIsDragging(false);
    setDragCounter(0);

    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;

    // Get drop position relative to the drop zone
    const rect = e.currentTarget.getBoundingClientRect();
    const position = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };

    // Filter supported files
    const validFiles = files.filter(file => getFileInfo(file) !== null);

    if (validFiles.length > 0) {
      onFileDrop(validFiles, position);
    }
  }, [disabled, onFileDrop]);

  return (
    <div
      className="relative w-full h-full"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {children}

      {/* Drop overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-indigo-500/10 border-2 border-dashed border-indigo-500 rounded-lg flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-white rounded-xl shadow-lg px-6 py-4 flex flex-col items-center gap-3">
            <div className="w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-800">释放文件以添加到画布</p>
              <p className="text-xs text-slate-500 mt-1">
                支持：文本、图片、视频、音频
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CanvasDropZone;
