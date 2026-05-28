import React, { memo, useState, useCallback, useRef, useEffect } from 'react';
import { CanvasElement, SelectionRegion } from '../../api/canvasApi';

interface SelectionOverlayProps {
  elements: CanvasElement[];
  selection: SelectionRegion | null;
  onSelectionChange: (selection: SelectionRegion | null) => void;
  toolType: 'select' | 'lasso' | 'rect_select';
  canvasOffset: { x: number; y: number };
  zoom: number;
}

interface Point {
  x: number;
  y: number;
}

// 射线法检测点是否在多边形内（不依赖组件state）
const isPointInPolygon = (polygon: Point[], point: Point): boolean => {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;

    if (
      yi > point.y !== yj > point.y &&
      point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi
    ) {
      inside = !inside;
    }
  }
  return inside;
};

// 检测元素的中心点是否在多边形内
const isElementCenterInPolygon = (
  polygon: Point[],
  element: CanvasElement
): boolean => {
  const centerX = element.position.x + element.size.width / 2;
  const centerY = element.position.y + element.size.height / 2;
  return isPointInPolygon(polygon, { x: centerX, y: centerY });
};

const SelectionOverlay: React.FC<SelectionOverlayProps> = ({
  elements,
  selection,
  onSelectionChange,
  toolType,
  canvasOffset,
  zoom,
}) => {
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectionStart, setSelectionStart] = useState<Point | null>(null);
  const [selectionEnd, setSelectionEnd] = useState<Point | null>(null);
  const [lassoPoints, setLassoPoints] = useState<Point[]>([]);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [previewCount, setPreviewCount] = useState<number>(0);
  const feedbackTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Clear feedback message after timeout
  const clearFeedback = useCallback(() => {
    if (feedbackTimeoutRef.current) {
      clearTimeout(feedbackTimeoutRef.current);
    }
    feedbackTimeoutRef.current = setTimeout(() => {
      setFeedbackMessage(null);
    }, 2000);
  }, []);

  // Show feedback message
  const showFeedback = useCallback((message: string) => {
    if (feedbackTimeoutRef.current) {
      clearTimeout(feedbackTimeoutRef.current);
    }
    setFeedbackMessage(message);
    feedbackTimeoutRef.current = setTimeout(() => {
      setFeedbackMessage(null);
    }, 2000);
  }, []);

  // Calculate bounds from selection region
  const getSelectionBounds = useCallback((): {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null => {
    if (!selection) return null;

    if (selection.type === 'lasso' && selection.lasso) {
      const points = selection.lasso.points;
      if (points.length < 2) return null;

      const xs = points.map(p => p.x);
      const ys = points.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      return {
        x: minX,
        y: minY,
        width: maxX - minX,
        height: maxY - minY,
      };
    }

    return selection.bounds;
  }, [selection]);

  // Check if a point is inside the selection region
  const isPointInSelection = useCallback((point: Point): boolean => {
    if (!selection) return false;

    if (selection.type === 'rect') {
      const { x, y, width, height } = selection.bounds;
      return (
        point.x >= x &&
        point.x <= x + width &&
        point.y >= y &&
        point.y <= y + height
      );
    }

    if (selection.type === 'lasso' && selection.lasso) {
      // Ray casting algorithm for polygon
      const points = selection.lasso.points;
      let inside = false;

      for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
        const xi = points[i].x;
        const yi = points[i].y;
        const xj = points[j].x;
        const yj = points[j].y;

        if (
          yi > point.y !== yj > point.y &&
          point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi
        ) {
          inside = !inside;
        }
      }

      return inside;
    }

    return false;
  }, [selection]);

  // Check if an element intersects with the selection
  const doesElementIntersect = useCallback((element: CanvasElement): boolean => {
    if (!selection) return false;

    const elRight = element.position.x + element.size.width;
    const elBottom = element.position.y + element.size.height;

    if (selection.type === 'rect') {
      const selRight = selection.bounds.x + selection.bounds.width;
      const selBottom = selection.bounds.y + selection.bounds.height;

      return !(
        element.position.x > selRight ||
        elRight < selection.bounds.x ||
        element.position.y > selBottom ||
        elBottom < selection.bounds.y
      );
    }

    if (selection.type === 'lasso') {
      // Check if any corner of the element is inside the lasso
      const corners = [
        { x: element.position.x, y: element.position.y },
        { x: elRight, y: element.position.y },
        { x: element.position.x, y: elBottom },
        { x: elRight, y: elBottom },
      ];

      return corners.some(corner => isPointInSelection(corner));
    }

    return false;
  }, [selection, isPointInSelection]);

  // Calculate elements that would be selected by current lasso preview
  const calculateLassoPreviewCount = useCallback((points: Point[]): number => {
    if (points.length < 2) return 0;

    const xs = points.map(p => p.x);
    const ys = points.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = maxX - minX;
    const height = maxY - minY;

    // Too small
    if (width <= 5 && height <= 5) return 0;

    // 使用射线法检测元素的中心点是否在套索多边形内
    return elements.filter(el => isElementCenterInPolygon(points, el)).length;
  }, [elements]);

  // Handle mouse down
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (toolType === 'select') return;

    const svg = svgRef.current;
    if (!svg) return;

    const rect = svg.getBoundingClientRect();
    // SelectionOverlay 在 transformed div 内部，getBoundingClientRect 已经考虑了 transform
    // 只需要计算相对于 SVG 左上角的坐标
    const point = {
      x: (e.clientX - rect.left) / zoom,
      y: (e.clientY - rect.top) / zoom,
    };

    setIsSelecting(true);
    setSelectionStart(point);
    setSelectionEnd(point);

    if (toolType === 'lasso') {
      setLassoPoints([point]);
    }
  }, [toolType, zoom]);

  // Handle mouse move
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isSelecting || !selectionStart) return;

    const svg = svgRef.current;
    if (!svg) return;

    const rect = svg.getBoundingClientRect();
    const point = {
      x: (e.clientX - rect.left) / zoom,
      y: (e.clientY - rect.top) / zoom,
    };

    setSelectionEnd(point);

    if (toolType === 'lasso') {
      const newLassoPoints = [...lassoPoints, point];
      setLassoPoints(newLassoPoints);

      // Update preview count for feedback
      const count = calculateLassoPreviewCount(newLassoPoints);
      setPreviewCount(count);
    }
  }, [isSelecting, selectionStart, toolType, zoom, lassoPoints, calculateLassoPreviewCount]);

  // Handle mouse up
  const handleMouseUp = useCallback(() => {
    if (!isSelecting || !selectionStart || !selectionEnd) {
      setIsSelecting(false);
      return;
    }

    let newSelection: SelectionRegion | null = null;

    if (toolType === 'rect_select' || toolType === 'select') {
      const x = Math.min(selectionStart.x, selectionEnd.x);
      const y = Math.min(selectionStart.y, selectionEnd.y);
      const width = Math.abs(selectionEnd.x - selectionStart.x);
      const height = Math.abs(selectionEnd.y - selectionStart.y);

      if (width > 5 || height > 5) {
        const selectedIds = elements
          .filter(el => {
            const elRight = el.position.x + el.size.width;
            const elBottom = el.position.y + el.size.height;
            return !(
              el.position.x > x + width ||
              elRight < x ||
              el.position.y > y + height ||
              elBottom < y
            );
          })
          .map(el => el.id);

        newSelection = {
          id: `selection_${Date.now()}`,
          type: 'rect',
          bounds: { x, y, width, height },
          element_ids: selectedIds,
        };

        // Show feedback for rect selection
        if (selectedIds.length === 0) {
          showFeedback('矩形区域内没有元素');
        } else {
          showFeedback(`选中了 ${selectedIds.length} 个元素`);
        }
      } else {
        showFeedback('选择区域太小');
      }
    } else if (toolType === 'lasso' && lassoPoints.length > 2) {
      // 直接从 lassoPoints 计算边界矩形（不依赖 selection state）
      const xs = lassoPoints.map(p => p.x);
      const ys = lassoPoints.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const bounds = {
        x: minX,
        y: minY,
        width: maxX - minX,
        height: maxY - minY,
      };

      console.log('[Lasso] Calculating bounds from lassoPoints:', {
        lassoPointsLength: lassoPoints.length,
        bounds,
        minX, maxX, minY, maxY
      });

      if (bounds.width > 5 || bounds.height > 5) {
        // 使用射线法检测元素的中心点是否在套索多边形内（真正的多边形碰撞检测）
        const selectedIds = elements
          .filter(el => isElementCenterInPolygon(lassoPoints, el))
          .map(el => el.id);

        newSelection = {
          id: `selection_${Date.now()}`,
          type: 'rect',  // 转换为矩形类型，用于后端处理
          bounds: bounds,
          element_ids: selectedIds,
          lasso: {
            id: `lasso_${Date.now()}`,
            type: 'lasso',
            points: lassoPoints,
            closed: true,
          },
        };

        // Show feedback for lasso selection
        if (selectedIds.length === 0) {
          showFeedback('套索区域内没有元素');
        } else {
          showFeedback(`套索选中了 ${selectedIds.length} 个元素`);
        }
        console.log('[Lasso] Selection completed:', {
          lassoPointsCount: lassoPoints.length,
          bounds,
          selectedIds,
          selectedCount: selectedIds.length
        });
      } else {
        showFeedback('套索区域太小');
        console.log('[Lasso] Selection too small:', bounds);
      }
    }

    onSelectionChange(newSelection);
    setIsSelecting(false);
    setSelectionStart(null);
    setSelectionEnd(null);
    setLassoPoints([]);
    setPreviewCount(0);
  }, [isSelecting, selectionStart, selectionEnd, toolType, lassoPoints, elements, onSelectionChange, showFeedback]);

  // Clear selection on escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onSelectionChange(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onSelectionChange]);

  // Render current selection shape
  const renderSelectionShape = () => {
    if (!isSelecting || !selectionStart || !selectionEnd) {
      if (!selection) return null;

      // Render existing selection - 增强版：始终显示选择框，醒目样式
      if (selection.type === 'rect') {
        const { x, y, width, height } = selection.bounds;

        // 如果有 lasso 信息（套索绘制后转换），同时渲染轨迹和矩形框
        if (selection.lasso && selection.lasso.points && selection.lasso.points.length > 0) {
          const pathData = selection.lasso.points
            .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
            .join(' ');

          return (
            <g>
              {/* 矩形框 - 实线高亮，醒目样式 */}
              <rect
                x={x}
                y={y}
                width={width}
                height={height}
                fill="rgba(99, 102, 241, 0.2)"
                stroke="#4f46e5"
                strokeWidth={3 / zoom}
              />
              {/* 外发光效果 */}
              <rect
                x={x - 2 / zoom}
                y={y - 2 / zoom}
                width={width + 4 / zoom}
                height={height + 4 / zoom}
                fill="none"
                stroke="rgba(99, 102, 241, 0.3)"
                strokeWidth={2 / zoom}
              />
              {/* 套索轨迹 - 虚线 */}
              <path
                d={pathData + ' Z'}
                fill="none"
                stroke="#a5b4fc"
                strokeWidth={1.5 / zoom}
                strokeDasharray={`${5 / zoom} ${3 / zoom}`}
              />
              {/* 角落标记 - 左上 */}
              <path d={`M ${x} ${y + 10 / zoom} L ${x} ${y} L ${x + 10 / zoom} ${y}`} stroke="#4f46e5" strokeWidth={2 / zoom} fill="none" />
              {/* 角落标记 - 右上 */}
              <path d={`M ${x + width - 10 / zoom} ${y} L ${x + width} ${y} L ${x + width} ${y + 10 / zoom}`} stroke="#4f46e5" strokeWidth={2 / zoom} fill="none" />
              {/* 角落标记 - 左下 */}
              <path d={`M ${x} ${y + height - 10 / zoom} L ${x} ${y + height} L ${x + 10 / zoom} ${y + height}`} stroke="#4f46e5" strokeWidth={2 / zoom} fill="none" />
              {/* 角落标记 - 右下 */}
              <path d={`M ${x + width - 10 / zoom} ${y + height} L ${x + width} ${y + height} L ${x + width} ${y + height - 10 / zoom}`} stroke="#4f46e5" strokeWidth={2 / zoom} fill="none" />
            </g>
          );
        }

        // 增强样式：更明显的填充和边框 + 外发光 + 角落标记
        return (
          <g>
            {/* 外发光效果 */}
            <rect
              x={x - 2 / zoom}
              y={y - 2 / zoom}
              width={width + 4 / zoom}
              height={height + 4 / zoom}
              fill="none"
              stroke="rgba(99, 102, 241, 0.4)"
              strokeWidth={3 / zoom}
            />
            {/* 主选择框 */}
            <rect
              x={x}
              y={y}
              width={width}
              height={height}
              fill="rgba(99, 102, 241, 0.15)"
              stroke="#4f46e5"
              strokeWidth={2 / zoom}
              strokeDasharray={`${6 / zoom} ${3 / zoom}`}
            />
            {/* 角落标记 - 左上 */}
            <path d={`M ${x} ${y + 12 / zoom} L ${x} ${y} L ${x + 12 / zoom} ${y}`} stroke="#4f46e5" strokeWidth={2.5 / zoom} fill="none" strokeLinecap="round" />
            {/* 角落标记 - 右上 */}
            <path d={`M ${x + width - 12 / zoom} ${y} L ${x + width} ${y} L ${x + width} ${y + 12 / zoom}`} stroke="#4f46e5" strokeWidth={2.5 / zoom} fill="none" strokeLinecap="round" />
            {/* 角落标记 - 左下 */}
            <path d={`M ${x} ${y + height - 12 / zoom} L ${x} ${y + height} L ${x + 12 / zoom} ${y + height}`} stroke="#4f46e5" strokeWidth={2.5 / zoom} fill="none" strokeLinecap="round" />
            {/* 角落标记 - 右下 */}
            <path d={`M ${x + width - 12 / zoom} ${y + height} L ${x + width} ${y + height} L ${x + width} ${y + height - 12 / zoom}`} stroke="#4f46e5" strokeWidth={2.5 / zoom} fill="none" strokeLinecap="round" />
          </g>
        );
      }

      if (selection.type === 'lasso' && selection.lasso) {
        const points = selection.lasso.points;
        const pathData = points
          .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
          .join(' ');

        return (
          <path
            d={pathData + ' Z'}
            fill="rgba(99, 102, 241, 0.1)"
            stroke="#6366f1"
            strokeWidth={1 / zoom}
          />
        );
      }

      return null;
    }

    // Render selection being drawn
    if (toolType === 'lasso' && lassoPoints.length > 1) {
      const pathData = lassoPoints
        .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
        .join(' ');

      // 计算当前边界矩形
      const xs = lassoPoints.map(p => p.x);
      const ys = lassoPoints.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      return (
        <g>
          {/* 套索轨迹 */}
          <path
            d={pathData}
            fill="none"
            stroke="#a5b4fc"
            strokeWidth={1.5 / zoom}
          />
          {/* 边界矩形预览 */}
          <rect
            x={minX}
            y={minY}
            width={maxX - minX}
            height={maxY - minY}
            fill="rgba(99, 102, 241, 0.1)"
            stroke="#6366f1"
            strokeWidth={2 / zoom}
            strokeDasharray={`${4 / zoom} ${4 / zoom}`}
          />
          {/* 预览数量标签 */}
          {previewCount > 0 && (
            <>
              <rect
                x={minX}
                y={minY - 24}
                width={80}
                height={20}
                fill="rgba(99, 102, 241, 0.9)"
                rx={4}
              />
              <text
                x={minX + 40}
                y={minY - 10}
                textAnchor="middle"
                fill="white"
                fontSize={12 / zoom}
                fontWeight="bold"
              >
                {previewCount} 个元素
              </text>
            </>
          )}
        </g>
      );
    }

    if ((toolType === 'rect_select' || toolType === 'select') && selectionStart && selectionEnd) {
      const x = Math.min(selectionStart.x, selectionEnd.x);
      const y = Math.min(selectionStart.y, selectionEnd.y);
      const width = Math.abs(selectionEnd.x - selectionStart.x);
      const height = Math.abs(selectionEnd.y - selectionStart.y);

      return (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill="rgba(99, 102, 241, 0.1)"
          stroke="#6366f1"
          strokeWidth={1 / zoom}
          strokeDasharray={`${4 / zoom} ${4 / zoom}`}
        />
      );
    }

    return null;
  };

  // 只有 lasso 和 rect_select 工具需要 SelectionOverlay 接收鼠标事件
  const needsPointerEvents = toolType === 'lasso' || toolType === 'rect_select';

  return (
    <>
    <svg
      ref={svgRef}
      className="selection-overlay"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: needsPointerEvents ? 'auto' : 'none',
        overflow: 'visible',
        zIndex: needsPointerEvents ? 100 : 0,
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {renderSelectionShape()}
    </svg>

    {/* Feedback message toast */}
    {feedbackMessage && (
      <div
        style={{
          position: 'absolute',
          top: 20,
          left: '50%',
          transform: 'translateX(-50%)',
          backgroundColor: 'rgba(99, 102, 241, 0.95)',
          color: 'white',
          padding: '10px 20px',
          borderRadius: 8,
          fontSize: 14,
          fontWeight: 500,
          zIndex: 1000,
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          animation: 'fadeIn 0.2s ease-out',
        }}
      >
        {feedbackMessage}
      </div>
    )}

    <style>{`
      @keyframes fadeIn {
        from { opacity: 0; transform: translateX(-50%) translateY(-10px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
      }
    `}</style>
    </>
  );
};

export default memo(SelectionOverlay);
