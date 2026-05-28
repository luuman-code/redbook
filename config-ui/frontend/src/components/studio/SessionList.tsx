import React from 'react';
import { Session } from '../../api/studioApi';

interface SessionListProps {
  sessions: Session[];
  activeSessionId?: string;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

const SessionList: React.FC<SessionListProps> = ({
  sessions,
  activeSessionId,
  onSelect,
  onDelete,
}) => {
  const statusLabels: Record<string, { text: string; color: string }> = {
    created: { text: '已创建', color: 'bg-slate-100 text-slate-700' },
    planning: { text: '规划中', color: 'bg-blue-100 text-blue-700' },
    generating: { text: '生成中', color: 'bg-indigo-100 text-indigo-700' },
    reviewing: { text: '审核中', color: 'bg-amber-100 text-amber-700' },
    iterating: { text: '迭代中', color: 'bg-purple-100 text-purple-700' },
    completed: { text: '已完成', color: 'bg-emerald-100 text-emerald-700' },
    published: { text: '已发布', color: 'bg-green-100 text-green-700' },
    cancelled: { text: '已取消', color: 'bg-red-100 text-red-700' },
  };

  return (
    <div className="divide-y divide-slate-100">
      {sessions.map((session) => (
        <div
          key={session.session_id}
          className={`p-4 cursor-pointer hover:bg-slate-50 transition-colors ${
            activeSessionId === session.session_id ? 'bg-indigo-50' : ''
          }`}
          onClick={() => onSelect(session.session_id)}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate">
                {session.brief?.raw_input?.slice(0, 30) || '新会话'}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {new Date(session.created_at).toLocaleString('zh-CN')}
              </p>
            </div>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              statusLabels[session.status]?.color || 'bg-slate-100 text-slate-700'
            }`}>
              {statusLabels[session.status]?.text || session.status}
            </span>
          </div>
          <div className="flex gap-2 mt-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(session.session_id);
              }}
              className="text-xs text-red-500 hover:text-red-600"
            >
              删除
            </button>
          </div>
        </div>
      ))}

      {sessions.length === 0 && (
        <div className="p-8 text-center text-slate-500 text-sm">
          暂无会话记录
        </div>
      )}
    </div>
  );
};

export default SessionList;
