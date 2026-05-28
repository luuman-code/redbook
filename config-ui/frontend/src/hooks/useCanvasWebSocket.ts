// useCanvasWebSocket Hook - 画板WebSocket连接管理
// 基于现有的 useWebSocket.ts 扩展

import { useState, useEffect, useCallback, useRef } from 'react';

export type WSMessageType =
  | 'REPORT_OPERATION'
  | 'OPERATION_ACK'
  | 'SUGGESTION'
  | 'AGENT_ACTION'
  | 'CANVAS_UPDATE'
  | 'PING'
  | 'PONG'
  | 'ERROR'
  | 'DRAW_START'
  | 'DRAW_PROGRESS'
  | 'DRAW_COMPLETE'
  | 'DRAW_ERROR'
  | 'DRAW_UNDO';

export interface CanvasUpdateData {
  canvas_id: string;
  elements?: any[];
  operations?: any[];
}

export interface WSAckData {
  operation_id: string;
  success: boolean;
  error?: string;
}

export interface CanvasSuggestion {
  type: 'suggestion';
  content: string;
  suggestions?: string[];
}

export interface CanvasAgentAction {
  type: 'agent_action';
  actions: any[];
  message?: string;
}

export type WSResponse =
  | { type: 'OPERATION_ACK'; data: WSAckData }
  | { type: 'SUGGESTION'; data: CanvasSuggestion }
  | { type: 'AGENT_ACTION'; data: CanvasAgentAction }
  | { type: 'CANVAS_UPDATE'; data: CanvasUpdateData }
  | { type: 'PONG' }
  | { type: 'ERROR'; data: { error: string } };

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

export const OperationTypes = {
  CREATE: 'create',
  DELETE: 'delete',
  UPDATE: 'update',
  MOVE: 'move',
  RESIZE: 'resize',
  ROTATE: 'rotate',
  STYLE: 'style',
  GROUP: 'group',
  UNGROUP: 'ungroup',
  PASTE: 'paste',
  DUPLICATE: 'duplicate',
  ALIGN: 'align',
  TEXT_EDIT: 'text_edit',
  LASSO_SELECT: 'lasso_select',
  ELEMENT_SELECT: 'element_select',
} as const;

export type OperationType = typeof OperationTypes[keyof typeof OperationTypes];

