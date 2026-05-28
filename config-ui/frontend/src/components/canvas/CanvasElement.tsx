import React, { memo, useState, useRef, useEffect } from 'react';
import { CanvasElement as CanvasElementType, ElementStyles } from '../../api/canvasApi';

interface CanvasElementProps {
  element: CanvasElementType;
  isSelected: boolean;
  onSelect: (elementId: string, addToSelection: boolean) => void;
  onElementUpdate?: (elementId: string, updates: Partial<CanvasElementType>) => void;
  onElementMove?: (elementId: string, position: { x: number; y: number }) => void;
  onElementResize?: (elementId: string, size: { width: number; height: number }) => void;
}

const CanvasElement: React.FC<CanvasElementProps> = ({
  element,
  isSelected,
  onSelect,
  onElementUpdate,
  onElementMove,
  onElementResize,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Drag/resize state - using refs to avoid closure issues with state
  const isDraggingRef = useRef(false);
  const isResizingRef = useRef(false);
  const resizeHandleRef = useRef<string | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0, elementX: 0, elementY: 0, elementWidth: 0, elementHeight: 0 });

  const { position, size, styles, metadata, type, visible, locked } = element;

  // Handle drag start (from element body)
  const handleDragStart = (e: React.MouseEvent) => {
    if (locked || isEditing) return;
    e.stopPropagation();

    isDraggingRef.current = true;
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      elementX: position.x,
      elementY: position.y,
      elementWidth: size.width,
      elementHeight: size.height,
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current) return;

      const deltaX = e.clientX - dragStartRef.current.x;
      const deltaY = e.clientY - dragStartRef.current.y;

      const newX = dragStartRef.current.elementX + deltaX;
      const newY = dragStartRef.current.elementY + deltaY;

      if (onElementMove) {
        onElementMove(element.id, { x: newX, y: newY });
      }
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  // Handle resize start (from selection handles)
  const handleResizeStart = (e: React.MouseEvent, handle: string) => {
    if (locked || isEditing) return;
    e.stopPropagation();

    isResizingRef.current = true;
    resizeHandleRef.current = handle;
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      elementX: position.x,
      elementY: position.y,
      elementWidth: size.width,
      elementHeight: size.height,
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;

      const deltaX = e.clientX - dragStartRef.current.x;
      const deltaY = e.clientY - dragStartRef.current.y;
      const { elementX, elementY, elementWidth, elementHeight } = dragStartRef.current;

      let newX = elementX;
      let newY = elementY;
      let newWidth = elementWidth;
      let newHeight = elementHeight;

      // Calculate new dimensions based on which handle is being dragged
      switch (handle) {
        case 'se':
          newWidth = Math.max(20, elementWidth + deltaX);
          newHeight = Math.max(20, elementHeight + deltaY);
          break;
        case 'sw':
          newWidth = Math.max(20, elementWidth - deltaX);
          newHeight = Math.max(20, elementHeight + deltaY);
          newX = elementX + (elementWidth - newWidth);
          break;
        case 'ne':
          newWidth = Math.max(20, elementWidth + deltaX);
          newHeight = Math.max(20, elementHeight - deltaY);
          newY = elementY + (elementHeight - newHeight);
          break;
        case 'nw':
          newWidth = Math.max(20, elementWidth - deltaX);
          newHeight = Math.max(20, elementHeight - deltaY);
          newX = elementX + (elementWidth - newWidth);
          newY = elementY + (elementHeight - newHeight);
          break;
        case 'n':
          newHeight = Math.max(20, elementHeight - deltaY);
          newY = elementY + (elementHeight - newHeight);
          break;
        case 's':
          newHeight = Math.max(20, elementHeight + deltaY);
          break;
        case 'e':
          newWidth = Math.max(20, elementWidth + deltaX);
          break;
        case 'w':
          newWidth = Math.max(20, elementWidth - deltaX);
          newX = elementX + (elementWidth - newWidth);
          break;
      }

      if (onElementResize && (newWidth !== elementWidth || newHeight !== elementHeight)) {
        onElementResize(element.id, { width: newWidth, height: newHeight });
      }
      if (onElementMove && (newX !== elementX || newY !== elementY)) {
        onElementMove(element.id, { x: newX, y: newY });
      }
    };

    const handleMouseUp = () => {
      isResizingRef.current = false;
      resizeHandleRef.current = null;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  // Sync edit text with metadata
  useEffect(() => {
    if (isEditing) {
      setEditText(metadata.text_content || '');
    }
  }, [isEditing, metadata.text_content]);

  // Focus textarea when editing starts
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.select();
    }
  }, [isEditing]);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!locked) {
      onSelect(element.id, e.shiftKey || e.ctrlKey || e.metaKey);
    }
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (type === 'text' && !locked) {
      setIsEditing(true);
    }
  };

  const handleBlur = () => {
    if (isEditing) {
      setIsEditing(false);
      console.log('[CanvasElement] handleBlur:', {
        elementId: element.id,
        editText,
        metadataTextContent: metadata.text_content,
        willUpdate: onElementUpdate && editText !== metadata.text_content
      });
      if (onElementUpdate && editText !== metadata.text_content) {
        console.log('[CanvasElement] Calling onElementUpdate with:', { text_content: editText });
        onElementUpdate(element.id, {
          metadata: { ...metadata, text_content: editText },
        });
      } else {
        console.log('[CanvasElement] Skipping update - text unchanged or no handler');
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsEditing(false);
      setEditText(metadata.text_content || '');
    } else if (e.key === 'Enter' && !e.shiftKey) {
      handleBlur();
    }
  };

  // Render different element types
  const renderElementContent = () => {
    switch (type) {
      case 'text':
        return renderTextElement();
      case 'image':
        return renderImageElement();
      case 'video':
        return renderVideoElement();
      case 'audio':
        return renderAudioElement();
      case 'shape':
        return renderShapeElement();
      default:
        return renderDefaultElement();
    }
  };

  const renderTextElement = () => {
    const textStyle: React.CSSProperties = {
      fontSize: metadata.font_size || styles.font_size || 16,
      fontFamily: metadata.font_family || styles.font_family || 'inherit',
      textAlign: (metadata.text_align || styles.text_align || 'left') as any,
      lineHeight: metadata.line_height || styles.line_height || 1.5,
      color: styles.color || '#000000',
      fontWeight: styles.bold ? 'bold' : 'normal',
      fontStyle: styles.italic ? 'italic' : 'normal',
      textDecoration: styles.underline ? 'underline' : 'none',
    };

    if (isEditing) {
      return (
        <textarea
          ref={textareaRef}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          className="w-full h-full bg-transparent border-none outline-none resize-none"
          style={textStyle}
        />
      );
    }

    return (
      <div className="w-full h-full overflow-hidden" style={textStyle}>
        {metadata.text_content || '双击编辑文本'}
      </div>
    );
  };

  const renderImageElement = () => {
    let imageSrc = metadata.url || metadata.local_path;

    // 如果是外部 OSS URL（包含 aliyuncs.com），使用后端代理避免 CORS 问题
    // 包括: redbook-materials, dashscope 等
    if (imageSrc && imageSrc.includes('aliyuncs.com')) {
      imageSrc = `http://localhost:8080/api/studio/proxy/image?url=${encodeURIComponent(imageSrc)}`;
    }

    if (!imageSrc) {
      return (
        <div className="w-full h-full flex items-center justify-center bg-slate-100 text-slate-400">
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
      );
    }

    return (
      <img
        src={imageSrc}
        alt={metadata.text_content || 'Image'}
        className="w-full h-full object-cover"
        draggable={false}
        crossOrigin="anonymous"
      />
    );
  };

  const renderVideoElement = () => {
    const videoSrc = metadata.url || metadata.local_path;

    if (!videoSrc) {
      return (
        <div className="w-full h-full flex items-center justify-center bg-slate-100 text-slate-400">
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        </div>
      );
    }

    return (
      <video
        src={videoSrc}
        className="w-full h-full object-cover"
        controls
        preload="metadata"
      />
    );
  };

  const renderAudioElement = () => {
    const audioSrc = metadata.url || metadata.local_path;

    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-slate-50 p-4">
        <svg className="w-8 h-8 text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
        </svg>
        {audioSrc ? (
          <audio
            src={audioSrc}
            className="w-full"
            controls
            preload="metadata"
          />
        ) : (
          <span className="text-xs text-slate-400">无音频源</span>
        )}
      </div>
    );
  };

  const renderShapeElement = () => {
    const shapeType = metadata.shape_type || 'rect';
    // 修改：让 metadata 中的颜色优先，避免被 styles 的默认值覆盖
    // 修复：如果 metadata 和 styles 都没有颜色，使用明显可见的颜色
    let fill = metadata.fill_color || styles.fill;
    let stroke = metadata.stroke_color || styles.stroke;
    // 如果 fill 为空，使用浅蓝色作为默认（比灰色更明显可见）
    if (!fill) fill = '#93c5fd';
    // 如果 stroke 为空，使用深蓝色
    if (!stroke) stroke = '#1d4ed8';
    let strokeWidth = metadata.stroke_width || styles.stroke_width || 2;
    const borderRadius = styles.corner_radius || 0;

    // DEBUG: 渲染时打印颜色信息
    console.log('[CanvasElement] renderShapeElement - element id:', element.id);
    console.log('[CanvasElement] renderShapeElement - shapeType:', shapeType);
    console.log('[CanvasElement] position:', element.position);
    console.log('[CanvasElement] size:', element.size);
    console.log('[CanvasElement] metadata.fill_color:', metadata.fill_color);
    console.log('[CanvasElement] metadata.stroke_color:', metadata.stroke_color);
    console.log('[CanvasElement] styles.fill:', styles.fill);
    console.log('[CanvasElement] styles.stroke:', styles.stroke);
    console.log('[CanvasElement] final fill (used for render):', fill);
    console.log('[CanvasElement] final stroke (used for render):', stroke);

    // Handle path type (from pen tool and Agent)
    if (shapeType === 'path') {
      // 【关键】优先使用 normalized_points（用户绘制时有）
      // 如果没有，则使用 points（Agent 绘制时有）
      const rawPoints = metadata.normalized_points || metadata.points || [];
      if (rawPoints.length < 2) {
        // 如果没有有效的点，但有 fill_color，仍然显示一个有色矩形
        if (fill && fill !== '#93c5fd') {
          return (
            <svg width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`}>
              <rect x="0" y="0" width={size.width} height={size.height} fill={fill} rx={borderRadius} />
            </svg>
          );
        }
        return <div className="w-full h-full" />;
      }

      // Normalize points to [[x, y], ...] format
      // Points can be either [{x, y}, ...] or [[x, y], ...]
      const points = rawPoints.map((p: any) =>
        Array.isArray(p) ? p : [p.x, p.y]
      );

      // 【新增】自动检测坐标类型
      let effectivePoints: number[][];
      const firstX = points[0]?.[0] || 0;
      const firstY = points[0]?.[1] || 0;

      // 检测是否为绝对坐标：第一个点超过元素尺寸
      const isAbsoluteCoords = firstX > size.width || firstY > size.height;

      if (isAbsoluteCoords) {
        // 绝对坐标：转换为 viewBox 内的相对坐标
        effectivePoints = points.map((p: number[]) => [
          p[0] - position.x,
          p[1] - position.y
        ]);
      } else {
        // 相对坐标：直接使用
        effectivePoints = points;
      }

      // Build SVG path from effectivePoints
      const pathData = effectivePoints.reduce((d: string, point: number[], i: number) => {
        if (i === 0) {
          return `M ${point[0]} ${point[1]}`;
        }
        return `${d} L ${point[0]} ${point[1]}`;
      }, '');

      return (
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${size.width} ${size.height}`}
          style={{ overflow: 'visible' }}
        >
          <path
            d={pathData}
            fill={metadata.fill_color || fill || 'none'}
            stroke={metadata.stroke_color || stroke}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    }

    const shapeStyle: React.CSSProperties = {
      width: '100%',
      height: '100%',
      backgroundColor: fill,
      border: `${strokeWidth}px solid ${stroke}`,
      borderRadius: `${borderRadius}px`,
    };

    switch (shapeType) {
      case 'circle':
        return <div {...shapeStyle} style={{ ...shapeStyle, borderRadius: '50%' }} />;
      case 'triangle':
        return (
          <div
            style={{
              width: 0,
              height: 0,
              background: 'transparent',
              borderLeft: `${size.width / 2}px solid transparent`,
              borderRight: `${size.width / 2}px solid transparent`,
              borderBottom: `${size.height}px solid ${fill}`,
            }}
          />
        );
      case 'line':
        return (
          <svg width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`}>
            <line
              x1="0"
              y1={size.height / 2}
              x2={size.width}
              y2={size.height / 2}
              stroke={stroke}
              strokeWidth={strokeWidth}
            />
          </svg>
        );
      case 'polygon':
        // 多边形使用 SVG 渲染
        // points 格式: [[x1, y1], [x2, y2], ...] 或 [x1, y1, x2, y2, ...] 或 [{x, y}, ...]
        // 注意: points 可能是绝对坐标，需要转换为相对于元素位置的坐标
        if (!metadata.points || !Array.isArray(metadata.points) || metadata.points.length === 0) {
          return <div {...shapeStyle} />;
        }

        let pointsStr: string;
        try {
          const firstItem = metadata.points[0];
          // 元素位置的偏移量（points 可能是绝对坐标）
          const offsetX = position.x;
          const offsetY = position.y;

          if (typeof firstItem === 'number') {
            // 格式: [x1, y1, x2, y2, ...] - 扁平数组，假设是绝对坐标
            const nums = metadata.points as number[];
            const pairs: string[] = [];
            for (let i = 0; i < nums.length; i += 2) {
              if (i + 1 < nums.length) {
                // 转换为相对坐标
                pairs.push(`${nums[i] - offsetX},${nums[i+1] - offsetY}`);
              }
            }
            pointsStr = pairs.join(' ');
          } else if (Array.isArray(firstItem)) {
            // 格式: [[x1, y1], [x2, y2], ...]
            // 检查是否是绝对坐标（如果第一个点超过元素尺寸，认为是绝对坐标）
            const isAbsoluteCoords = (metadata.points as number[][])[0][0] > size.width ||
                                     (metadata.points as number[][])[0][1] > size.height;
            if (isAbsoluteCoords) {
              // 绝对坐标转换为相对坐标
              pointsStr = (metadata.points as number[][]).map(p => `${p[0] - offsetX},${p[1] - offsetY}`).join(' ');
            } else {
              // 已经是相对坐标
              pointsStr = (metadata.points as number[][]).map(p => `${p[0]},${p[1]}`).join(' ');
            }
          } else if (typeof firstItem === 'object' && firstItem !== null && 'x' in firstItem && 'y' in firstItem) {
            // 格式: [{x, y}, ...]
            pointsStr = (metadata.points as {x: number, y: number}[]).map(p => `${p.x - offsetX},${p.y - offsetY}`).join(' ');
          } else {
            console.error('Invalid polygon points format:', metadata.points);
            return <div {...shapeStyle} />;
          }
        } catch (e) {
          console.error('Error parsing polygon points:', e, metadata.points);
          return <div {...shapeStyle} />;
        }

        return (
          <svg width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`} preserveAspectRatio="none">
            <polygon
              points={pointsStr}
              fill={fill || 'none'}
              stroke={stroke}
              strokeWidth={strokeWidth}
            />
          </svg>
        );
      case 'ellipse':
        return (
          <svg width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`}>
            <ellipse
              cx={size.width / 2}
              cy={size.height / 2}
              rx={size.width / 2}
              ry={size.height / 2}
              fill={fill || 'none'}
              stroke={stroke}
              strokeWidth={strokeWidth}
            />
          </svg>
        );
      default:
        return <div {...shapeStyle} />;
    }
  };

  const renderDefaultElement = () => {
    return (
      <div className="w-full h-full flex items-center justify-center bg-slate-100 text-slate-400 border-2 border-dashed border-slate-300">
        <span className="text-xs">未知元素类型</span>
      </div>
    );
  };

  const elementStyle: React.CSSProperties = {
    position: 'absolute',
    left: position.x,
    top: position.y,
    width: size.width,
    height: size.height,
    transform: `rotate(${styles.rotation || 0}deg)`,
    opacity: styles.opacity ?? 1,
    visibility: visible ? 'visible' : 'hidden',
    pointerEvents: locked ? 'none' : 'auto',
    zIndex: element.z_index,
    filter: `
      blur(${styles.blur || 0}px)
      brightness(100%)
      contrast(100%)
    `,
    boxShadow: styles.shadow_enabled
      ? `${styles.shadow_offset_x || 0}px ${styles.shadow_offset_y || 0}px ${styles.shadow_blur || 0}px ${styles.shadow_color || 'rgba(0,0,0,0.1)'}`
      : 'none',
  };

  return (
    <div
      className={`canvas-element ${isSelected ? 'selected' : ''} ${locked ? 'locked' : ''} ${isDraggingRef.current ? 'dragging' : ''}`}
      style={elementStyle}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onMouseDown={handleDragStart}
    >
      {renderElementContent()}

      {/* Selection indicators */}
      {isSelected && !isEditing && !isDraggingRef.current && !isResizingRef.current && (
        <div className="selection-handles">
          {/* Corner handles */}
          <div className="handle handle-nw" onMouseDown={(e) => handleResizeStart(e, 'nw')} />
          <div className="handle handle-ne" onMouseDown={(e) => handleResizeStart(e, 'ne')} />
          <div className="handle handle-sw" onMouseDown={(e) => handleResizeStart(e, 'sw')} />
          <div className="handle handle-se" onMouseDown={(e) => handleResizeStart(e, 'se')} />
          {/* Edge handles */}
          <div className="handle handle-n" onMouseDown={(e) => handleResizeStart(e, 'n')} />
          <div className="handle handle-s" onMouseDown={(e) => handleResizeStart(e, 's')} />
          <div className="handle handle-e" onMouseDown={(e) => handleResizeStart(e, 'e')} />
          <div className="handle handle-w" onMouseDown={(e) => handleResizeStart(e, 'w')} />
        </div>
      )}

      <style>{`
        .canvas-element {
          cursor: move;
          user-select: none;
        }
        .canvas-element.locked {
          cursor: not-allowed;
        }
        .canvas-element.selected {
          outline: 2px solid #6366f1;
          outline-offset: 1px;
        }
        .canvas-element.dragging {
          opacity: 0.8;
          cursor: grabbing;
        }
        .selection-handles .handle {
          position: absolute;
          width: 8px;
          height: 8px;
          background: white;
          border: 2px solid #6366f1;
          border-radius: 2px;
        }
        .handle-nw { top: -4px; left: -4px; cursor: nw-resize; }
        .handle-ne { top: -4px; right: -4px; cursor: ne-resize; }
        .handle-sw { bottom: -4px; left: -4px; cursor: sw-resize; }
        .handle-se { bottom: -4px; right: -4px; cursor: se-resize; }
        .handle-n { top: -4px; left: 50%; transform: translateX(-50%); cursor: n-resize; }
        .handle-s { bottom: -4px; left: 50%; transform: translateX(-50%); cursor: s-resize; }
        .handle-e { right: -4px; top: 50%; transform: translateY(-50%); cursor: e-resize; }
        .handle-w { left: -4px; top: 50%; transform: translateY(-50%); cursor: w-resize; }
      `}</style>
    </div>
  );
};

export default memo(CanvasElement);
