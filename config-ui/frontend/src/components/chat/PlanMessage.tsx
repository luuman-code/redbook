import React, { useState } from 'react';
import { PlanData } from '../../api/studioApi';

interface PlanMessageProps {
  sessionId: string;
  planData: PlanData;
  onConfirm: () => void;
  onAdjust?: (adjustments: PlanAdjustments) => void;
}

export interface PlanAdjustments {
  imageCount?: number;
  titleStyle?: 'question' | 'exclamation' | 'number';
  colorScheme?: 'warm' | 'cool' | 'fresh' | 'vintage';
}

const PlanMessage: React.FC<PlanMessageProps> = ({
  sessionId,
  planData,
  onConfirm,
  onAdjust,
}) => {
  // Local state for adjustments
  const [imageCount, setImageCount] = useState(planData.image_plan?.count || 3);
  const [titleStyle, setTitleStyle] = useState<'question' | 'exclamation' | 'number'>('question');
  const [colorScheme, setColorScheme] = useState<'warm' | 'cool' | 'fresh' | 'vintage'>('fresh');

  const currentPlan = planData;

  // Get mock image URLs for the preview
  const mockImages = Array.from(
    { length: Math.min(imageCount, 6) },
    (_, i) => `https://picsum.photos/seed/${sessionId}-${i}/300/300`
  );

  // Handle adjustment changes
  const handleImageCountChange = (count: number) => {
    setImageCount(count);
    onAdjust?.({ imageCount: count, titleStyle, colorScheme });
  };

  const handleTitleStyleChange = (style: 'question' | 'exclamation' | 'number') => {
    setTitleStyle(style);
    onAdjust?.({ imageCount, titleStyle: style, colorScheme });
  };

  const handleColorSchemeChange = (scheme: 'warm' | 'cool' | 'fresh' | 'vintage') => {
    setColorScheme(scheme);
    onAdjust?.({ imageCount, titleStyle, colorScheme: scheme });
  };

  // Generate a mock preview title based on plan
  const previewTitle = currentPlan.title || '小红书笔记';

  return (
    <div className="mt-3 space-y-4">
      {/* 小红书 Preview Card */}
      <div className="bg-white rounded-xl shadow-md border border-slate-100 overflow-hidden">
        {/* Cover Image Grid */}
        {mockImages.length > 0 && (
          <div className={`grid gap-0.5 p-1.5 ${
            mockImages.length === 1 ? 'grid-cols-1' :
            mockImages.length === 2 ? 'grid-cols-2' :
            mockImages.length === 3 ? 'grid-cols-2 grid-rows-2' :
            'grid-cols-3 grid-rows-2'
          }`}>
            {mockImages.slice(0, mockImages.length === 3 ? 2 : mockImages.length).map((img, i) => (
              <div
                key={i}
                className={`bg-slate-100 rounded-md overflow-hidden ${
                  mockImages.length === 3 && i === 0 ? 'row-span-2' : ''
                }`}
              >
                <img src={img} alt="" className="w-full h-full object-cover aspect-square" />
              </div>
            ))}
            {mockImages.length > 3 && (
              <div className="bg-slate-800/60 rounded-md flex items-center justify-center">
                <span className="text-white text-sm font-medium">+{mockImages.length - 3}</span>
              </div>
            )}
          </div>
        )}

        {/* Content */}
        <div className="p-3">
          {/* Title */}
          <h4 className="text-base font-bold text-slate-800 leading-snug line-clamp-2 mb-2">
            {previewTitle}
          </h4>

          {/* Tags */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {currentPlan.text_sections.slice(0, 3).map((section, i) => (
              <span key={i} className="px-2 py-0.5 bg-rose-50 text-rose-500 text-xs rounded-full font-medium">
                #{section.section_type}
              </span>
            ))}
            {currentPlan.image_plan && (
              <span className="px-2 py-0.5 bg-amber-50 text-amber-600 text-xs rounded-full font-medium">
                {currentPlan.image_plan.style}
              </span>
            )}
          </div>

          {/* Author Bar */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-gradient-to-br from-rose-400 to-pink-500 rounded-full" />
              <span className="text-xs text-slate-600">AI 内容助手</span>
            </div>
            <div className="flex items-center gap-3 text-slate-400">
              <span className="text-xs flex items-center gap-0.5">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                </svg>
                999
              </span>
              <span className="text-xs flex items-center gap-0.5">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                88
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Structure Preview */}
      <div className="bg-slate-50 rounded-xl p-3">
        <p className="text-xs font-medium text-slate-500 mb-2">内容结构</p>
        <div className="space-y-1.5">
          {currentPlan.text_sections.slice(0, 4).map((section, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className={`w-4 h-4 rounded-full flex items-center justify-center text-white font-medium ${
                section.section_type === 'title' ? 'bg-rose-500' :
                section.section_type === 'headline' ? 'bg-amber-500' :
                section.section_type === 'hashtag' ? 'bg-emerald-500' :
                'bg-blue-500'
              }`}>
                {i + 1}
              </span>
              <span className="text-slate-600 capitalize">{section.section_type}</span>
              <span className="text-slate-400">({section.content_words}字)</span>
            </div>
          ))}
        </div>
      </div>

      {/* Adjustment Controls */}
      <div className="bg-white rounded-xl border border-slate-200 p-3 space-y-3">
        <p className="text-xs font-medium text-slate-500">方案调整</p>

        {/* Image Count Selector */}
        <div>
          <p className="text-xs text-slate-600 mb-1.5">图片数量</p>
          <div className="flex gap-1 flex-wrap">
            {[1, 2, 3, 4, 5, 6].map((count) => (
              <button
                key={count}
                onClick={() => handleImageCountChange(count)}
                className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                  imageCount === count
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {count}
              </button>
            ))}
          </div>
        </div>

        {/* Title Style Selector */}
        <div>
          <p className="text-xs text-slate-600 mb-1.5">标题风格</p>
          <div className="flex gap-2 flex-wrap">
            {[
              { value: 'question', label: '问号式' },
              { value: 'exclamation', label: '感叹式' },
              { value: 'number', label: '数字列表式' },
            ].map((style) => (
              <button
                key={style.value}
                onClick={() => handleTitleStyleChange(style.value as 'question' | 'exclamation' | 'number')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  titleStyle === style.value
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {style.label}
              </button>
            ))}
          </div>
        </div>

        {/* Color Scheme Selector */}
        <div>
          <p className="text-xs text-slate-600 mb-1.5">配色方案</p>
          <div className="flex gap-2 flex-wrap">
            {[
              { value: 'warm', label: '暖色', color: 'bg-orange-500' },
              { value: 'cool', label: '冷色', color: 'bg-blue-500' },
              { value: 'fresh', label: '清新', color: 'bg-emerald-500' },
              { value: 'vintage', label: '复古', color: 'bg-amber-700' },
            ].map((scheme) => (
              <button
                key={scheme.value}
                onClick={() => handleColorSchemeChange(scheme.value as 'warm' | 'cool' | 'fresh' | 'vintage')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                  colorScheme === scheme.value
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <span className={`w-3 h-3 rounded-full ${scheme.color}`} />
                {scheme.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Warning */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
        <div className="flex items-start gap-2">
          <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <p className="text-xs font-medium text-amber-800">确认后将消耗 API 配额</p>
            <p className="text-xs text-amber-600 mt-0.5">生成文案和图片将调用 AI API，确认前请确保方案正确。</p>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex justify-end gap-2">
        <button
          onClick={onConfirm}
          className="px-5 py-2 bg-gradient-to-r from-rose-500 to-pink-600 hover:from-rose-600 hover:to-pink-700 text-white text-sm font-medium rounded-lg transition-all flex items-center gap-2 shadow-lg shadow-rose-200"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
          确认方案
        </button>
      </div>
    </div>
  );
};

export default PlanMessage;