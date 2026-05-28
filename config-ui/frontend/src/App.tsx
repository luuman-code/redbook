import React, { useState, useEffect } from 'react';
import { configApi } from './api/configApi';
import { StudioPage } from './components/studio';
import { CanvasListPage, CanvasWorkspace } from './pages';
import LogViewerPage from './pages/LogViewerPage';

interface ModelProviderConfig {
  provider: string;
  api_url: string;
  model_name: string;
  api_key: string;
  default_params: Record<string, any>;
  timeout: number;
  retry_count: number;
  enabled: boolean;
}

interface ModelConfig {
  type: string;
  primary: ModelProviderConfig;
  fallback?: ModelProviderConfig;
}

interface Environment {
  name: string;
  displayName: string;
  active: boolean;
}

const modelTypeNames: Record<string, string> = {
  llm: '大语言模型',
  vision: '视觉模型',
  image_generation: '图片生成',
  tts: '语音合成',
  video: '视频生成',
  video_t2v: '视频生成-文生视频',
  video_i2v: '视频生成-图生视频',
  video_r2v: '视频生成-图文视频',
  video_edit: '视频生成-视频剪辑',
};

const Icons = {
  Download: () => (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  ),
  Upload: () => (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
    </svg>
  ),
  Server: () => (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
    </svg>
  ),
};

const defaultModels: ModelConfig[] = [
  { type: 'llm', primary: { provider: 'openai', api_url: 'https://api.openai.com/v1', model_name: 'gpt-4o', api_key: '', default_params: {}, timeout: 120, retry_count: 3, enabled: true }},
  { type: 'vision', primary: { provider: 'openai', api_url: 'https://api.openai.com/v1', model_name: 'gpt-4o', api_key: '', default_params: {}, timeout: 120, retry_count: 3, enabled: true }},
  { type: 'image_generation', primary: { provider: 'openai', api_url: 'https://api.openai.com/v1', model_name: 'dall-e-3', api_key: '', default_params: {}, timeout: 120, retry_count: 3, enabled: true }},
  { type: 'tts', primary: { provider: 'openai', api_url: 'https://api.openai.com/v1', model_name: 'tts-1', api_key: '', default_params: {}, timeout: 120, retry_count: 3, enabled: true }},
  { type: 'video', primary: { provider: 'openai', api_url: 'https://api.openai.com/v1', model_name: 'sora', api_key: '', default_params: {}, timeout: 120, retry_count: 3, enabled: true }},
];

const defaultEnvironments: Environment[] = [
  { name: 'development', displayName: '开发环境', active: true },
  { name: 'staging', displayName: '预发布环境', active: false },
  { name: 'production', displayName: '生产环境', active: false },
];

