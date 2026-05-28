import React from 'react';
import useWebSocket, { WebSocketMessage } from '../../hooks/useWebSocket';

interface GenerationItem {
  id: string;
  name: string;
  type: string;
  status: 'pending' | 'generating' | 'completed' | 'failed';
}

interface GenerationProgressProps {
  sessionId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
  onTokenStream?: (itemId: string, token: string, done: boolean) => void;
}

const GenerationProgress: React.FC<GenerationProgressProps> = ({
  sessionId,
  onComplete,
  onError,
  onTokenStream,
}) => {
  const [items, setItems] = React.useState<GenerationItem[]>([
    { id: '1', name: '标题', type: 'title', status: 'pending' },
    { id: '2', name: '正文第一段', type: 'text', status: 'pending' },
    { id: '3', name: '正文第二段', type: 'text', status: 'pending' },
    { id: '4', name: '话题标签', type: 'hashtag', status: 'pending' },
    { id: '5', name: '互动引导', type: 'cta', status: 'pending' },
    { id: '6', name: '配图 1', type: 'image', status: 'pending' },
    { id: '7', name: '配图 2', type: 'image', status: 'pending' },
    { id: '8', name: '配图 3', type: 'image', status: 'pending' },
  ]);

  const [currentItem, setCurrentItem] = React.useState<string | null>(null);
  const [logs, setLogs] = React.useState<string[]>([]);
  const [streamingContent, setStreamingContent] = React.useState<Record<string, string>>({});

  // Calculate progress
  const completedCount = items.filter(i => i.status === 'completed').length;
  const totalCount = items.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  // WebSocket connection for real-time updates
  const wsUrl = `ws://localhost:8080/api/studio/sessions/${sessionId}/progress`;

  // Map backend event types to frontend-compatible types
  const mapEventType = (type: string): string => {
    const typeMap: Record<string, string> = {
      'generation_start': 'item_start',
      'generation_complete': 'item_complete',
      'generation_error': 'item_error',
      'generation_progress': 'progress',
    };
    return typeMap[type] || type;
  };

  // Map backend event data to frontend format
  const mapEventData = (message: WebSocketMessage): WebSocketMessage => {
    const type = mapEventType(message.type);
    let data = message.data;

    // Handle legacy event types
    if (message.type === 'generation_start' && data) {
      data = { ...data, item_name: data.item_type || data.item_name };
    }
    if (message.type === 'generation_complete' && data) {
      data = { ...data, item_name: data.item_type };
    }
    if (message.type === 'generation_error' && data) {
      data = { ...data, item_name: data.item_type };
    }

    return { ...message, type, data };
  };

  const handleMessage = React.useCallback((message: WebSocketMessage) => {
    const mappedMessage = mapEventData(message);

    switch (mappedMessage.type) {
      case 'token_stream':
        // Handle streaming token events
        if (mappedMessage.data?.item_id) {
          const itemId = mappedMessage.data.item_id;
          const token = mappedMessage.data.content || '';
          const done = mappedMessage.data.message === 'done';

          // Update local streaming content state
          setStreamingContent(prev => {
            const currentContent = prev[itemId] || '';
            let newContent = done ? '' : currentContent + token;

            // Filter: only keep content after "Final Text:"
            if (newContent.includes('Final Text:')) {
              const parts = newContent.split('Final Text:');
              newContent = parts[parts.length - 1].trim();
            }

            return { ...prev, [itemId]: newContent };
          });

          // Call parent's token stream callback
          onTokenStream?.(itemId, token, done);

          // Also log the streaming
          if (!done && token) {
            // Don't spam logs with every token, just update silently
          }
        }
        break;

      case 'item_start':
        setCurrentItem(mappedMessage.data?.item_id);
        setItems(prev =>
          prev.map(item =>
            item.id === mappedMessage.data?.item_id
              ? { ...item, status: 'generating' }
              : item
          )
        );
        setLogs(prev => [...prev, `开始生成: ${mappedMessage.data?.item_name || mappedMessage.data?.item_id}`]);
        break;

      case 'item_complete':
        setItems(prev =>
          prev.map(item =>
            item.id === mappedMessage.data?.item_id
              ? { ...item, status: 'completed' }
              : item
          )
        );
        setCurrentItem(null);
        setStreamingContent(prev => {
          const newContent = { ...prev };
          delete newContent[mappedMessage.data?.item_id];
          return newContent;
        });
        setLogs(prev => [...prev, `完成: ${mappedMessage.data?.item_name || mappedMessage.data?.item_id}`]);
        break;

      case 'item_error':
        setItems(prev =>
          prev.map(item =>
            item.id === mappedMessage.data?.item_id
              ? { ...item, status: 'failed' }
              : item
          )
        );
        setStreamingContent(prev => {
          const newContent = { ...prev };
          delete newContent[mappedMessage.data?.item_id];
          return newContent;
        });
        setLogs(prev => [...prev, `错误: ${mappedMessage.data?.item_name || mappedMessage.data?.item_id} - ${mappedMessage.data?.error}`]);
        onError?.(mappedMessage.data?.error);
        break;

      case 'progress':
        setLogs(prev => [...prev, mappedMessage.data?.message || '处理中...']);
        break;

      case 'complete':
        setLogs(prev => [...prev, '所有内容生成完成!']);
        onComplete?.();
        break;

      default:
        if (mappedMessage.data) {
          setLogs(prev => [...prev, String(mappedMessage.data)]);
        }
    }
  }, [onComplete, onError, onTokenStream]);

  const { isConnected, connect, disconnect } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
    reconnect: true,
    reconnectInterval: 2000,
  });

  React.useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Get status color
  const getStatusColor = (status: GenerationItem['status']) => {
    switch (status) {
      case 'pending':
        return 'bg-slate-100 text-slate-400';
      case 'generating':
        return 'bg-blue-100 text-blue-600';
      case 'completed':
        return 'bg-emerald-100 text-emerald-600';
      case 'failed':
        return 'bg-red-100 text-red-600';
    }
  };

  // Get status icon
  const getStatusIcon = (status: GenerationItem['status']) => {
    switch (status) {
      case 'pending':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" strokeWidth="2" stroke="currentColor" strokeDasharray="4 2" />
          </svg>
        );
      case 'generating':
        return (
          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        );
      case 'completed':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
        );
      case 'failed':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        );
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-indigo-500 to-purple-600">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-white/20 rounded-lg">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">内容生成中</h3>
              <p className="text-xs text-indigo-100 mt-0.5">
                {isConnected ? '已连接' : '正在连接...'}
              </p>
            </div>
          </div>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
            isConnected ? 'bg-emerald-100 text-emerald-600' : 'bg-amber-100 text-amber-600'
          }`}>
            {isConnected ? '实时同步' : '连接中'}
          </span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="px-4 py-3 border-b border-slate-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-600">生成进度</span>
          <span className="text-xs font-medium text-slate-700">
            {completedCount} / {totalCount} 项
          </span>
        </div>
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-purple-600 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Items List */}
      <div className="p-4 max-h-[300px] overflow-y-auto">
        <div className="grid grid-cols-2 gap-2">
          {items.map((item) => (
            <div key={item.id}>
              <div
                className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                  currentItem === item.id
                    ? 'bg-indigo-50 border border-indigo-200'
                    : item.status === 'completed'
                    ? 'bg-emerald-50 border border-emerald-100'
                    : item.status === 'failed'
                    ? 'bg-red-50 border border-red-100'
                    : 'bg-slate-50 border border-slate-100'
                }`}
              >
                <span className={`p-1 rounded ${getStatusColor(item.status)}`}>
                  {getStatusIcon(item.status)}
                </span>
                <span className={`text-xs font-medium ${
                  item.status === 'completed'
                    ? 'text-emerald-700'
                    : item.status === 'failed'
                    ? 'text-red-700'
                    : item.status === 'generating'
                    ? 'text-indigo-700'
                    : 'text-slate-500'
                }`}>
                  {item.name}
                </span>
                {currentItem === item.id && (
                  <span className="ml-auto text-xs text-indigo-500 animate-pulse">生成中</span>
                )}
              </div>
              {/* Streaming content preview */}
              {streamingContent[item.id] && (
                <div className="mt-1 px-3 py-2 bg-slate-900/80 rounded-lg border border-slate-700">
                  <p className="text-xs text-slate-300 font-mono line-clamp-2">
                    {streamingContent[item.id]}
                    <span className="inline-block w-1 h-3 bg-indigo-400 animate-pulse ml-1 align-middle" />
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Logs */}
      {logs.length > 0 && (
        <div className="px-4 py-3 border-t border-slate-100 bg-slate-50">
          <p className="text-xs font-medium text-slate-500 mb-2">生成日志</p>
          <div className="h-24 overflow-y-auto bg-slate-900 rounded-lg p-2 font-mono">
            {logs.map((log, index) => (
              <p key={index} className="text-xs text-slate-300 leading-relaxed">
                <span className="text-slate-500 mr-2">{index + 1}</span>
                {log}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-4 py-3 border-t border-slate-100 flex justify-end gap-2">
        <button
          onClick={disconnect}
          className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
        >
          关闭
        </button>
      </div>
    </div>
  );
};

export default GenerationProgress;