export function createCanvasOperation(
  type: OperationType | string,
  targetIds: string[],
  afterState: Record<string, any>,
  beforeState: Record<string, any> = {},
  creator: 'user' | 'agent' = 'user',
  description: string = ''
): CanvasOperation {
  return {
    id: `op_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    type,
    target_ids: targetIds,
    before_state: beforeState,
    after_state: afterState,
    timestamp: new Date().toISOString(),
    creator,
    description,
  };
}

export interface UseCanvasWebSocketOptions {
  canvasId: string;
  userId?: string;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  onOperationAck?: (data: WSAckData) => void;
  onSuggestion?: (data: CanvasSuggestion) => void;
  onAgentAction?: (data: CanvasAgentAction) => void;
  onCanvasUpdate?: (data: CanvasUpdateData) => void;
  onDrawStart?: (data: { item_id: string; item_type: string }) => void;
  onDrawProgress?: (data: { item_id: string; points: number[][];
                            stroke_color: string; stroke_width: number; done: boolean }) => void;
  onDrawComplete?: (data: { item_id: string; element: any }) => void;
  onDrawError?: (data: { item_id: string; error: string }) => void;
  onDrawUndo?: (data: { element_id?: string; element_ids?: string[]; reason: string }) => void;
}

export interface UseCanvasWebSocketReturn {
  isConnected: boolean;
  sendOperation: (operation: CanvasOperation, expectResponse?: boolean) => void;
  syncState: (elements: any[]) => void;
  sendBrushStroke: (points: number[][], color?: string, strokeWidth?: number, elementId?: string) => void;
  sendPing: () => void;
  sendStopMessage: () => void;
  disconnect: () => void;
  reconnect: () => void;
}

const WS_URL = 'ws://localhost:8080/api/canvas/ws/canvas';

export function useCanvasWebSocket(options: UseCanvasWebSocketOptions): UseCanvasWebSocketReturn {
  const {
    canvasId,
    userId = 'anonymous',
    onOpen,
    onClose,
    onError,
    onOperationAck,
    onSuggestion,
    onAgentAction,
    onCanvasUpdate,
    onDrawStart,
    onDrawProgress,
    onDrawComplete,
    onDrawError,
    onDrawUndo,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    // Skip if already connecting or connected
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[CanvasWS] Already connecting/connected, skipping');
      return;
    }

    try {
      console.log('[CanvasWS] Connecting to:', `${WS_URL}/${canvasId}`);
      const ws = new WebSocket(`${WS_URL}/${canvasId}`);
      wsRef.current = ws;
      console.log('[CanvasWS] WebSocket created, readyState:', ws.readyState);

      ws.onopen = () => {
        if (!mountedRef.current) {
          console.log('[CanvasWS] Connected but component unmounted, closing');
          ws.close();
          return;
        }
        console.log('[CanvasWS] Connected, readyState:', ws.readyState);
        setIsConnected(true);
        onOpen?.();

        // Start ping interval
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'PING' }));
          }
        }, 30000);
      };

      ws.onclose = (event) => {
        console.log('[CanvasWS] Disconnected', event);
        console.log('[CanvasWS] Close code:', event.code, 'reason:', event.reason);
        setIsConnected(false);
        onClose?.();

        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }

        // Auto reconnect only if not intentionally closed and still mounted
        if (event.code !== 1000 && mountedRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[CanvasWS] Reconnecting...');
            connectRef.current();
          }, 5000);
        }
      };

      ws.onerror = (event) => {
        console.error('[CanvasWS] Error event:', event);
        console.error('[CanvasWS] Error target:', event.target);
        console.error('[CanvasWS] Error target readyState:', (event.target as WebSocket)?.readyState);
        onError?.(event);
      };

      ws.onmessage = (event) => {
        try {
          const message: WSResponse = JSON.parse(event.data);

          switch (message.type) {
            case 'OPERATION_ACK':
              onOperationAck?.(message.data);
              break;
            case 'SUGGESTION':
              onSuggestion?.(message.data);
              break;
            case 'AGENT_ACTION':
              onAgentAction?.(message.data);
              break;
            case 'CANVAS_UPDATE':
              // 处理 CANVAS_UPDATE - Agent 操作完成后会广播最新元素列表
              if (message.data?.elements) {
                console.log('[CanvasWS] Received CANVAS_UPDATE with elements, count:', message.data.elements.length);
                onCanvasUpdate?.(message.data);
              } else if (message.operation) {
                // 兼容旧格式：包含 operation 而不是 data.elements
                console.log('[CanvasWS] Received CANVAS_UPDATE with operation, fetching latest state...');
                // 通知上层需要刷新画板数据
                onCanvasUpdate?.({ canvas_id: message.canvas_id, elements: [] });
              }
              break;
            case 'PONG':
              // Heartbeat response
              break;
            case 'ERROR':
              console.error('[CanvasWS] Server error:', message.data.error);
              break;
            case 'DRAW_START':
              console.log('[CanvasWS] DRAW_START:', message.data);
              onDrawStart?.(message.data);
              break;
            case 'DRAW_PROGRESS':
              console.log('[CanvasWS] DRAW_PROGRESS:', message.data);
              onDrawProgress?.(message.data);
              break;
            case 'DRAW_COMPLETE':
              console.log('[CanvasWS] DRAW_COMPLETE:', message.data);
              onDrawComplete?.(message.data);
              break;
            case 'DRAW_ERROR':
              console.error('[CanvasWS] DRAW_ERROR:', message.data);
              onDrawError?.(message.data);
              break;
            case 'DRAW_UNDO':
              console.log('[CanvasWS] DRAW_UNDO:', message.data);
              onDrawUndo?.(message.data);
              break;
          }
        } catch (err) {
          console.error('[CanvasWS] Failed to parse message:', err);
        }
      };
    } catch (err) {
      console.error('[CanvasWS] Failed to connect:', err);
    }
  }, [canvasId, userId, onOpen, onClose, onError, onOperationAck, onSuggestion, onAgentAction, onCanvasUpdate, onDrawStart, onDrawProgress, onDrawComplete, onDrawError, onDrawUndo]);

  // Use ref to always call the latest connect function
  const connectRef = useRef(connect);
  connectRef.current = connect;

  useEffect(() => {
    mountedRef.current = true;
    console.log('[CanvasWS] Effect mount');

    const doConnect = () => {
      if (mountedRef.current) {
        connectRef.current();
      }
    };

    doConnect();

    return () => {
      console.log('[CanvasWS] Effect cleanup');
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
      if (wsRef.current) {
        // Clear handlers to prevent stale callbacks
        wsRef.current.onopen = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []); // Empty deps - only run on mount/unmount

  const sendOperation = useCallback((operation: CanvasOperation, expectResponse = true) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'REPORT_OPERATION',
        payload: operation,
        expect_response: expectResponse,
      }));
    } else {
      console.warn('[CanvasWS] Cannot send operation, not connected');
    }
  }, []);

  // Sync full element state via WebSocket (for auto-save)
  const syncState = useCallback((elements: any[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'SYNC_STATE',
        elements: elements,
      }));
      console.log('[CanvasWS] Sent SYNC_STATE with', elements.length, 'elements');
    } else {
      console.warn('[CanvasWS] Cannot sync state, not connected');
    }
  }, []);

  // Send brush stroke data to backend
  const sendBrushStroke = useCallback((
    points: number[][],
    color: string = "#000000",
    strokeWidth: number = 2,
    elementId?: string
  ) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'BRUSH_STROKE',
        points: points,
        color: color,
        stroke_width: strokeWidth,
        element_id: elementId,
      }));
      console.log('[CanvasWS] Sent BRUSH_STROKE with', points.length, 'points');
    } else {
      console.warn('[CanvasWS] Cannot send brush stroke, not connected');
    }
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'PING' }));
    }
  }, []);

  // Send stop message to interrupt ongoing agent operations
  const sendStopMessage = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'STOP_MESSAGE' }));
      console.log('[CanvasWS] Sent STOP_MESSAGE');
    } else {
      console.warn('[CanvasWS] Cannot send stop message, not connected');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    connect();
  }, [disconnect, connect]);

  return {
    isConnected,
    sendOperation,
    syncState,
    sendBrushStroke,
    sendPing,
    sendStopMessage,
    disconnect,
    reconnect,
  };
}