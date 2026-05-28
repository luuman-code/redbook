import React, { useState } from 'react';
import { Session } from '../../api/studioApi';

interface FeedbackPanelProps {
  session: Session;
  onSubmit: (feedback: string) => void;
  onExport: () => void;
}

const FeedbackPanel: React.FC<FeedbackPanelProps> = ({ session, onSubmit, onExport }) => {
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!feedback.trim()) return;

    setIsSubmitting(true);
    try {
      await onSubmit(feedback);
      setFeedback('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const quickFeedbackOptions = [
    '标题不够吸引人',
    '正文太长了，精简一下',
    '第三张图换成卡通风格',
    '语气不够活泼',
    '增加更多互动引导',
  ];

  return (
    <div className="space-y-6">
      {/* Quick Feedback */}
      <div>
        <h3 className="text-sm font-bold text-slate-800 mb-3">快捷反馈</h3>
        <div className="flex flex-wrap gap-2">
          {quickFeedbackOptions.map((option, index) => (
            <button
              key={index}
              onClick={() => setFeedback(option)}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg border border-slate-200 transition-colors"
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      {/* Feedback Input */}
      <div>
        <h3 className="text-sm font-bold text-slate-800 mb-3">详细反馈</h3>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="请输入您的修改意见，例如：
- 改标题
- 第三张图改成卡通风格
- 正文里'清爽'这个词用太多了
- 语气太正式了，更活泼一点"
          rows={6}
          className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-none"
        />
      </div>

      {/* Submit */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">
          已迭代 {session.current_version - 1} 轮
        </div>
        <div className="flex gap-3">
          <button
            onClick={onExport}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors border border-slate-200 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            导出素材包
          </button>
          <button
            onClick={handleSubmit}
            disabled={!feedback.trim() || isSubmitting}
            className="px-5 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {isSubmitting ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                提交中...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                提交修改
              </>
            )}
          </button>
        </div>
      </div>

      {/* Tips */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <h4 className="text-sm font-medium text-amber-800 mb-2 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          修改建议
        </h4>
        <ul className="text-sm text-amber-700 space-y-1">
          <li>• 尽量具体描述要修改的内容</li>
          <li>• 可以指定要修改哪个部分（如"标题"、"第三张图"）</li>
          <li>• 支持添加新的内容要求</li>
        </ul>
      </div>
    </div>
  );
};

export default FeedbackPanel;
