import React from 'react';
import { CanvasSummary } from '../../api/canvasApi';

interface CanvasListProps {
  canvases: CanvasSummary[];
  onOpenCanvas: (canvasId: string) => void;
  onDeleteCanvas: (canvasId: string) => void;
  onCreateCanvas: () => void;
}

const CanvasList: React.FC<CanvasListProps> = ({
  canvases,
  onOpenCanvas,
  onDeleteCanvas,
  onCreateCanvas,
}) => {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500 rounded-lg">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-800">我的画板</h2>
            <p className="text-sm text-slate-500">{canvases.length} 个画板</p>
          </div>
        </div>
        <button
          onClick={onCreateCanvas}
          className="flex items-center gap-2 px-4 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          新建画板
        </button>
      </div>

      {/* Canvas Grid */}
      {canvases.length === 0 ? (
        <div className="text-center py-16">
          <div className="w-16 h-16 mx-auto mb-4 bg-slate-100 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
            </svg>
          </div>
          <h3 className="text-base font-medium text-slate-700 mb-1">暂无画板</h3>
          <p className="text-sm text-slate-500 mb-4">创建你的第一个画板开始创作</p>
          <button
            onClick={onCreateCanvas}
            className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors"
          >
            创建画板
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {canvases.map((canvas) => (
            <div
              key={canvas.canvas_id}
              className="bg-white border border-slate-200 rounded-xl overflow-hidden hover:border-indigo-300 hover:shadow-lg transition-all group"
            >
              {/* Thumbnail */}
              <div className="aspect-video bg-slate-100 relative overflow-hidden">
                {canvas.thumbnail ? (
                  <img
                    src={canvas.thumbnail}
                    alt={canvas.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <svg className="w-12 h-12 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                    </svg>
                  </div>
                )}
                {/* Hover overlay */}
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                  <button
                    onClick={() => onOpenCanvas(canvas.canvas_id)}
                    className="px-3 py-1.5 bg-white hover:bg-slate-100 text-slate-800 text-xs font-medium rounded-lg transition-colors"
                  >
                    打开
                  </button>
                </div>
              </div>

              {/* Info */}
              <div className="p-4">
                <h3 className="text-sm font-medium text-slate-800 truncate mb-1">
                  {canvas.name}
                </h3>
                <p className="text-xs text-slate-500 mb-3">
                  {formatDate(canvas.updated_at)}
                </p>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">
                    {canvas.element_count} 个元素
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => onOpenCanvas(canvas.canvas_id)}
                      className="text-xs text-indigo-500 hover:text-indigo-600 font-medium"
                    >
                      打开
                    </button>
                    <button
                      onClick={() => onDeleteCanvas(canvas.canvas_id)}
                      className="text-xs text-red-500 hover:text-red-600 font-medium"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default CanvasList;
