import React, { useState, useEffect, useCallback, useRef } from 'react';
import LeftToolbar from '../components/canvas/LeftToolbar';
import RightPanel, { ChatMessage } from '../components/canvas/RightPanel';
import CanvasDropZone from '../components/canvas/CanvasDropZone';
import CanvasElement from '../components/canvas/CanvasElement';
import SelectionOverlay from '../components/canvas/SelectionOverlay';
import { canvasApi, Canvas, CanvasElement as CanvasElementType, SelectionRegion } from '../api/canvasApi';
import { ToolType } from '../components/canvas/types';
import { useCanvasWebSocket, CanvasUpdateData } from '../hooks/useCanvasWebSocket';
import html2canvas from 'html2canvas';

// Helper function: Check if a point is inside a polygon using ray casting algorithm
function isPointInPolygon(x: number, y: number, polygon: { x: number; y: number }[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x, yi = polygon[i].y;
    const xj = polygon[j].x, yj = polygon[j].y;
    const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

interface CanvasWorkspaceProps {
  canvasId: string;
  onBack: () => void;
}

const CanvasWorkspace: React.FC<CanvasWorkspaceProps> = ({
  canvasId,
  onBack,
}) => {
  // Canvas state
  const [canvas, setCanvas] = useState<Canvas | null>(null);
  const [elements, setElements] = useState<CanvasElementType[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selection, setSelection] = useState<SelectionRegion | null>(null);

  // Tool state
  const [currentTool, setCurrentTool] = useState<ToolType>('select');

  // UI state
  const [leftToolbarCollapsed, setLeftToolbarCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [zoom, setZoom] = useState(1);
  const [canvasOffset, setCanvasOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [agentMode, setAgentMode] = useState<string>('daily');  // agent 当前模式

  // Mode switch confirmation dialog state
  const [showModeConfirm, setShowModeConfirm] = useState(false);
  const [modeConfirmType, setModeConfirmType] = useState<string>('');
  const [modeConfirmConfidence, setModeConfirmConfidence] = useState<number>(0);
  const [modeConfirmReason, setModeConfirmReason] = useState<string>('');

  // Canvas container ref
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Canvas content ref for smart crop
  const canvasContentRef = useRef<HTMLDivElement>(null);

  // Drawing state for pen tool
  const [isDrawing, setIsDrawing] = useState(false);
  const [currentPath, setCurrentPath] = useState<{ x: number; y: number }[]>([]);
  const [penColor, setPenColor] = useState('#000000');
  const [penWidth, setPenWidth] = useState(2);

  // Streaming painting state for real-time AI drawing
  const [streamingElements, setStreamingElements] = useState<Record<string, {
    points: number[][];
    stroke_color: string;
    fill_color: string;
    stroke_width: number;
    x: number;
    y: number;
  }>>({});

  // Eraser state
  const [isErasing, setIsErasing] = useState(false);

  // Text tool drag state
  const [isCreatingText, setIsCreatingText] = useState(false);
  const [textPreview, setTextPreview] = useState<{ x: number; y: number; width: number; height: number } | null>(null);

  // Smart crop preview state - only used for showing immediate feedback after crop
  const [cropPreview, setCropPreview] = useState<{ x: number; y: number; width: number; height: number; success: boolean; path?: { x: number; y: number }[] } | null>(null);

  // Group editing mode state - 用于编辑组合时解锁子元素
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editModeMessage, setEditModeMessage] = useState<string | null>(null);

  // Show temporary message to user
  const showEditModeMessage = useCallback((message: string) => {
    setEditModeMessage(message);
    setTimeout(() => setEditModeMessage(null), 3000);
  }, []);

  // Enter group edit mode - unlock group and its children
  const enterGroupEditMode = useCallback((groupId: string) => {
    const group = elements.find(el => el.id === groupId);
    if (!group?.metadata?.child_ids || group.metadata.child_ids.length === 0) {
      console.log('[Canvas] Cannot enter edit mode: not a group or has no children');
      showEditModeMessage('⚠️ 未找到组合，无法进入编辑模式');
      return;
    }

    const childIds = group.metadata.child_ids;
    console.log('[Canvas] Entering edit mode for group:', groupId, 'children:', childIds);

    // Unlock group and all its children
    setElements(prev => prev.map(el => {
      if (el.id === groupId || childIds.includes(el.id)) {
        return { ...el, locked: false };
      }
      return el;
    }));
    setEditingGroupId(groupId);
    showEditModeMessage('✏️ 已进入编辑模式，可单独修改或删除元素');
  }, [elements, showEditModeMessage]);

  // Exit group edit mode - relock group and its children
  const exitGroupEditMode = useCallback(() => {
    if (!editingGroupId) return;

    const group = elements.find(el => el.id === editingGroupId);
    if (!group?.metadata?.child_ids) {
      setEditingGroupId(null);
      return;
    }

    const childIds = group.metadata.child_ids;
    console.log('[Canvas] Exiting edit mode for group:', editingGroupId, 'children:', childIds);

    // Relock group and all its children
    setElements(prev => prev.map(el => {
      if (el.id === editingGroupId || childIds.includes(el.id)) {
        return { ...el, locked: true };
      }
      return el;
    }));
    setEditingGroupId(null);
    showEditModeMessage('🔒 已退出编辑模式，组合已锁定');
  }, [editingGroupId, elements, showEditModeMessage]);

  // WebSocket for real-time updates
  const handleCanvasUpdate = useCallback((data: CanvasUpdateData) => {
    console.log('[CanvasWS] Received CANVAS_UPDATE:', JSON.stringify(data));
    console.log('[CanvasWS] data type:', typeof data);
    console.log('[CanvasWS] data.elements:', data?.elements);
    if (data?.elements) {
      console.log('[CanvasWS] Updating elements, count:', data.elements.length);
      console.log('[CanvasWS] First element:', data.elements[0]);
      setElements(data.elements);
    } else {
      console.log('[CanvasWS] CANVAS_UPDATE has no elements, full data:', data);
    }
  }, []);

  const { isConnected, syncState, sendBrushStroke, sendStopMessage } = useCanvasWebSocket({
    canvasId,
    onCanvasUpdate: handleCanvasUpdate,
    onOpen: () => console.log('[CanvasWS] Connected'),
    onClose: () => console.log('[CanvasWS] Disconnected'),
    onError: (err) => console.error('[CanvasWS] Error:', err),
    onDrawStart: (data) => {
      console.log('[Canvas] Draw started:', data);
      // Optional: show "drawing..." hint
    },
    onDrawProgress: (data) => {
      console.log('[Canvas] Draw progress:', data);
      setStreamingElements(prev => ({
        ...prev,
        [data.item_id]: {
          points: data.points,
          stroke_color: data.stroke_color,
          fill_color: data.fill_color,
          stroke_width: data.stroke_width,
          x: data.x || 0,
          y: data.y || 0,
        }
      }));
    },
    onDrawComplete: (data) => {
      console.log('[Canvas] Draw complete:', data);
      // DEBUG: 详细打印 metadata 信息
      if (data.element) {
        console.log('[Canvas] === DEBUG fill_color ===');
        console.log('[Canvas] element.id:', data.element.id);
        console.log('[Canvas] metadata.fill_color:', data.element.metadata?.fill_color);
        console.log('[Canvas] metadata.stroke_color:', data.element.metadata?.stroke_color);
        console.log('[Canvas] metadata.stroke_width:', data.element.metadata?.stroke_width);
        console.log('[Canvas] styles.fill:', data.element.styles?.fill);
        console.log('[Canvas] styles.stroke:', data.element.styles?.stroke);
        console.log('[Canvas] full metadata:', data.element.metadata);
        console.log('[Canvas] full styles:', data.element.styles);
      }
      // Remove streaming state, add element to official list
      setStreamingElements(prev => {
        const { [data.item_id]: _, ...rest } = prev;
        return rest;
      });
      // Add final element
      if (data.element) {
        setElements(prev => [...prev, data.element]);
      }
    },
    onDrawError: (data) => {
      console.error('[Canvas] Draw error:', data);
      // Show error hint
      setStreamingElements(prev => {
        const { [data.item_id]: _, ...rest } = prev;
        return rest;
      });
    },
    onDrawUndo: (data) => {
      console.log('[Canvas] Draw undo:', data);
      // 移除被回撤的元素（支持单个或批量删除）
      if (data.element_ids && data.element_ids.length > 0) {
        // 批量删除 - 用于按 drawing_session_id 回撤
        setElements(prev => prev.filter(el => !data.element_ids!.includes(el.id)));
      } else if (data.element_id) {
        // 单个删除 - 用于回撤最近一次绘制
        setElements(prev => prev.filter(el => el.id !== data.element_id));
      }
      // 如果退出了编辑模式，清除编辑状态
      if (editingGroupId) {
        exitGroupEditMode();
      }
    },
  });

  // Load canvas
  const loadCanvas = useCallback(async () => {
    try {
      const response = await canvasApi.loadCanvas(canvasId);
      if (response.success && response.canvas) {
        setCanvas(response.canvas);
        setElements(response.canvas.elements || []);
      }
    } catch (err) {
      console.error('Failed to load canvas:', err);
    }
  }, [canvasId]);

  useEffect(() => {
    loadCanvas();
  }, [loadCanvas]);

  // Auto-save via WebSocket
  useEffect(() => {
    if (!canvas) return;

    const saveInterval = setInterval(() => {
      // 通过 WebSocket 同步状态，后端会广播给所有客户端
      console.log('[AutoSave] Syncing via WebSocket, elements:', elements.length);
      syncState(elements);
      setLastSaved(new Date());
    }, 5000); // Auto-save every 5 seconds

    return () => clearInterval(saveInterval);
  }, [canvas, elements, syncState]);

  // Handle file drop
  const handleFileDrop = useCallback(async (files: File[], position: { x: number; y: number }) => {
    for (const file of files) {
      const extension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      let elementType = 'text';
      let metadata: any = {};

      // Determine element type by extension
      if (['.txt', '.md'].includes(extension)) {
        elementType = 'text';
        const text = await file.text();
        metadata.text_content = text;
        metadata.font_size = 16;
        metadata.font_family = 'Arial, sans-serif';
      } else if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(extension)) {
        elementType = 'image';
        // 先上传到 OSS 获取公开 URL
        const uploadResult = await canvasApi.uploadImage(file);
        if (uploadResult.success && uploadResult.url) {
          metadata.url = uploadResult.url;
          console.log('[Canvas] Image uploaded to OSS:', uploadResult.url);
        } else {
          // 如果上传失败，回退到 blob URL
          console.warn('[Canvas] OSS upload failed, using blob URL:', uploadResult.error);
          metadata.url = URL.createObjectURL(file);
        }
        metadata.mime_type = file.type;
      } else if (['.mp4', '.webm'].includes(extension)) {
        elementType = 'video';
        const url = URL.createObjectURL(file);
        metadata.url = url;
        metadata.mime_type = file.type;
      } else if (['.mp3', '.wav', '.ogg'].includes(extension)) {
        elementType = 'audio';
        const url = URL.createObjectURL(file);
        metadata.url = url;
        metadata.mime_type = file.type;
      }

      // Create new element
      const newElement: Omit<CanvasElementType, 'id' | 'created_at' | 'updated_at'> = {
        type: elementType,
        position: { x: position.x, y: position.y },
        size: {
          width: elementType === 'text' ? 300 : 200,
          height: elementType === 'text' ? 100 : 200,
        },
        z_index: elements.length + 1,
        locked: false,
        visible: true,
        metadata,
        styles: {
          x: position.x,
          y: position.y,
          width: elementType === 'text' ? 300 : 200,
          height: elementType === 'text' ? 100 : 200,
          rotation: 0,
          stroke_width: 1,
          opacity: 1,
          corner_radius: 0,
          shadow_enabled: false,
          shadow_blur: 0,
          shadow_offset_x: 0,
          shadow_offset_y: 0,
          blur: 0,
          brightness: 100,
          contrast: 100,
          bold: false,
          italic: false,
          underline: false,
        },
        created_by: 'user',
      };

      // Add element via API
      const response = await canvasApi.addElement(canvasId, newElement);
      if (response.success && response.element) {
        setElements(prev => [...prev, response.element!]);
      }
    }
  }, [canvasId, elements.length]);

  // Handle element selection
  const handleElementSelect = useCallback((elementId: string, addToSelection: boolean) => {
    if (addToSelection) {
      setSelectedIds(prev =>
        prev.includes(elementId)
          ? prev.filter(id => id !== elementId)
          : [...prev, elementId]
      );
    } else {
      setSelectedIds([elementId]);
    }
    setSelection(null);
  }, [elements]);

  // Handle selection change
  const handleSelectionChange = useCallback((newSelection: SelectionRegion | null) => {
    setSelection(newSelection);
    if (newSelection) {
      setSelectedIds(newSelection.element_ids);
    }
  }, []);

  // Helper function to find element at given coordinates
  const findElementAtPosition = useCallback((x: number, y: number): CanvasElementType | null => {
    // Search in reverse order (top elements first)
    for (let i = elements.length - 1; i >= 0; i--) {
      const el = elements[i];
      if (!el.visible || el.locked) continue;

      const { position, size } = el;
      if (
        x >= position.x &&
        x <= position.x + size.width &&
        y >= position.y &&
        y <= position.y + size.height
      ) {
        return el;
      }
    }
    return null;
  }, [elements]);

  // Handle canvas click (deselect or create element based on tool)
  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    // If in edit mode and clicking on canvas background (not an element), exit edit mode
    if (editingGroupId) {
      const target = e.target as HTMLElement;
      if (!target.closest('.canvas-element')) {
        // Clicking on canvas background - exit edit mode
        exitGroupEditMode();
        return;
      }
    }

    // Don't create new element if clicking on an element
    const target = e.target as HTMLElement;
    if (target.closest('.canvas-element')) {
      // When clicking on an element, just deselect (let element's own handler deal with it)
      setSelectedIds([]);
      setSelection(null);
      return;
    }

    // Clicking on canvas background - clear crop path display
    setCropPreview(null);

    // For selection tools (select, lasso, rect_select), clicking on background should NOT clear the current selection
    // The selection persists until: 1) user presses ESC, 2) user explicitly clears, or 3) user makes a new selection
    if (currentTool === 'select' || currentTool === 'lasso' || currentTool === 'rect_select') {
      return; // Don't clear selection for selection tools - keep it visible
    }

    // Only process shape tool for click-to-create; text tool uses drag
    if (currentTool !== 'shape') {
      // For other tools, just deselect
      setSelectedIds([]);
      setSelection(null);
      return;
    }

    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
    const y = (e.clientY - rect.top - canvasOffset.y) / zoom;
    console.log('[Canvas] Click position:', { x, y, currentTool });

    switch (currentTool) {
      case 'shape': {
        console.log('[Canvas] Creating shape element');
        // Create rectangle shape at click position
        const newElement: Omit<CanvasElementType, 'id' | 'created_at' | 'updated_at'> = {
          type: 'shape',
          position: { x: x - 50, y: y - 50 },
          size: { width: 100, height: 100 },
          z_index: elements.length + 1,
          locked: false,
          visible: true,
          metadata: {
            shape_type: 'rect',
          },
          styles: {
            x: 0, y: 0, width: 100, height: 100, rotation: 0,
            fill: '#3b82f6', stroke: '#1d4ed8', stroke_width: 2,
            opacity: 1, corner_radius: 0,
            shadow_enabled: false, shadow_blur: 0, shadow_offset_x: 0, shadow_offset_y: 0,
            blur: 0, brightness: 100, contrast: 100,
            bold: false, italic: false, underline: false,
          },
          created_by: 'user',
        };
        canvasApi.addElement(canvasId, newElement).then(response => {
          console.log('[Canvas] addElement response:', response);
          if (response.success && response.element) {
            setElements(prev => [...prev, response.element!]);
          }
        });
        break;
      }

      case 'image': {
        console.log('[Canvas] Image tool - triggering file input');
        // Trigger file input for image selection
        if (fileInputRef.current) {
          fileInputRef.current.click();
        }
        break;
      }

      default:
        // For select, lasso, rect_select, pan tools - just deselect
        setSelectedIds([]);
        setSelection(null);
    }
  }, [currentTool, elements.length, canvasOffset, zoom, canvasId, penColor, penWidth, editingGroupId, exitGroupEditMode]);

  // Handle element update
  const handleElementUpdate = useCallback(async (elementId: string, updates: Partial<CanvasElementType>) => {
    console.log('[CanvasWorkspace] handleElementUpdate:', { elementId, updates });
    setElements(prev => {
      console.log('[CanvasWorkspace] setElements, prev.length:', prev.length);
      return prev.map(el => {
        if (el.id !== elementId) return el;
        console.log('[CanvasWorkspace] Found element to update:', el.id);

        // Deep merge metadata if both have metadata
        const mergedMetadata = updates.metadata && el.metadata
          ? { ...el.metadata, ...updates.metadata }
          : updates.metadata || el.metadata;

        console.log('[CanvasWorkspace] mergedMetadata:', mergedMetadata);
        return { ...el, ...updates, metadata: mergedMetadata };
      });
    });

    // Persist to API
    console.log('[CanvasWorkspace] Calling API updateElement');
    await canvasApi.updateElement(canvasId, elementId, updates);
    console.log('[CanvasWorkspace] API updateElement done');
  }, [canvasId]);

  // Handle delete selected elements
  const handleDeleteSelected = useCallback(async () => {
    console.log('[CanvasWorkspace] handleDeleteSelected called, selectedIds:', selectedIds);
    // Prevent deletion during text editing or when no elements selected
    if (selectedIds.length === 0) return;

    try {
      await canvasApi.deleteElements(canvasId, selectedIds);
      setElements(prev => prev.filter(el => !selectedIds.includes(el.id)));
      setSelectedIds([]);
    } catch (err) {
      console.error('Failed to delete elements:', err);
    }
  }, [canvasId, selectedIds]);

  // Handle element move
  const handleElementMove = useCallback(async (elementId: string, position: { x: number; y: number }) => {
    setElements(prev =>
      prev.map(el =>
        el.id === elementId ? { ...el, position } : el
      )
    );

    // Persist to API
    await canvasApi.updateElement(canvasId, elementId, { position });
  }, [canvasId]);

  // Handle element resize
  const handleElementResize = useCallback(async (elementId: string, size: { width: number; height: number }) => {
    setElements(prev =>
      prev.map(el =>
        el.id === elementId ? { ...el, size } : el
      )
    );

    // Persist to API
    await canvasApi.updateElement(canvasId, elementId, { size });
  }, [canvasId]);

  // Handle save
  const handleSave = useCallback(async () => {
    try {
      setSaving(true);
      await canvasApi.saveElements(canvasId, elements);
      setLastSaved(new Date());
    } catch (err) {
      console.error('Save failed:', err);
    } finally {
      setSaving(false);
    }
  }, [canvasId, elements]);

  // Handle export
  const handleExport = useCallback(async () => {
    try {
      const blob = await canvasApi.exportCanvas(canvasId, 'json');
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${canvas?.name || 'canvas'}_${Date.now()}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    }
  }, [canvasId, canvas?.name]);

  // Handle image file selection
  const handleImageFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const rect = canvasContainerRef.current?.getBoundingClientRect();
    if (!rect) return;

    // Create image element at center of visible area
    const x = (rect.width / 2 - canvasOffset.x) / zoom;
    const y = (rect.height / 2 - canvasOffset.y) / zoom;

    // 先上传到 OSS 获取公开 URL
    let imageUrl = '';
    const uploadResult = await canvasApi.uploadImage(file);
    if (uploadResult.success && uploadResult.url) {
      imageUrl = uploadResult.url;
      console.log('[Canvas] Image uploaded to OSS:', uploadResult.url);
    } else {
      // 如果上传失败，回退到 data URL
      console.warn('[Canvas] OSS upload failed, using data URL:', uploadResult.error);
      imageUrl = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = (event) => resolve(event.target?.result as string);
        reader.readAsDataURL(file);
      });
    }

    const newElement: Omit<CanvasElementType, 'id' | 'created_at' | 'updated_at'> = {
      type: 'image',
      position: { x: x - 100, y: y - 100 },
      size: { width: 200, height: 200 },
      z_index: elements.length + 1,
      locked: false,
      visible: true,
      metadata: {
        url: imageUrl,
        mime_type: file.type,
      },
      styles: {
        x: 0, y: 0, width: 200, height: 200, rotation: 0,
        stroke_width: 0, opacity: 1, corner_radius: 0,
        shadow_enabled: false, shadow_blur: 0, shadow_offset_x: 0, shadow_offset_y: 0,
        blur: 0, brightness: 100, contrast: 100,
        bold: false, italic: false, underline: false,
      },
      created_by: 'user',
    };

    canvasApi.addElement(canvasId, newElement).then(response => {
      if (response.success && response.element) {
        setElements(prev => [...prev, response.element!]);
      }
    });

    // Reset input
    e.target.value = '';
  }, [canvasId, elements.length, canvasOffset, zoom]);

  // Handle zoom
  const handleZoom = useCallback((delta: number) => {
    setZoom(prev => Math.max(0.1, Math.min(5, prev + delta)));
  }, []);

  // Handle pan
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (currentTool === 'pan' || (e.button === 1 && currentTool === 'select')) {
      setIsPanning(true);
      setPanStart({ x: e.clientX - canvasOffset.x, y: e.clientY - canvasOffset.y });
      return;
    }

    // Pen tool - start drawing
    if (currentTool === 'pen') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      setIsDrawing(true);
      setCurrentPath([{ x, y }]);
      return;
    }

    // Smart crop tool - start drawing closed path
    if (currentTool === 'smart_crop') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      setIsDrawing(true);
      setCurrentPath([{ x, y }]);
      return;
    }

    // Group edit tool - start drawing closed path to select group
    if (currentTool === 'group_edit') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      console.log('[GroupEdit] Mouse down, starting path at:', { x, y });
      setIsDrawing(true);
      setCurrentPath([{ x, y }]);
      return;
    }

    // Eraser tool - find and delete element at click position
    if (currentTool === 'eraser') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      const elementToDelete = findElementAtPosition(x, y);
      if (elementToDelete) {
        setIsErasing(true);
        canvasApi.deleteElements(canvasId, [elementToDelete.id]).then(response => {
          if (response.success) {
            setElements(prev => prev.filter(el => el.id !== elementToDelete.id));
          }
        });
      }
      return;
    }

    // Text tool - start creating text box by dragging
    if (currentTool === 'text') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      setIsCreatingText(true);
      setTextPreview({ x, y, width: 0, height: 0 });
      return;
    }
  }, [currentTool, canvasOffset, zoom, findElementAtPosition, canvasId]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isPanning) {
      setCanvasOffset({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y,
      });
      return;
    }

    // Pen tool - continue drawing
    if (isDrawing && currentTool === 'pen') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      setCurrentPath(prev => [...prev, { x, y }]);
      return;
    }

    // Smart crop tool - continue drawing closed path
    if (isDrawing && currentTool === 'smart_crop') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      setCurrentPath(prev => [...prev, { x, y }]);
      return;
    }

    // Group edit tool - continue drawing closed path
    if (isDrawing && currentTool === 'group_edit') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      setCurrentPath(prev => [...prev, { x, y }]);
      return;
    }

    // Eraser tool - continue erasing while dragging
    if (isErasing && currentTool === 'eraser') {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      const elementToDelete = findElementAtPosition(x, y);
      if (elementToDelete) {
        canvasApi.deleteElements(canvasId, [elementToDelete.id]).then(response => {
          if (response.success) {
            setElements(prev => prev.filter(el => el.id !== elementToDelete.id));
          }
        });
      }
    }

    // Text tool - update text box preview while dragging
    if (isCreatingText && currentTool === 'text' && textPreview) {
      const rect = canvasContainerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const x = (e.clientX - rect.left - canvasOffset.x) / zoom;
      const y = (e.clientY - rect.top - canvasOffset.y) / zoom;

      // Calculate the rectangle from start point to current point
      const startX = textPreview.x;
      const startY = textPreview.y;
      const width = Math.abs(x - startX);
      const height = Math.abs(y - startY);
      const newX = Math.min(startX, x);
      const newY = Math.min(startY, y);

      setTextPreview({ x: newX, y: newY, width, height });
    }
  }, [isPanning, panStart, isDrawing, currentTool, canvasOffset, zoom, isErasing, isCreatingText, textPreview, findElementAtPosition, canvasId]);

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
    setIsErasing(false);

    // Pen tool - finish drawing
    if (isDrawing && currentTool === 'pen' && currentPath.length > 1) {
      // Calculate bounding box
      const minX = Math.min(...currentPath.map(p => p.x));
      const maxX = Math.max(...currentPath.map(p => p.x));
      const minY = Math.min(...currentPath.map(p => p.y));
      const maxY = Math.max(...currentPath.map(p => p.y));

      // Create shape element with path data
      const newElement: Omit<CanvasElementType, 'id' | 'created_at' | 'updated_at'> = {
        type: 'shape',
        position: { x: minX, y: minY },
        size: { width: Math.max(maxX - minX, 1), height: Math.max(maxY - minY, 1) },
        z_index: elements.length + 1,
        locked: false,
        visible: true,
        metadata: {
          shape_type: 'path',
          points: currentPath,
          // Normalize points relative to position
          normalized_points: currentPath.map(p => ({ x: p.x - minX, y: p.y - minY })),
        },
        styles: {
          x: 0, y: 0, width: Math.max(maxX - minX, 1), height: Math.max(maxY - minY, 1),
          rotation: 0, fill: 'transparent', stroke: penColor, stroke_width: penWidth,
          opacity: 1, corner_radius: 0,
          shadow_enabled: false, shadow_blur: 0, shadow_offset_x: 0, shadow_offset_y: 0,
          blur: 0, brightness: 100, contrast: 100,
          bold: false, italic: false, underline: false,
        },
        created_by: 'user',
      };

      canvasApi.addElement(canvasId, newElement).then(response => {
        if (response.success && response.element) {
          setElements(prev => [...prev, response.element!]);
          // Also send brush stroke via WebSocket for real-time sync
          sendBrushStroke(
            currentPath.map(p => [p.x, p.y]),
            penColor,
            penWidth,
            response.element.id
          );
        }
      });
    }

    // Smart crop tool - finish drawing and capture
    if (isDrawing && currentTool === 'smart_crop' && currentPath.length > 2) {
      console.log('[SmartCrop] Finishing smart crop, path length:', currentPath.length);
      // Check if path is closed - must be a true closed loop
      const firstPoint = currentPath[0];
      const lastPoint = currentPath[currentPath.length - 1];
      const distance = Math.sqrt(Math.pow(firstPoint.x - lastPoint.x, 2) + Math.pow(firstPoint.y - lastPoint.y, 2));
      // Use stricter threshold for true closure (12px)
      const isClosed = distance < 12;
      console.log('[SmartCrop] Path closed check:', { distance, isClosed, threshold: 12, firstPoint, lastPoint });

      if (isClosed) {
        console.log('[SmartCrop] Path is closed, starting capture');
        // Calculate bounding box
        const minX = Math.min(...currentPath.map(p => p.x));
        const maxX = Math.max(...currentPath.map(p => p.x));
        const minY = Math.min(...currentPath.map(p => p.y));
        const maxY = Math.max(...currentPath.map(p => p.y));
        const width = maxX - minX;
        const height = maxY - minY;
        console.log('[SmartCrop] Bounding box:', { minX, minY, width, height });

        // Validate minimum size
        if (width < 10 || height < 10) {
          console.log('[SmartCrop] FAILED - Crop area too small');
          setIsDrawing(false);
          setCurrentPath([]);
          return;
        }

        // Use native Canvas API to render elements directly for accurate capture
        console.log('[SmartCrop] Starting native Canvas capture...');

        // Create canvas matching full canvas size
        const captureCanvas = document.createElement('canvas');
        captureCanvas.width = canvas?.width || 1920;
        captureCanvas.height = canvas?.height || 1080;
        const ctx = captureCanvas.getContext('2d');
        if (!ctx) {
          console.log('[SmartCrop] FAILED - Could not get canvas context');
          setIsDrawing(false);
          setCurrentPath([]);
          return;
        }

        // Draw white background
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, captureCanvas.width, captureCanvas.height);

        // Helper to draw image from URL
        const drawImage = (img: HTMLImageElement, x: number, y: number, w: number, h: number) => {
          try {
            ctx.drawImage(img, x, y, w, h);
          } catch (e) {
            console.log('[SmartCrop] Failed to draw image at', x, y, e);
          }
        };

        // Sort elements by z_index to ensure proper layering (lower z_index renders first, under higher z_index)
        const sortedElements = [...elements].sort((a, b) => a.z_index - b.z_index);

        // Helper function to wrap text into multiple lines
        const wrapText = (text: string, maxWidth: number, fontSize: number, fontFamily: string): string[] => {
          const words = text.split('');
          const lines: string[] = [];
          let currentLine = '';

          // Create a temporary canvas to measure text width
          const measureCanvas = document.createElement('canvas');
          const measureCtx = measureCanvas.getContext('2d');
          if (!measureCtx) return [text];

          measureCtx.font = `${fontSize}px ${fontFamily}`;

          for (const char of words) {
            const testLine = currentLine + char;
            const metrics = measureCtx.measureText(testLine);
            if (metrics.width > maxWidth && currentLine.length > 0) {
              lines.push(currentLine);
              currentLine = char;
            } else {
              currentLine = testLine;
            }
          }
          if (currentLine.length > 0) {
            lines.push(currentLine);
          }
          return lines.length > 0 ? lines : [text];
        };

        // Render all elements with proper layering
        const renderPromises = sortedElements.map((element) => {
          return new Promise<void>((resolve) => {
            const elX = element.position.x;
            const elY = element.position.y;
            const elW = element.size.width;
            const elH = element.size.height;

            // Skip elements outside crop region
            if (elX + elW < minX || elX > maxX || elY + elH < minY || elY > maxY) {
              resolve();
              return;
            }

            if (element.type === 'image') {
              const img = new Image();
              img.crossOrigin = 'anonymous';
              img.onload = () => {
                drawImage(img, elX, elY, elW, elH);
                resolve();
              };
              img.onerror = () => {
                resolve();
              };
              // Handle proxy URLs
              let src = element.metadata.url || '';
              if (src.includes('aliyuncs.com')) {
                src = `http://localhost:8080/api/studio/proxy/image?url=${encodeURIComponent(src)}`;
              }
              img.src = src;
            } else if (element.type === 'text') {
              const fontSize = element.metadata.font_size || 16;
              const fontFamily = element.metadata.font_family || 'Arial, sans-serif';
              const textAlign = element.metadata.text_align || 'left';
              const color = element.styles.color || '#000000';
              const text = element.metadata.text_content || '';
              const lineHeight = element.metadata.line_height || 1.5;

              ctx.font = `${fontSize}px ${fontFamily}, "Microsoft YaHei", "PingFang SC", sans-serif`;
              ctx.textAlign = textAlign as CanvasTextAlign;
              ctx.fillStyle = color;

              // Calculate text position
              let textX = elX;
              if (textAlign === 'center') textX = elX + elW / 2;
              else if (textAlign === 'right') textX = elX + elW;

              // Wrap text into multiple lines
              const lines = wrapText(text, elW, fontSize, fontFamily);
              const actualLineHeight = fontSize * lineHeight;

              // Draw each line of text
              lines.forEach((line, lineIndex) => {
                const lineY = elY + fontSize + (lineIndex * actualLineHeight);
                ctx.fillText(line, textX, lineY);
              });
              resolve();
            } else if (element.type === 'shape') {
              const stroke = element.styles.stroke || '#000000';
              const strokeWidth = element.styles.stroke_width || 1;
              // 与流式绘制保持一致：fill 默认为 'none'
              const fill = element.styles.fill || 'none';

              ctx.strokeStyle = stroke;
              ctx.lineWidth = strokeWidth;
              ctx.fillStyle = fill;

              if (element.metadata.shape_type === 'path' && element.metadata.points) {
                ctx.beginPath();
                element.metadata.points.forEach((point: {x: number, y: number}, i: number) => {
                  if (i === 0) ctx.moveTo(point.x, point.y);
                  else ctx.lineTo(point.x, point.y);
                });
                ctx.stroke();
                // 与流式绘制保持一致：只有 fill 有值且不是 'none' 时才填充
                if (fill && fill !== 'none') {
                  ctx.fill();
                }
              } else {
                ctx.strokeRect(elX, elY, elW, elH);
              }
              resolve();
            } else {
              resolve();
            }
          });
        });

        Promise.all(renderPromises).then(() => {
          // Re-draw text elements ON TOP of everything to ensure they're visible (fix for async image loading)
          const textElements = sortedElements.filter(el => el.type === 'text' && el.position.x + el.size.width >= minX && el.position.x <= maxX && el.position.y + el.size.height >= minY && el.position.y <= maxY);
          textElements.forEach(element => {
            const elX = element.position.x;
            const elY = element.position.y;
            const elW = element.size.width;
            const fontSize = element.metadata.font_size || 16;
            const fontFamily = element.metadata.font_family || 'Arial, sans-serif';
            const textAlign = element.metadata.text_align || 'left';
            const color = element.styles.color || '#000000';
            const text = element.metadata.text_content || '';
            const lineHeight = element.metadata.line_height || 1.5;

            ctx.font = `${fontSize}px ${fontFamily}, "Microsoft YaHei", "PingFang SC", sans-serif`;
            ctx.textAlign = textAlign as CanvasTextAlign;
            ctx.fillStyle = color;

            let textX = elX;
            if (textAlign === 'center') textX = elX + elW / 2;
            else if (textAlign === 'right') textX = elX + elW;

            const actualLineHeight = fontSize * lineHeight;
            const lines = wrapText(text, elW, fontSize, fontFamily);
            lines.forEach((line, lineIndex) => {
              const lineY = elY + fontSize + (lineIndex * actualLineHeight);
              ctx.fillText(line, textX, lineY);
            });
          });

          // Create temporary canvas for final crop
          const tempCanvas = document.createElement('canvas');
          tempCanvas.width = width;
          tempCanvas.height = height;
          const tempCtx = tempCanvas.getContext('2d');
          if (!tempCtx) {
            console.log('[SmartCrop] FAILED - Could not get temp canvas context');
            setIsDrawing(false);
            setCurrentPath([]);
            return;
          }

          // Draw cropped region using the actual drawing path for clipping
          tempCtx.save();
          // Create path from currentPath for clipping
          tempCtx.beginPath();
          currentPath.forEach((p, i) => {
            const x = p.x - minX;
            const y = p.y - minY;
            if (i === 0) tempCtx.moveTo(x, y);
            else tempCtx.lineTo(x, y);
          });
          tempCtx.closePath();
          tempCtx.clip();

          // Draw the captured canvas region (only the part inside the path will be visible due to clipping)
          tempCtx.drawImage(
            captureCanvas,
            minX, minY, width, height,
            0, 0, width, height
          );
          tempCtx.restore();

          // Convert to blob and upload
          tempCanvas.toBlob(async (blob) => {
            if (blob) {
                  const file = new File([blob], 'smart_crop.png', { type: 'image/png' });
                  try {
                    const uploadResponse = await canvasApi.uploadImage(file);
                    if (uploadResponse.success && uploadResponse.url) {
                      // Store the crop path as RELATIVE coordinates (relative to element top-left)
                      // This way it will work correctly even when element moves
                      const cropPathRelative = currentPath.map(p => ({
                        x: p.x - minX,
                        y: p.y - minY
                      }));

                      // Create image element at the crop position
                      const newElement: Omit<CanvasElementType, 'id' | 'created_at' | 'updated_at'> = {
                        type: 'image',
                        position: { x: minX, y: minY },
                        size: { width, height },
                        z_index: elements.length + 1,
                        locked: false,
                        visible: true,
                        metadata: {
                          url: uploadResponse.url,
                          mime_type: 'image/png',
                          crop_path: cropPathRelative, // Store as RELATIVE coordinates
                          crop_original_width: width, // Store original dimensions for scaling
                          crop_original_height: height,
                        },
                        styles: {
                          x: 0, y: 0, width, height, rotation: 0,
                          stroke_width: 1, opacity: 1, corner_radius: 0,
                          shadow_enabled: false, shadow_blur: 0, shadow_offset_x: 0, shadow_offset_y: 0,
                          blur: 0, brightness: 100, contrast: 100,
                          bold: false, italic: false, underline: false,
                        },
                        created_by: 'user',
                      };

                      const addResponse = await canvasApi.addElement(canvasId, newElement);
                      if (addResponse.success && addResponse.element) {
                        setElements(prev => [...prev, addResponse.element!]);
                        // Show crop preview feedback (dashed border) - success
                        // For immediate display, use relative path directly since element is at minX, minY
                        setCropPreview({ x: minX, y: minY, width, height, success: true, path: cropPathRelative });
                        // Keep the dashed border visible while element is selected (don't auto-hide)
                      } else {
                        // Show failure feedback
                        setCropPreview({ x: minX, y: minY, width, height, success: false, path: cropPathRelative });
                        setTimeout(() => setCropPreview(null), 1500);
                      }
                    }
                  } catch (error) {
                    console.error('Smart crop failed:', error);
                  }
                }
              }, 'image/png');
          })
        } else {
        // Path not closed - show failure feedback
        console.log('[SmartCrop] FAILED - Path not closed, distance:', distance);

        // Calculate bounding box for feedback
        const minX = Math.min(...currentPath.map(p => p.x));
        const maxX = Math.max(...currentPath.map(p => p.x));
        const minY = Math.min(...currentPath.map(p => p.y));
        const maxY = Math.max(...currentPath.map(p => p.y));
        const width = maxX - minX;
        const height = maxY - minY;

        // Show failure feedback with red dashed border
        setCropPreview({ x: minX, y: minY, width, height, success: false, path: [...currentPath] });
        setTimeout(() => setCropPreview(null), 1500);
      }
    }

    setIsDrawing(false);
    setCurrentPath([]);

    // Text tool - finish creating text box
    if (isCreatingText && currentTool === 'text' && textPreview && textPreview.width > 10 && textPreview.height > 10) {
      const newElement: Omit<CanvasElementType, 'id' | 'created_at' | 'updated_at'> = {
        type: 'text',
        position: { x: textPreview.x, y: textPreview.y },
        size: { width: textPreview.width, height: textPreview.height },
        z_index: elements.length + 1,
        locked: false,
        visible: true,
        metadata: {
          text_content: '双击编辑文本',
          font_size: 16,
          font_family: 'Arial, sans-serif',
          text_align: 'left',
        },
        styles: {
          x: 0, y: 0, width: textPreview.width, height: textPreview.height, rotation: 0,
          stroke_width: 1, opacity: 1, corner_radius: 0,
          shadow_enabled: false, shadow_blur: 0, shadow_offset_x: 0, shadow_offset_y: 0,
          blur: 0, brightness: 100, contrast: 100,
          bold: false, italic: false, underline: false,
        },
        created_by: 'user',
      };

      canvasApi.addElement(canvasId, newElement).then(response => {
        if (response.success && response.element) {
          setElements(prev => [...prev, response.element!]);
        }
      });
    }

    // Group edit tool - check if drawn path encloses a group
    if (isDrawing && currentTool === 'group_edit' && currentPath.length > 2) {
      console.log('[GroupEdit] Finishing group edit selection, path length:', currentPath.length);

      // Check if path is closed
      const firstPoint = currentPath[0];
      const lastPoint = currentPath[currentPath.length - 1];
      const distance = Math.sqrt(Math.pow(firstPoint.x - lastPoint.x, 2) + Math.pow(firstPoint.y - lastPoint.y, 2));
      const isClosed = distance < 20; // 20px threshold for closing

      console.log('[GroupEdit] Path closed check:', { distance, isClosed, threshold: 20 });
      showEditModeMessage('🔍 正在检查圈住的组合...');

      if (isClosed) {
        // Calculate bounding box of the drawn path
        const minX = Math.min(...currentPath.map(p => p.x));
        const maxX = Math.max(...currentPath.map(p => p.x));
        const minY = Math.min(...currentPath.map(p => p.y));
        const maxY = Math.max(...currentPath.map(p => p.y));

        console.log('[GroupEdit] Selection bounding box:', { minX, minY, maxX, maxY });
        console.log('[GroupEdit] Total elements to check:', elements.length);

        // Find groups that are fully enclosed by the drawn path
        const enclosedGroups = elements.filter(el => {
          // Only check group elements (have child_ids)
          if (!el.metadata?.child_ids || el.metadata.child_ids.length === 0) {
            return false;
          }

          // Group must be fully enclosed (simplified check - just check if center is inside)
          const centerX = el.position.x + el.size.width / 2;
          const centerY = el.position.y + el.size.height / 2;

          // More accurate: check if center is inside the path (point-in-polygon)
          const isInside = isPointInPolygon(centerX, centerY, currentPath);

          console.log('[GroupEdit] Checking group:', el.id, {
            type: el.type,
            centerX, centerY,
            elBounds: { x: el.position.x, y: el.position.y, w: el.size.width, h: el.size.height },
            childIds: el.metadata.child_ids,
            isInsidePath: isInside
          });

          return isInside;
        });

        console.log('[GroupEdit] Found enclosed groups:', enclosedGroups.length);

        console.log('[GroupEdit] Found enclosed groups:', enclosedGroups.length);

        if (enclosedGroups.length > 0) {
          // Enter edit mode for the first enclosed group
          enterGroupEditMode(enclosedGroups[0].id);
        } else {
          // No groups found - check if path was closed
          if (isClosed) {
            showEditModeMessage('⚠️ 圈住的区域没有组合，请圈住一个组合元素');
          }
        }
      } else {
        showEditModeMessage('⚠️ 路径未封闭，请画一个封闭的圈');
      }
    }

    setIsCreatingText(false);
    setTextPreview(null);
  }, [isDrawing, currentTool, currentPath, elements.length, canvasId, penColor, penWidth, isCreatingText, textPreview, canvasContentRef, enterGroupEditMode, showEditModeMessage]);

  // Handle chat message
  const handleSendMessage = useCallback(async (message: string, imageUrls?: string[]) => {
    const userMessage: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
      imageUrls: imageUrls,
    };

    setChatMessages(prev => [...prev, userMessage]);
    setIsTyping(true);

    try {
      // Call AI chat API with selection context and image URLs
      const response = await canvasApi.chat(
        canvasId,
        message,
        [],
        selection ? {
          type: selection.type,
          bounds: selection.bounds,
          element_ids: selection.element_ids,
          lasso: selection.lasso,
        } : undefined,
        chatSessionId || undefined,  // 传递 session_id 以保持对话历史
        imageUrls  // 传递图片 URL 列表以支持多模态识别
      );

      // 保存 session_id 用于后续请求
      if (response.session_id) {
        setChatSessionId(response.session_id);
      }

      // 更新 agent 模式
      if (response.agent_mode) {
        setAgentMode(response.agent_mode);
        console.log('[Chat] Agent mode:', response.agent_mode);
      }

      // 检查是否需要用户确认模式切换
      if (response.needs_confirm && response.confirm_type) {
        console.log('[Chat] Needs confirm:', response.confirm_type, 'confidence:', response.route_confidence);
        setModeConfirmType(response.confirm_type);
        setModeConfirmConfidence(response.route_confidence || 0);
        setModeConfirmReason(response.route_reason || '');
        setShowModeConfirm(true);
      }

      const aiMessage: ChatMessage = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: response.message || response.error || '抱歉，发生了错误。',
        timestamp: new Date().toISOString(),
      };

      setChatMessages(prev => [...prev, aiMessage]);

      console.log('[Chat] Response:', response.message || response.error);

      // 从响应中获取最新 elements 并更新
      if (response.elements && response.elements.length > 0) {
        console.log('[Chat] Updating elements from response, count:', response.elements.length);
        setElements(response.elements);
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: ChatMessage = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: '抱歉，发生了网络错误，请稍后重试。',
        timestamp: new Date().toISOString(),
      };
      setChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  }, [canvasId, selection]);

  // Handle stop button click - interrupt ongoing agent operation
  const handleStop = useCallback(() => {
    console.log('[Canvas] Stop button clicked');
    sendStopMessage();
    setIsTyping(false);
  }, [sendStopMessage]);

  // Handle mode switch confirmation
  const handleModeSwitchConfirm = useCallback(async () => {
    if (!modeConfirmType || !chatSessionId) return;

    console.log('[Canvas] Confirming mode switch to:', modeConfirmType);

    try {
      const response = await canvasApi.confirmModeSwitch(canvasId, chatSessionId, modeConfirmType);

      if (response.success) {
        console.log('[Canvas] Mode switch success:', response.agent_mode);
        if (response.agent_mode) {
          setAgentMode(response.agent_mode);
        }
        // 添加系统消息
        const sysMessage: ChatMessage = {
          id: `msg_${Date.now()}`,
          role: 'assistant',
          content: `【系统】已切换到${modeConfirmType === 'planning' ? '规划' : '工作'}模式`,
          timestamp: new Date().toISOString(),
        };
        setChatMessages(prev => [...prev, sysMessage]);
      } else {
        console.error('[Canvas] Mode switch failed:', response.error);
        const errorMessage: ChatMessage = {
          id: `msg_${Date.now()}`,
          role: 'assistant',
          content: `【系统】模式切换失败: ${response.error}`,
          timestamp: new Date().toISOString(),
        };
        setChatMessages(prev => [...prev, errorMessage]);
      }
    } catch (error) {
      console.error('[Canvas] Mode switch error:', error);
    } finally {
      setShowModeConfirm(false);
      setModeConfirmType('');
      setModeConfirmConfidence(0);
      setModeConfirmReason('');
    }
  }, [canvasId, chatSessionId, modeConfirmType]);

  // Handle mode switch cancel
  const handleModeSwitchCancel = useCallback(() => {
    console.log('[Canvas] Mode switch cancelled');
    setShowModeConfirm(false);
    setModeConfirmType('');
    setModeConfirmConfidence(0);
    setModeConfirmReason('');
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keyboard events when typing in input/textarea
      const target = e.target as HTMLElement;
      if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT' || target.isContentEditable) {
        return;
      }

      // Tool shortcuts
      switch (e.key.toLowerCase()) {
        case 'v':
          setCurrentTool('select');
          break;
        case 'l':
          setCurrentTool('lasso');
          break;
        case 'r':
          setCurrentTool('rect_select');
          break;
        case 'h':
          setCurrentTool('pan');
          break;
        case 't':
          setCurrentTool('text');
          break;
        case 's':
          setCurrentTool('shape');
          break;
        case 'i':
          setCurrentTool('image');
          break;
        case 'p':
          setCurrentTool('pen');
          break;
        case 'e':
          setCurrentTool('eraser');
          break;
        case 'c':
          setCurrentTool('smart_crop');
          break;
        case 'x':
          setCurrentTool('group_edit');
          break;
        case 'delete':
        case 'backspace':
          if (selectedIds.length > 0) {
            handleDeleteSelected();
          }
          break;
        case 'escape':
          // 如果在编辑模式，退出编辑模式
          if (editingGroupId) {
            exitGroupEditMode();
          } else {
            setSelectedIds([]);
            setSelection(null);
          }
          break;
      }

      // Zoom shortcuts
      if ((e.ctrlKey || e.metaKey) && e.key === '=') {
        e.preventDefault();
        handleZoom(0.1);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '-') {
        e.preventDefault();
        handleZoom(-0.1);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '0') {
        e.preventDefault();
        setZoom(1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedIds, handleZoom, editingGroupId, exitGroupEditMode, elements]);

  // Exit edit mode when switching tools (except select and group_edit tools)
  useEffect(() => {
    if (editingGroupId && currentTool !== 'select' && currentTool !== 'group_edit') {
      exitGroupEditMode();
    }
  }, [currentTool, editingGroupId, exitGroupEditMode]);

  return (
    <div className="h-screen flex flex-col bg-slate-100 overflow-hidden">
      {/* Hidden file input for image uploads */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleImageFileSelect}
      />

      {/* Header */}
      <header className="flex-shrink-0 bg-white border-b border-slate-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={onBack}
              className="flex items-center gap-2 px-3 py-1.5 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              <span className="text-sm font-medium">返回</span>
            </button>
            <div className="h-6 w-px bg-slate-200" />
            <h1 className="text-base font-semibold text-slate-800">
              {canvas?.name || '加载中...'}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-3 py-1.5 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
              </svg>
              <span className="text-sm font-medium">{saving ? '保存中...' : '保存'}</span>
            </button>
            {/* 完成绘图按钮 - 将当前绘画会话的元素分组 */}
            <button
              onClick={async () => {
                try {
                  const response = await canvasApi.resetDrawingSession(canvasId);
                  if (response.success) {
                    showEditModeMessage('✅ 绘图已完成，元素已分组');
                    // 重新加载画板以获取分组的元素
                    loadCanvas();
                  } else {
                    showEditModeMessage('⚠️ ' + (response.error || '分组失败'));
                  }
                } catch (err) {
                  console.error('[Canvas] Failed to finish drawing:', err);
                  showEditModeMessage('⚠️ 分组失败');
                }
              }}
              className="flex items-center gap-2 px-3 py-1.5 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm font-medium">完成绘图</span>
            </button>
            {/* WebSocket 连接状态 */}
            <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${isConnected ? 'text-green-600 bg-green-50' : 'text-red-600 bg-red-50'}`}>
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span>{isConnected ? '实时同步' : '离线'}</span>
            </div>
            <button
              onClick={handleExport}
              className="flex items-center gap-2 px-3 py-1.5 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              <span className="text-sm font-medium">导出</span>
            </button>
            <button className="p-1.5 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Toolbar */}
        <LeftToolbar
          collapsed={leftToolbarCollapsed}
          onToggle={() => setLeftToolbarCollapsed(!leftToolbarCollapsed)}
          currentTool={currentTool}
          onToolChange={setCurrentTool}
        />

        {/* Canvas Area */}
        <div className="flex-1 relative overflow-hidden">
          <CanvasDropZone
            onFileDrop={handleFileDrop}
            disabled={currentTool === 'lasso' || currentTool === 'rect_select'}
          >
            <div
              ref={canvasContainerRef}
              className="w-full h-full overflow-hidden"
              style={{ cursor: currentTool === 'pan' || isPanning ? 'grab' : 'default' }}
              onClick={handleCanvasClick}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              {/* Canvas content */}
              <div
                ref={canvasContentRef}
                className="relative bg-white shadow-xl"
                style={{
                  width: canvas?.width || 1920,
                  height: canvas?.height || 1080,
                  transform: `translate(${canvasOffset.x}px, ${canvasOffset.y}px) scale(${zoom})`,
                  transformOrigin: '0 0',
                }}
              >
                {/* Canvas background */}
                <div
                  className="absolute inset-0"
                  style={{ backgroundColor: canvas?.background_color || '#ffffff' }}
                />

                {/* Grid pattern */}
                <div
                  className="absolute inset-0 pointer-events-none opacity-30"
                  style={{
                    backgroundImage: `
                      linear-gradient(to right, #e5e7eb 1px, transparent 1px),
                      linear-gradient(to bottom, #e5e7eb 1px, transparent 1px)
                    `,
                    backgroundSize: '20px 20px',
                  }}
                />

                {/* Selection overlay - inside transformed div */}
                <SelectionOverlay
                  elements={elements}
                  selection={selection}
                  onSelectionChange={handleSelectionChange}
                  toolType={currentTool as 'select' | 'lasso' | 'rect_select'}
                  canvasOffset={{ x: 0, y: 0 }}
                  zoom={1}
                />

                {/* Elements */}
                {elements.map((element) => (
                  <CanvasElement
                    key={element.id}
                    element={element}
                    isSelected={selectedIds.includes(element.id)}
                    onSelect={handleElementSelect}
                    onElementUpdate={handleElementUpdate}
                    onElementMove={handleElementMove}
                    onElementResize={handleElementResize}
                  />
                ))}

                {/* Streaming painting elements (AI drawing in progress) */}
                {Object.entries(streamingElements).map(([itemId, data]) => (
                  <svg
                    key={itemId}
                    className="absolute pointer-events-none"
                    style={{
                      left: data.x,
                      top: data.y,
                      overflow: 'visible',
                    }}
                  >
                    <path
                      d={data.points.reduce((d, point, i) => {
                        if (i === 0) return `M ${point[0]} ${point[1]}`;
                        return `${d} L ${point[0]} ${point[1]}`;
                      }, '')}
                      fill={data.fill_color || 'none'}
                      stroke={data.stroke_color}
                      strokeWidth={data.stroke_width}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      opacity={0.9}
                    />
                  </svg>
                ))}

                {/* Drawing preview for pen tool */}
                {isDrawing && currentPath.length > 0 && (
                  <svg
                    className="absolute inset-0 pointer-events-none"
                    style={{
                      width: canvas?.width || 1920,
                      height: canvas?.height || 1080,
                      overflow: 'visible',
                    }}
                  >
                    {/* Smart crop shows open path until closed */}
                    {currentTool === 'smart_crop' ? (
                      <>
                        {/* Open path - no Z command */}
                        <path
                          d={currentPath.reduce((d, point, i) => {
                            if (i === 0) return `M ${point.x} ${point.y}`;
                            return `${d} L ${point.x} ${point.y}`;
                          }, '')}
                          fill="rgba(99, 102, 241, 0.05)"
                          stroke="#6366f1"
                          strokeWidth={2}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        {/* Start point indicator */}
                        <circle
                          cx={currentPath[0].x}
                          cy={currentPath[0].y}
                          r={5}
                          fill="#6366f1"
                        />
                      </>
                    ) : currentTool === 'group_edit' ? (
                      /* Group edit tool - dashed indigo line */
                      <>
                        <path
                          d={currentPath.reduce((d, point, i) => {
                            if (i === 0) return `M ${point.x} ${point.y}`;
                            return `${d} L ${point.x} ${point.y}`;
                          }, '')}
                          fill="rgba(99, 102, 241, 0.1)"
                          stroke="#6366f1"
                          strokeWidth={2}
                          strokeDasharray="8 4"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        {/* Start point indicator */}
                        <circle
                          cx={currentPath[0].x}
                          cy={currentPath[0].y}
                          r={5}
                          fill="#6366f1"
                        />
                        {/* End point indicator */}
                        <circle
                          cx={currentPath[currentPath.length - 1].x}
                          cy={currentPath[currentPath.length - 1].y}
                          r={5}
                          fill="#6366f1"
                        />
                      </>
                    ) : (
                      /* Regular pen tool path */
                      <path
                        d={currentPath.reduce((d, point, i) => {
                          if (i === 0) return `M ${point.x} ${point.y}`;
                          return `${d} L ${point.x} ${point.y}`;
                        }, '')}
                        fill="none"
                        stroke={penColor}
                        strokeWidth={penWidth}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    )}
                  </svg>
                )}

                {/* Text box preview for text tool */}
                {isCreatingText && textPreview && (
                  <div
                    className="absolute pointer-events-none border-2 border-indigo-500 bg-indigo-50 bg-opacity-50"
                    style={{
                      left: textPreview.x,
                      top: textPreview.y,
                      width: textPreview.width,
                      height: textPreview.height,
                    }}
                  >
                    <div className="w-full h-full flex items-center justify-center text-slate-400 text-sm">
                      拖动创建文本框
                    </div>
                  </div>
                )}

                {/* Smart crop preview - dashed border for selected elements with crop_path */}
                {selectedIds.length > 0 && (
                  <svg
                    className="absolute pointer-events-none"
                    style={{
                      left: 0,
                      top: 0,
                      width: '100%',
                      height: '100%',
                      overflow: 'visible',
                      zIndex: 9999,
                    }}
                  >
                    {selectedIds.map(elementId => {
                      const selectedElement = elements.find(el => el.id === elementId);
                      if (!selectedElement || !selectedElement.metadata) return null;
                      const cropPath = (selectedElement.metadata as any).crop_path;
                      const cropOriginalW = (selectedElement.metadata as any).crop_original_width || selectedElement.size.width;
                      const cropOriginalH = (selectedElement.metadata as any).crop_original_height || selectedElement.size.height;
                      if (!cropPath || !Array.isArray(cropPath) || cropPath.length === 0) return null;

                      // Path is stored as RELATIVE coordinates, convert to absolute using element's current position and scale
                      const elX = selectedElement.position.x;
                      const elY = selectedElement.position.y;
                      const elW = selectedElement.size.width;
                      const elH = selectedElement.size.height;

                      // Calculate scale factors
                      const scaleX = cropOriginalW > 0 ? elW / cropOriginalW : 1;
                      const scaleY = cropOriginalH > 0 ? elH / cropOriginalH : 1;

                      return (
                        <g key={elementId}>
                          {/* Convert relative path coordinates to absolute SVG path string */}
                          {/* White outline for better visibility */}
                          <path
                            d={cropPath.map((p: { x: number; y: number }, i: number) => {
                              const absX = elX + p.x * scaleX;
                              const absY = elY + p.y * scaleY;
                              return `${i === 0 ? 'M' : 'L'} ${absX} ${absY}`;
                            }).join(' ') + ' Z'}
                            fill="none"
                            stroke="white"
                            strokeWidth={Math.max(2, 3 / Math.min(scaleX, scaleY))}
                            strokeDasharray="8 4"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                          {/* Green dashed line */}
                          <path
                            d={cropPath.map((p: { x: number; y: number }, i: number) => {
                              const absX = elX + p.x * scaleX;
                              const absY = elY + p.y * scaleY;
                              return `${i === 0 ? 'M' : 'L'} ${absX} ${absY}`;
                            }).join(' ') + ' Z'}
                            fill="none"
                            stroke="#22c55e"
                            strokeWidth={Math.max(1.5, 2 / Math.min(scaleX, scaleY))}
                            strokeDasharray="8 4"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </g>
                      );
                    })}
                  </svg>
                )}
              </div>
            </div>
          </CanvasDropZone>

          {/* Edit mode message toast */}
          {editModeMessage && (
            <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-50 bg-indigo-600 text-white px-6 py-3 rounded-lg shadow-lg text-sm font-medium">
              {editModeMessage}
            </div>
          )}

          {/* Zoom controls */}
          <div className="absolute bottom-4 left-4 flex items-center gap-2 bg-white rounded-lg shadow-md px-3 py-2">
            <button
              onClick={() => handleZoom(-0.1)}
              className="p-1 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
              </svg>
            </button>
            <span className="text-sm text-slate-600 min-w-[50px] text-center">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => handleZoom(0.1)}
              className="p-1 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
            <button
              onClick={() => setZoom(1)}
              className="p-1 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
            </button>
          </div>
        </div>

        {/* Right Panel */}
        <RightPanel
          collapsed={rightPanelCollapsed}
          onToggle={() => setRightPanelCollapsed(!rightPanelCollapsed)}
          messages={chatMessages}
          onSendMessage={handleSendMessage}
          onStop={handleStop}
          isTyping={isTyping}
        />
      </div>

      {/* Status Bar */}
      <footer className="flex-shrink-0 bg-white border-t border-slate-200 px-4 py-2">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-4">
            <span>
              {saving ? '保存中...' : lastSaved ? `已保存 ${lastSaved.toLocaleTimeString('zh-CN')}` : '未保存'}
            </span>
            <span>|</span>
            <span>元素数量：{elements.length}</span>
          </div>
          <div className="flex items-center gap-4">
            {/* Agent 模式指示器 */}
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                agentMode === 'daily' ? 'bg-green-500' :
                agentMode === 'planning' ? 'bg-yellow-500' :
                agentMode === 'working' ? 'bg-blue-500' : 'bg-gray-500'
              }`}></span>
              <span>Agent: {
                agentMode === 'daily' ? '日常模式' :
                agentMode === 'planning' ? '规划模式' :
                agentMode === 'working' ? '工作模式' : agentMode
              }</span>
            </div>
            <span>|</span>
            <span>缩放：{Math.round(zoom * 100)}%</span>
            <span>|</span>
            <span>画布：{canvas?.width || 1920} x {canvas?.height || 1080}</span>
          </div>
        </div>
      </footer>

      {/* Mode Switch Confirmation Dialog */}
      {showModeConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-100">
              <h3 className="text-lg font-semibold text-slate-800">
                确认切换到{modeConfirmType === 'planning' ? '规划' : '工作'}模式
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                AI 路由判断您可能需要{modeConfirmType === 'planning' ? '进行绘图规划' : '执行任务'}
              </p>
            </div>

            {/* Content */}
            <div className="px-6 py-4">
              <div className="bg-slate-50 rounded-lg p-4 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-500">路由置信度</span>
                  <span className="text-sm font-medium text-slate-700">
                    {(modeConfirmConfidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-gradient-to-r from-rose-500 to-pink-500 h-2 rounded-full transition-all"
                    style={{ width: `${modeConfirmConfidence * 100}%` }}
                  />
                </div>
              </div>

              {modeConfirmReason && (
                <p className="text-sm text-slate-600">
                  <span className="font-medium">判断理由：</span>
                  {modeConfirmReason}
                </p>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
              <button
                onClick={handleModeSwitchCancel}
                className="px-4 py-2 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors text-sm font-medium"
              >
                取消
              </button>
              <button
                onClick={handleModeSwitchConfirm}
                className="px-5 py-2 bg-gradient-to-r from-rose-500 to-pink-600 hover:from-rose-600 hover:to-pink-700 text-white text-sm font-medium rounded-lg transition-all flex items-center gap-2 shadow-lg shadow-rose-200"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                确认切换
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CanvasWorkspace;
