import React, { useState } from 'react';

interface ModelConfig {
  type: string;
  name: string;
  provider: string;
  enabled: boolean;
  config: Record<string, any>;
}

interface ModelConfigCardProps {
  model: ModelConfig;
  onEdit: (model: ModelConfig) => void;
  onTest: (type: string) => void;
}

const modelTypeNames: Record<string, string> = {
  llm: '大语言模型',
  vision: '视觉模型',
  image_generation: '图片生成',
  tts: '语音合成',
  video: '视频生成',
};

const ModelConfigCard: React.FC<ModelConfigCardProps> = ({ model, onEdit, onTest }) => {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await onTest(model.type);
      setTestResult('success');
    } catch {
      setTestResult('error');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-300 hover:shadow-md transition-all">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-base font-bold text-slate-800">{modelTypeNames[model.type] || model.type}</h3>
          <p className="text-sm text-slate-500 mt-0.5">提供商: {model.provider}</p>
        </div>
        <div className={`w-3 h-3 rounded-full ${model.enabled ? 'bg-emerald-400' : 'bg-slate-300'}`} />
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-500">状态:</span>
          <span className={model.enabled ? 'text-emerald-600 font-medium' : 'text-slate-400'}>
            {model.enabled ? '已启用' : '已禁用'}
          </span>
        </div>
      </div>

      <div className="flex gap-3 mt-5">
        <button
          onClick={() => onEdit(model)}
          className="flex-1 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          编辑
        </button>
        <button
          onClick={handleTest}
          disabled={testing}
          className={`flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            testResult === 'success' ? 'bg-emerald-500 hover:bg-emerald-600 text-white' :
            testResult === 'error' ? 'bg-red-500 hover:bg-red-600 text-white' :
            testing ? 'bg-slate-200 text-slate-400 cursor-not-allowed' :
            'bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-200'
          }`}
        >
          {testing ? '测试中...' : testResult === 'success' ? '成功' : testResult === 'error' ? '失败' : '测试连接'}
        </button>
      </div>
    </div>
  );
};

export default ModelConfigCard;