function App() {
  const [activeTab, setActiveTab] = useState<'config' | 'studio' | 'canvas' | 'logs'>('config');
  const [canvasTabView, setCanvasTabView] = useState<'list' | 'workspace'>('list');
  const [currentCanvasId, setCurrentCanvasId] = useState<string | null>(null);
  const [models, setModels] = useState<ModelConfig[]>(defaultModels);
  const [environments] = useState<Environment[]>(defaultEnvironments);
  const [activeEnv, setActiveEnv] = useState('development');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingModel, setEditingModel] = useState<{ type: string; config: ModelProviderConfig; isFallback: boolean } | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const data = await configApi.getConfig();
      if (data && data.environments && data.environments[activeEnv]) {
        const envModels = data.environments[activeEnv].models;
        const modelList: ModelConfig[] = [];

        for (const [type, config] of Object.entries(envModels)) {
          if (type === 'video' && typeof config === 'object' && config !== null) {
            // Handle video models: extract sub-models and the main video config
            // Main video config
            if (config.primary && typeof config.primary === 'object') {
              modelList.push({
                type: 'video',
                primary: config.primary,
                fallback: config.fallback,
              });
            }
            // Video sub-models (video_t2v, video_i2v, video_r2v, video_edit)
            for (const subType of ['video_t2v', 'video_i2v', 'video_r2v', 'video_edit']) {
              if (config[subType] && typeof config[subType] === 'object') {
                modelList.push({
                  type: subType,
                  primary: config[subType],
                  fallback: undefined,
                });
              }
            }
          } else if (typeof config === 'object' && config !== null) {
            // Regular model (llm, vision, image_generation, tts)
            modelList.push({
              type,
              primary: config.primary || config,
              fallback: config.fallback,
            });
          }
        }

        setModels(modelList);
      }
    } catch (error) {
      console.log('Using default configuration');
    }
  };

  const handleEnvChange = async (env: string) => {
    setActiveEnv(env);
    try {
      await configApi.activateEnv(env);
      setMessage({ type: 'success', text: `已切换到 ${env}` });
      setTimeout(() => setMessage(null), 3000);
      loadConfig();
    } catch (error) {
      setMessage({ type: 'error', text: '环境切换失败' });
    }
  };

  const handleEditModel = (model: ModelConfig, isFallback = false) => {
    setEditingModel({
      type: model.type,
      config: isFallback && model.fallback ? { ...model.fallback } : { ...model.primary },
      isFallback,
    });
  };

  const handleTestModel = async (type: string) => {
    try {
      await configApi.testModel(type);
    } catch (error) {
      throw error;
    }
  };

  const handleExport = async () => {
    try {
      setLoading(true);
      const data = await configApi.exportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      link.download = `redbook-config-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setMessage({ type: 'success', text: '配置已导出成功' });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: '导出失败' });
    } finally {
      setLoading(false);
    }
  };

  const handleImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const config = JSON.parse(e.target?.result as string);
        await configApi.importConfig(config);
        setMessage({ type: 'success', text: '配置已导入成功' });
        setTimeout(() => setMessage(null), 3000);
        loadConfig();
      } catch (error) {
        setMessage({ type: 'error', text: '导入失败：无效的配置文件' });
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  };

  const handleSaveModel = async () => {
    if (!editingModel) return;

    try {
      const currentModel = models.find(m => m.type === editingModel.type);

      // Check if this is a video sub-model (video_t2v, video_i2v, etc.)
      const isVideoSubModel = editingModel.type.startsWith('video_') && editingModel.type !== 'video';

      if (isVideoSubModel) {
        // For video sub-models, send the config directly (flattened structure)
        await configApi.updateModel(editingModel.type, editingModel.config);
        setModels(models.map(m =>
          m.type === editingModel.type
            ? { ...m, primary: editingModel.config }
            : m
        ));
      } else {
        // For regular models, use primary/fallback structure
        const primaryConfig = editingModel.isFallback
          ? (currentModel?.primary || editingModel.config)
          : editingModel.config;
        const fallbackConfig = editingModel.isFallback
          ? editingModel.config
          : (currentModel?.fallback || undefined);

        await configApi.updateModel(editingModel.type, {
          primary: primaryConfig,
          fallback: fallbackConfig,
        });
        setModels(models.map(m =>
          m.type === editingModel.type
            ? { ...m, primary: primaryConfig, fallback: fallbackConfig }
            : m
        ));
      }
      setEditingModel(null);
      setMessage({ type: 'success', text: '配置已保存' });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: '保存失败' });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-100 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-500 rounded-lg">
                <Icons.Server />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-800">小红书 Agent</h1>
                <p className="text-sm text-slate-500 mt-0.5">AI 内容创作与配置管理</p>
              </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
              <button
                onClick={() => setActiveTab('config')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeTab === 'config'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                配置中心
              </button>
              <button
                onClick={() => setActiveTab('studio')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeTab === 'studio'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                内容创作
              </button>
              <button
                onClick={() => setActiveTab('canvas')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeTab === 'canvas'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                创意工坊
              </button>
              <button
                onClick={() => setActiveTab('logs')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeTab === 'logs'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                日志查看
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Studio Tab */}
      {activeTab === 'studio' && <StudioPage />}

      {/* Canvas Tab */}
      {activeTab === 'canvas' && (
        canvasTabView === 'list' ? (
          <CanvasListPage
            onNavigateToWorkspace={(canvasId: string) => {
              setCurrentCanvasId(canvasId);
              setCanvasTabView('workspace');
            }}
          />
        ) : (
          <CanvasWorkspace
            canvasId={currentCanvasId!}
            onBack={() => {
              setCanvasTabView('list');
              setCurrentCanvasId(null);
            }}
          />
        )
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && <LogViewerPage />}

      {/* Config Tab */}
      {activeTab === 'config' && (
        <div>
          {/* Environment Selector */}
          <div className="max-w-7xl mx-auto px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="text-sm text-slate-600">当前环境:</span>
              <select
                value={activeEnv}
                onChange={(e) => handleEnvChange(e.target.value)}
                className="px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
              >
                {environments.map((env) => (
                  <option key={env.name} value={env.name}>
                    {env.displayName}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Main Content */}
          <main className="max-w-7xl mx-auto px-6 py-8">
            {/* Message Toast */}
            {message && (
              <div className={`mb-6 px-4 py-3 rounded-lg text-sm ${
                message.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'
              }`}>
                {message.text}
              </div>
            )}

            {/* Models Section */}
            <section className="mb-8">
              <h2 className="text-base font-bold text-slate-800 flex items-center border-l-4 border-indigo-500 pl-3 mb-4">
                模型配置
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {models.map((model) => (
                  <div key={model.type} className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-300 hover:shadow-md transition-all">
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h3 className="text-base font-bold text-slate-800">{modelTypeNames[model.type] || model.type}</h3>
                        <p className="text-sm text-slate-500 mt-0.5">提供商: {model.primary.provider}</p>
                      </div>
                      <div className={`w-3 h-3 rounded-full ${model.primary.enabled ? 'bg-emerald-400' : 'bg-slate-300'}`} />
                    </div>

                    <div className="space-y-2 text-sm mb-4">
                      <div className="flex justify-between">
                        <span className="text-slate-500">API:</span>
                        <span className="text-slate-700 truncate max-w-[180px]" title={model.primary.api_url}>{model.primary.api_url}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">模型:</span>
                        <span className="text-slate-700">{model.primary.model_name}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">超时:</span>
                        <span className="text-slate-700">{model.primary.timeout}s</span>
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <button
                        onClick={() => handleEditModel(model, false)}
                        className="flex-1 px-3 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors"
                      >
                        主配置
                      </button>
                      <button
                        onClick={() => handleEditModel(model, true)}
                        className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors border border-slate-200"
                      >
                        备用配置
                      </button>
                      <button
                        onClick={() => handleTestModel(model.type)}
                        className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors border border-slate-200"
                      >
                        测试
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Actions Section */}
            <section className="flex items-center justify-between border-t border-slate-200 pt-6">
              <div className="text-sm text-slate-500">
                共 {models.length} 个模型配置
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleExport}
                  disabled={loading}
                  className="flex items-center gap-2 px-5 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  <Icons.Download />
                  导出配置
                </button>
                <label className="flex items-center gap-2 px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors cursor-pointer border border-slate-200">
                  <Icons.Upload />
                  导入配置
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleImport}
                    className="hidden"
                  />
                </label>
              </div>
            </section>
          </main>
        </div>
      )}

      {/* Edit Modal */}
      {editingModel && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-slate-200 rounded-xl p-6 w-full max-w-lg shadow-lg max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">
              编辑 {modelTypeNames[editingModel.type]} {editingModel.isFallback ? '(备用)' : '(主配置)'}
            </h3>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="block text-sm font-semibold text-slate-700">提供商</label>
                  <input
                    type="text"
                    value={editingModel.config.provider}
                    onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, provider: e.target.value } })}
                    className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-sm font-semibold text-slate-700">模型名称</label>
                  <input
                    type="text"
                    value={editingModel.config.model_name}
                    onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, model_name: e.target.value } })}
                    className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-sm font-semibold text-slate-700">API URL</label>
                <input
                  type="text"
                  value={editingModel.config.api_url}
                  onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, api_url: e.target.value } })}
                  className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-sm font-semibold text-slate-700">API Key</label>
                <input
                  type="password"
                  value={editingModel.config.api_key}
                  onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, api_key: e.target.value } })}
                  className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  placeholder={'支持 ${ENV_VAR} 环境变量语法'}
                />
                <p className="text-xs text-slate-500">支持 $ENV_VAR 环境变量语法</p>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <label className="block text-sm font-semibold text-slate-700">超时(秒)</label>
                  <input
                    type="number"
                    value={editingModel.config.timeout}
                    onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, timeout: parseInt(e.target.value) || 60 } })}
                    className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-sm font-semibold text-slate-700">重试次数</label>
                  <input
                    type="number"
                    value={editingModel.config.retry_count}
                    onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, retry_count: parseInt(e.target.value) || 3 } })}
                    className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-sm font-semibold text-slate-700">启用状态</label>
                  <select
                    value={editingModel.config.enabled ? 'true' : 'false'}
                    onChange={(e) => setEditingModel({ ...editingModel, config: { ...editingModel.config, enabled: e.target.value === 'true' } })}
                    className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  >
                    <option value="true">启用</option>
                    <option value="false">禁用</option>
                  </select>
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setEditingModel(null)}
                className="flex-1 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors border border-slate-200"
              >
                取消
              </button>
              <button
                onClick={handleSaveModel}
                className="flex-1 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
