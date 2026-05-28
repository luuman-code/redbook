import React, { useState, useEffect } from 'react';
import { Session, studioApi, ContentPlan } from '../../api/studioApi';

interface PlanDialogProps {
  session: Session;
  onConfirm: () => void;
  onCancel: () => void;
  onAdjust?: (adjustments: PlanAdjustments) => void;
}

export interface PlanAdjustments {
  imageCount?: number;
  titleStyle?: 'question' | 'exclamation' | 'number';
  colorScheme?: 'warm' | 'cool' | 'fresh' | 'vintage';
}

interface TextSection {
  section_id: string;
  section_type: string;
  content: string;
  content_words: number;
}

const PlanDialog: React.FC<PlanDialogProps> = ({ session, onConfirm, onCancel, onAdjust }) => {
  const { brief, plan } = session;

  // Check if template image exists
  const hasTemplateImage = !!(brief as any).template_image_url;
  const templateImageUrl = (brief as any).template_image_url;

  // Local state for adjustments
  const [imageCount, setImageCount] = useState(plan.image_plan?.count || 3);
  const [titleStyle, setTitleStyle] = useState<'question' | 'exclamation' | 'number'>('question');
  const [colorScheme, setColorScheme] = useState<'warm' | 'cool' | 'fresh' | 'vintage'>('fresh');

  // Multi-plan state
  const [plans, setPlans] = useState<ContentPlan[]>([plan]);
  const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [showCompareMode, setShowCompareMode] = useState(false);

  // Template preview state
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewTextSections, setPreviewTextSections] = useState<TextSection[]>([]);
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [editedContent, setEditedContent] = useState('');

  const currentPlan = plans[selectedPlanIndex] || plan;

  // Fetch multiple plans on mount
  useEffect(() => {
    const fetchPlans = async () => {
      setLoadingPlans(true);
      try {
        const result = await studioApi.generatePlans(session.session_id, 3);
        if (result.success && result.plans.length > 0) {
          setPlans(result.plans);
        }
      } catch (error) {
        console.error('Failed to generate plans:', error);
      } finally {
        setLoadingPlans(false);
      }
    };
    fetchPlans();
  }, [session.session_id]);

  // Fetch template preview when template image exists
  useEffect(() => {
    console.log("[PlanDialog] hasTemplateImage:", hasTemplateImage);
    console.log("[PlanDialog] templateImageUrl:", templateImageUrl);
    console.log("[PlanDialog] currentPlan:", currentPlan);
    console.log("[PlanDialog] session.brief:", session.brief);
    if (hasTemplateImage && currentPlan) {
      console.log("[PlanDialog] Calling fetchTemplatePreview...");
      fetchTemplatePreview();
    }
  }, [hasTemplateImage, session.session_id, currentPlan?.plan_id]);

  const fetchTemplatePreview = async () => {
    setLoadingPreview(true);
    try {
      // First, get preview text
      const planData = currentPlan as any;
      const textResult = await studioApi.previewText(session.session_id, planData);

      if (textResult.success) {
        setPreviewTitle(textResult.title);
        setPreviewTextSections(textResult.text_sections || []);

        // Then, get template preview image
        if (templateImageUrl) {
          const textItems = textResult.text_sections.map((section: any) => ({
            item_id: section.section_id,
            item_type: section.section_type,
            content: section.content,
            metadata: {},
            status: 'pending',
            generation_prompt: '',
            position: 0,
          }));

          const templateResult = await studioApi.previewTemplate(
            session.session_id,
            textItems,
            templateImageUrl
          );

          if (templateResult.success && templateResult.preview_image_url) {
            setPreviewImageUrl(templateResult.preview_image_url);
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch template preview:', error);
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleRegeneratePreview = async () => {
    await fetchTemplatePreview();
  };

  const handleEditSection = (section: TextSection) => {
    setEditingSection(section.section_id);
    setEditedContent(section.content);
  };

  const handleSaveSection = () => {
    if (editingSection) {
      const updatedSections = previewTextSections.map(section =>
        section.section_id === editingSection
          ? { ...section, content: editedContent, content_words: editedContent.length }
          : section
      );
      setPreviewTextSections(updatedSections);
      setEditingSection(null);
      setEditedContent('');

      // Re-render template preview with updated text
      rerenderTemplatePreview(updatedSections);
    }
  };

  const rerenderTemplatePreview = async (textSections: TextSection[]) => {
    if (!templateImageUrl) return;

    setLoadingPreview(true);
    try {
      const textItems = textSections.map((section: any) => ({
        item_id: section.section_id,
        item_type: section.section_type,
        content: section.content,
        metadata: {},
        status: 'pending',
        generation_prompt: '',
        position: 0,
      }));

      const templateResult = await studioApi.previewTemplate(
        session.session_id,
        textItems,
        templateImageUrl
      );

      if (templateResult.success && templateResult.preview_image_url) {
        setPreviewImageUrl(templateResult.preview_image_url);
      }
    } catch (error) {
      console.error('Failed to rerender template preview:', error);
    } finally {
      setLoadingPreview(false);
    }
  };

  // Get mock image URLs for the preview - react to imageCount changes
  const mockImages = Array.from(
    { length: Math.min(imageCount, 6) },
    (_, i) => `https://picsum.photos/seed/${session.session_id}-${i}/300/300`
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

  // Generate a mock preview title based on brief
  const displayTitle = previewTitle || currentPlan.title || `小红书 ${brief.goal === 'plant' ? '种草' : brief.goal === 'tutorial' ? '教程' : brief.goal === 'review' ? '测评' : '分享'}笔记`;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 bg-gradient-to-r from-rose-500 to-pink-600">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">
                {showCompareMode ? '方案对比' : '预览内容方案'}
              </h2>
              <p className="text-sm text-rose-100 mt-1">
                {showCompareMode ? '选择最满意的一个方案' : '小红书风格预览 · 确认后再开始生成'}
              </p>
            </div>
            {/* Plan switching tabs */}
            {!showCompareMode && plans.length > 1 && (
              <div className="flex items-center gap-2">
                {plans.map((_, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSelectedPlanIndex(idx)}
                    className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                      selectedPlanIndex === idx
                        ? 'bg-white text-rose-600'
                        : 'bg-white/20 text-white hover:bg-white/30'
                    }`}
                  >
                    方案 {idx + 1}
                  </button>
                ))}
                <button
                  onClick={() => setShowCompareMode(true)}
                  className="px-3 py-1 text-xs font-medium rounded-full bg-white/20 text-white hover:bg-white/30 transition-colors flex items-center gap-1"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  对比
                </button>
              </div>
            )}
            {showCompareMode && (
              <button
                onClick={() => setShowCompareMode(false)}
                className="px-3 py-1 text-xs font-medium rounded-full bg-white text-rose-600 hover:bg-rose-50 transition-colors"
              >
                返回单方案
              </button>
            )}
          </div>
        </div>

        {/* Loading state for plans */}
        {loadingPlans && (
          <div className="p-4 bg-amber-50 border-b border-amber-200 flex items-center gap-2">
            <svg className="w-4 h-4 animate-spin text-amber-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm text-amber-700">正在生成多个备选方案...</span>
          </div>
        )}

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-160px)]">
          <div className="grid grid-cols-2 gap-8">
            {/* Left: 小红书 Preview Card */}
            <div className="flex flex-col items-center">
              <h3 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                <svg className="w-4 h-4 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                笔记预览
              </h3>

              {/* 小红书 Style Card */}
              <div className="w-72 bg-white rounded-xl shadow-lg border border-slate-100 overflow-hidden">
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
                    {displayTitle}
                  </h4>

                  {/* Tags */}
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {brief.keywords.slice(0, 3).map((kw, i) => (
                      <span key={i} className="px-2 py-0.5 bg-rose-50 text-rose-500 text-xs rounded-full font-medium">
                        #{kw}
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
                      <span className="text-xs text-slate-600">小红书博主</span>
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
              <div className="w-72 mt-4 bg-slate-50 rounded-xl p-3">
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

              {/* Template Preview Section - Only show when template image exists */}
              {hasTemplateImage && (
                <>
                  {/* Template Preview Image */}
                  <div className="w-72 mt-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-semibold text-slate-700 flex items-center gap-2">
                        <svg className="w-4 h-4 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        文案模板预览
                        {loadingPreview && (
                          <svg className="w-3 h-3 animate-spin text-purple-500" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                        )}
                      </h4>
                      <button
                        onClick={handleRegeneratePreview}
                        disabled={loadingPreview}
                        className="px-2 py-1 bg-purple-500 hover:bg-purple-600 text-white text-xs font-medium rounded transition-colors disabled:opacity-50 flex items-center gap-1"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        重新生成
                      </button>
                    </div>
                    <div className="bg-white rounded-xl shadow-lg border border-slate-100 overflow-hidden">
                      {previewImageUrl ? (
                        <img src={previewImageUrl} alt="模板预览" className="w-full object-contain" />
                      ) : (
                        <div className="w-full aspect-square bg-slate-100 flex items-center justify-center">
                          <span className="text-slate-400 text-sm">点击生成预览</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Text Content Preview */}
                  <div className="w-72 mt-4 bg-slate-50 rounded-xl p-3">
                    <p className="text-xs font-medium text-slate-500 mb-2">文案内容（点击编辑）</p>

                    {/* Title */}
                    {previewTitle && (
                      <div className="mb-2">
                        <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
                          <span className="w-4 h-4 rounded-full bg-rose-500 flex items-center justify-center text-white text-xs">T</span>
                          <span>标题</span>
                        </div>
                        {editingSection === 'title-edit' ? (
                          <div className="space-y-2">
                            <textarea
                              value={editedContent}
                              onChange={(e) => setEditedContent(e.target.value)}
                              className="w-full px-2 py-1 text-xs border border-slate-200 rounded resize-none"
                              rows={2}
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={handleSaveSection}
                                className="px-2 py-1 bg-green-500 text-white text-xs rounded"
                              >
                                保存
                              </button>
                              <button
                                onClick={() => setEditingSection(null)}
                                className="px-2 py-1 bg-slate-200 text-slate-600 text-xs rounded"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div
                            onClick={() => {
                              setEditingSection('title-edit');
                              setEditedContent(previewTitle);
                            }}
                            className="text-xs text-slate-700 bg-white px-2 py-1 rounded border border-transparent hover:border-slate-200 cursor-pointer"
                          >
                            {previewTitle}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Text Sections */}
                    {previewTextSections.filter(s => s.section_type !== 'title').slice(0, 4).map((section, i) => (
                      <div key={section.section_id} className="mb-2">
                        <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
                          <span className={`w-4 h-4 rounded-full flex items-center justify-center text-white text-xs ${
                            section.section_type === 'headline' ? 'bg-amber-500' :
                            section.section_type === 'hashtag' ? 'bg-emerald-500' :
                            'bg-blue-500'
                          }`}>
                            {i + 2}
                          </span>
                          <span className="capitalize">{section.section_type}</span>
                        </div>
                        {editingSection === section.section_id ? (
                          <div className="space-y-2">
                            <textarea
                              value={editedContent}
                              onChange={(e) => setEditedContent(e.target.value)}
                              className="w-full px-2 py-1 text-xs border border-slate-200 rounded resize-none"
                              rows={3}
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={handleSaveSection}
                                className="px-2 py-1 bg-green-500 text-white text-xs rounded"
                              >
                                保存
                              </button>
                              <button
                                onClick={() => setEditingSection(null)}
                                className="px-2 py-1 bg-slate-200 text-slate-600 text-xs rounded"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div
                            onClick={() => handleEditSection(section)}
                            className="text-xs text-slate-700 bg-white px-2 py-1 rounded border border-transparent hover:border-slate-200 cursor-pointer line-clamp-2"
                          >
                            {section.content}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Right: Plan Details */}
            <div className="space-y-4">
              {/* Brief Summary */}
              <div className="bg-gradient-to-br from-rose-50 to-pink-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                  <svg className="w-4 h-4 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  需求概要
                </h3>
                <div className="space-y-2 text-sm">
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-medium text-rose-600 w-12 flex-shrink-0">目标：</span>
                    <span className="text-slate-700">
                      {brief.goal === 'plant' ? '种草推荐' :
                       brief.goal === 'tutorial' ? '教程分享' :
                       brief.goal === 'review' ? '产品测评' :
                       brief.goal === 'lifestyle' ? '生活分享' : brief.goal}
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-medium text-rose-600 w-12 flex-shrink-0">风格：</span>
                    <span className="text-slate-700">{brief.style}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-medium text-rose-600 w-12 flex-shrink-0">关键词：</span>
                    <div className="flex flex-wrap gap-1">
                      {brief.keywords.map((kw, i) => (
                        <span key={i} className="px-2 py-0.5 bg-white text-rose-600 text-xs rounded-full border border-rose-200">
                          {kw}
                        </span>
                      ))}
                    </div>
                  </div>
                  {hasTemplateImage && (
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-medium text-purple-600 w-12 flex-shrink-0">模板：</span>
                      <span className="text-slate-700 text-xs">已上传</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Content Plan */}
              <div className="bg-slate-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                  <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                  </svg>
                  内容方案
                </h3>

                {/* Text Sections */}
                <div className="mb-4">
                  <p className="text-xs font-medium text-slate-500 mb-2">文案结构</p>
                  <div className="space-y-1">
                    {currentPlan.text_sections.map((section, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <span className={`w-6 h-6 rounded flex items-center justify-center text-xs font-medium ${
                          section.section_type === 'title' ? 'bg-rose-100 text-rose-600' :
                          section.section_type === 'headline' ? 'bg-amber-100 text-amber-600' :
                          section.section_type === 'hashtag' ? 'bg-emerald-100 text-emerald-600' :
                          'bg-blue-100 text-blue-600'
                        }`}>
                          {i + 1}
                        </span>
                        <span className="text-slate-600">{section.section_type}</span>
                        <span className="text-slate-400 text-xs">({section.content_words}字)</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Image Plan */}
                {currentPlan.image_plan && (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-slate-500 mb-2">配图计划</p>
                    <div className="bg-white rounded-lg p-3">
                      <div className="flex items-center gap-4">
                        <span className="text-sm text-slate-700">
                          <span className="font-bold text-rose-600">{imageCount}</span> 张图片
                        </span>
                        <span className="text-sm text-slate-500">
                          风格：<span className="text-amber-600">{currentPlan.image_plan.style}</span>
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {currentPlan.image_plan.elements.map((el, i) => (
                          <span key={i} className="px-2 py-0.5 bg-purple-100 text-purple-600 text-xs rounded">
                            {el}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Video/Audio */}
                {(brief.need_video || brief.need_voiceover) && (
                  <div className="flex gap-2">
                    {brief.need_video && (
                      <span className="px-2 py-1 bg-orange-100 text-orange-600 text-xs rounded flex items-center gap-1">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        视频
                      </span>
                    )}
                    {brief.need_voiceover && (
                      <span className="px-2 py-1 bg-cyan-100 text-cyan-600 text-xs rounded flex items-center gap-1">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                        配音
                      </span>
                    )}
                  </div>
                )}

                {/* Drag Adjustments */}
                <div className="mt-4 pt-4 border-t border-slate-200">
                  <p className="text-xs font-medium text-slate-500 mb-3">方案调整</p>

                  {/* Image Count Selector */}
                  <div className="mb-3">
                    <p className="text-xs text-slate-600 mb-1.5">图片数量</p>
                    <div className="flex gap-1">
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((count) => (
                        <button
                          key={count}
                          onClick={() => handleImageCountChange(count)}
                          className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                            imageCount === count
                              ? 'bg-indigo-500 text-white'
                              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                          }`}
                        >
                          {count}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Title Style Selector */}
                  <div className="mb-3">
                    <p className="text-xs text-slate-600 mb-1.5">标题风格</p>
                    <div className="flex gap-2">
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
                              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
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
                    <div className="flex gap-2">
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
                              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                          }`}
                        >
                          <span className={`w-3 h-3 rounded-full ${scheme.color}`} />
                          {scheme.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Warning */}
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <p className="text-sm font-medium text-amber-800">确认后将消耗 API 配额</p>
                    <p className="text-xs text-amber-600 mt-1">生成文案和图片将调用 AI API，确认前请确保方案正确。</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 bg-slate-50">
          <button
            onClick={onCancel}
            className="px-5 py-2 bg-white hover:bg-slate-100 text-slate-700 text-sm font-medium rounded-lg transition-colors border border-slate-200 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
            </svg>
            返回修改
          </button>
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
    </div>
  );
};

export default PlanDialog;
