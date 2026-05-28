import React, { useState, useEffect, useCallback } from 'react';
import CanvasList from '../components/canvas/CanvasList';
import { canvasApi, CanvasSummary } from '../api/canvasApi';

interface CanvasListPageProps {
  onNavigateToWorkspace: (canvasId: string) => void;
}

const CanvasListPage: React.FC<CanvasListPageProps> = ({
  onNavigateToWorkspace,
}) => {
  const [canvases, setCanvases] = useState<CanvasSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCanvases = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await canvasApi.listCanvases();

      if (response.success) {
        setCanvases(response.canvases);
      } else {
        setError(response.error || '加载画板列表失败');
      }
    } catch (err) {
      setError('加载画板列表失败');
      console.error('Failed to load canvases:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCanvases();
  }, [loadCanvases]);

  const handleCreateCanvas = async () => {
    try {
      const response = await canvasApi.createCanvas('新画板');

      if (response.success && response.canvas) {
        await loadCanvases();
        onNavigateToWorkspace(response.canvas.canvas_id);
      }
    } catch (err) {
      console.error('Failed to create canvas:', err);
    }
  };

  const handleOpenCanvas = (canvasId: string) => {
    onNavigateToWorkspace(canvasId);
  };

  const handleDeleteCanvas = async (canvasId: string) => {
    if (!confirm('确定要删除这个画板吗？此操作不可撤销。')) {
      return;
    }

    try {
      const response = await canvasApi.deleteCanvas(canvasId);

      if (response.success) {
        setCanvases(prev => prev.filter(c => c.canvas_id !== canvasId));
      } else {
        alert(response.error || '删除画板失败');
      }
    } catch (err) {
      console.error('Failed to delete canvas:', err);
      alert('删除画板失败');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm text-slate-500">加载中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 bg-red-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-sm text-red-600 mb-4">{error}</p>
          <button
            onClick={loadCanvases}
            className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-100 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-500 rounded-lg">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-800">画板创作</h1>
                <p className="text-sm text-slate-500">创建和编辑你的创意画板</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Canvas List */}
      <main className="max-w-7xl mx-auto">
        <CanvasList
          canvases={canvases}
          onOpenCanvas={handleOpenCanvas}
          onDeleteCanvas={handleDeleteCanvas}
          onCreateCanvas={handleCreateCanvas}
        />
      </main>
    </div>
  );
};

export default CanvasListPage;
