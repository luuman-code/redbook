import React, { useState, useRef, useEffect } from 'react';
import { Session, studioApi, ContentItem } from '../../api/studioApi';

interface ContentPreviewProps {
  session: Session;
  onSessionUpdate?: (session: Session) => void;
}

const ContentPreview: React.FC<ContentPreviewProps> = ({ session, onSessionUpdate }) => {
  const { brief, items } = session;
  const [uploadingItemId, setUploadingItemId] = useState<string | null>(null);
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editedContent, setEditedContent] = useState<string>('');
  const [savingItemId, setSavingItemId] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [highlightedItemId, setHighlightedItemId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLDivElement>(null);

  // Group items by type
  const titleItem = items.find(i => i.item_type === 'title' || i.item_type === 'headline');
  const textItems = items.filter(i => i.item_type === 'text');
  const hashtagItems = items.filter(i => i.item_type === 'hashtag');
  const ctaItem = items.find(i => i.item_type === 'cta');
  const imageItems = items.filter(i => i.item_type === 'image');
  const templateItems = items.filter(i => i.item_type === 'composite' || i.item_type === 'template');
  const videoItems = items.filter(i => i.item_type === 'video');
  const audioItems = items.filter(i => i.item_type === 'audio');

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      pending: { bg: 'bg-slate-100', text: 'text-slate-600', label: '待生成' },
      generating: { bg: 'bg-blue-100', text: 'text-blue-600', label: '生成中' },
      completed: { bg: 'bg-emerald-100', text: 'text-emerald-600', label: '已完成' },
      failed: { bg: 'bg-red-100', text: 'text-red-600', label: '失败' },
      skipped: { bg: 'bg-slate-100', text: 'text-slate-400', label: '跳过' },
    };
    const badge = badges[status] || badges.pending;
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>
        {badge.label}
      </span>
    );
  };

  // 获取图片/视频/音频的 src
  const getMediaSrc = (item: ContentItem) => {
    // 优先使用 local_path 字段
    if (item.local_path) {
      // 转换为 HTTP URL（通过后端静态文件服务）
      // local_path 格式: data/studio/sessions/xxx/images/xxx.png
      // 静态文件挂载在 /static/studio -> {app}/data/studio/
      // 所以需要去掉 "data/studio/" 前缀
      const normalizedPath = item.local_path.replace(/\\/g, '/').replace(/^data\/studio\//, '');
      return `/static/studio/${normalizedPath}`;
    }
    // 其次使用 metadata 中的 local_path
    if (item.metadata?.local_path) {
      const normalizedPath = item.metadata.local_path.replace(/\\/g, '/').replace(/^data\/studio\//, '');
      return `/static/studio/${normalizedPath}`;
    }
    // 最后使用 content (URL 或 base64)
    return item.content;
  };

  // 处理文件上传
  const handleFileUpload = async (itemId: string, file: File) => {
    setUploadingItemId(itemId);
    try {
      const result = await studioApi.uploadItemContent(session.session_id, itemId, file);
      if (result.success) {
        // 刷新 session 获取更新后的 items
        const updated = await studioApi.getSession(session.session_id);
        if (onSessionUpdate) {
          onSessionUpdate(updated);
        }
      }
    } catch (error) {
      console.error('上传失败:', error);
    } finally {
      setUploadingItemId(null);
    }
  };

  // 渲染上传按钮
  const renderUploadButton = (item: ContentItem, accept: string) => (
    <label className="cursor-pointer px-3 py-1.5 bg-white/90 hover:bg-white rounded text-sm shadow-sm">
      {uploadingItemId === item.item_id ? '上传中...' : '替换'}
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFileUpload(item.item_id, file);
        }}
        disabled={uploadingItemId !== null}
      />
    </label>
  );

  // Handle inline edit start
  const handleEditStart = (item: ContentItem) => {
    setEditingItemId(item.item_id);
    setEditedContent(item.content || '');
  };

  // Handle edit save
  const handleEditSave = async () => {
    if (!editingItemId) return;

    setSavingItemId(editingItemId);
    try {
      const result = await studioApi.updateItemContent(
        session.session_id,
        editingItemId,
        editedContent
      );

      if (result.success) {
        // 设置高亮
        setHighlightedItemId(editingItemId);
        // 刷新 session 以获取更新后的数据
        const updated = await studioApi.getSession(session.session_id);
        if (onSessionUpdate) {
          onSessionUpdate(updated);
        }
      }
    } catch (error) {
      console.error('保存失败:', error);
    } finally {
      setSavingItemId(null);
      setEditingItemId(null);
    }
  };

  // Handle edit cancel
  const handleEditCancel = () => {
    setEditingItemId(null);
    setEditedContent('');
  };

  // Focus input when editing starts
  useEffect(() => {
    if (editingItemId && editInputRef.current) {
      editInputRef.current.focus();
    }
  }, [editingItemId]);

  // Auto-clear highlight after 2 seconds
  useEffect(() => {
    if (highlightedItemId) {
      const timer = setTimeout(() => {
        setHighlightedItemId(null);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [highlightedItemId]);

  // Handle copy to clipboard
  const handleCopy = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
    } catch (error) {
      console.error('复制失败:', error);
    }
  };

  // Handle regenerate (trigger feedback with request for regeneration)
  const handleRegenerate = async (itemType: string, feedback?: string) => {
    // 构建反馈消息，没有提供 feedback 时使用默认消息
    const feedbackMessage = feedback || `请重新生成${itemType}，保持其他内容不变`;

    setRegenerating(true);
    try {
      const response = await studioApi.submitFeedback(session.session_id, feedbackMessage);

      if (response.success) {
        // 刷新 session 获取最新状态
        const updated = await studioApi.getSession(session.session_id);
        if (onSessionUpdate) {
          onSessionUpdate(updated);
        }
      }
    } catch (error) {
      console.error('重新生成请求失败:', error);
    } finally {
      setRegenerating(false);
    }
  };

  // Shortcut action feedback text
  const shortcutActions = [
    { label: '更活泼', feedback: '语气更活泼一些' },
    { label: '更专业', feedback: '语气更专业正式一些' },
    { label: '缩短一点', feedback: '内容可以更简洁一些' },
    { label: '详细一点', feedback: '内容可以更详细丰富一些' },
    { label: '换个角度', feedback: '换一个角度来写' },
  ];

  // Action button group component
  const ActionButtons: React.FC<{
    item: ContentItem;
    content: string;
    itemType: string;
  }> = ({ item, content, itemType }) => (
    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button
        onClick={() => handleEditStart(item)}
        className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
        title="编辑"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      </button>
      <button
        onClick={() => handleCopy(content)}
        className="p-1.5 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
        title="复制"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
        </svg>
      </button>
      <button
        onClick={() => handleRegenerate(itemType)}
        className="p-1.5 text-slate-500 hover:text-amber-600 hover:bg-amber-50 rounded transition-colors"
        title="重新生成"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>
  );

  return (
    <div className="h-full overflow-y-auto space-y-8 p-6">
      {/* Brief Info */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          需求概要
        </h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500">目标：</span>
            <span className="text-slate-800 font-medium">
              {brief.goal === 'plant' ? '种草' :
               brief.goal === 'tutorial' ? '教程' :
               brief.goal === 'review' ? '测评' :
               brief.goal === 'lifestyle' ? '生活分享' : brief.goal}
            </span>
          </div>
          <div>
            <span className="text-slate-500">风格：</span>
            <span className="text-slate-800 font-medium">{brief.style}</span>
          </div>
          <div className="col-span-2">
            <span className="text-slate-500">关键词：</span>
            <span className="text-slate-800">
              {brief.keywords?.join(', ') || '无'}
            </span>
          </div>
          <div className="col-span-2">
            <span className="text-slate-500">原始需求：</span>
            <span className="text-slate-800">{brief.raw_input}</span>
          </div>
        </div>
      </div>

      {/* Generated Content */}
      <div>
        <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          生成内容
        </h3>

        {/* Shortcut Action Chips */}
        <div className="flex flex-wrap gap-2 mb-4 pb-4 border-b border-slate-100">
          {shortcutActions.map((action) => (
            <button
              key={action.label}
              onClick={() => handleRegenerate('内容', action.feedback)}
              className="px-3 py-1.5 bg-slate-100 hover:bg-indigo-100 text-slate-600 hover:text-indigo-600 rounded-full text-sm transition-colors flex items-center gap-1"
            >
              {action.label}
            </button>
          ))}
        </div>

        {items.length === 0 ? (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
            <p className="text-slate-500 text-sm">点击「生成内容」开始创作</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Title */}
            {titleItem && (
              <div className={`bg-white border rounded-xl p-5 group relative transition-all duration-500 ${
                highlightedItemId === titleItem.item_id && !editingItemId
                  ? 'ring-2 ring-amber-400 bg-amber-50/30'
                  : 'border-slate-200'
              }`}>
                <div className="flex items-start justify-between mb-2">
                  <span className="text-xs font-medium text-indigo-600 uppercase">标题</span>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(titleItem.status)}
                    <ActionButtons item={titleItem} content={titleItem.content || ''} itemType="标题" />
                  </div>
                </div>
                {editingItemId === titleItem.item_id ? (
                  <div className="mt-2">
                    <div
                      ref={editInputRef}
                      contentEditable
                      className="text-xl font-bold text-slate-800 outline-none border-b-2 border-indigo-500 pb-1"
                      onInput={(e) => setEditedContent(e.currentTarget.textContent || '')}
                      dangerouslySetInnerHTML={{ __html: editedContent }}
                    />
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={handleEditSave}
                        className="px-3 py-1 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-medium rounded-lg transition-colors"
                      >
                        保存
                      </button>
                      <button
                        onClick={handleEditCancel}
                        className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xl font-bold text-slate-800">
                    {titleItem.content || '（待生成）'}
                  </p>
                )}
              </div>
            )}

            {/* Text Sections */}
            {textItems.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-indigo-600 uppercase">正文</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{textItems.length} 段</span>
                    {textItems[0] && <ActionButtons item={textItems[0]} content={textItems.map(t => t.content).join('\n\n')} itemType="正文" />}
                  </div>
                </div>
                <div className="space-y-4">
                  {textItems.map((item, index) => (
                    <div key={item.item_id} className={`group relative p-2 -mx-2 rounded-lg transition-all duration-500 ${
                        highlightedItemId === item.item_id && editingItemId !== item.item_id
                          ? 'bg-amber-50 ring-2 ring-amber-400'
                          : ''
                      }`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-400">第 {index + 1} 段</span>
                        <div className="flex items-center gap-2">
                          {getStatusBadge(item.status)}
                          <ActionButtons item={item} content={item.content || ''} itemType={`正文${index + 1}`} />
                        </div>
                      </div>
                      {editingItemId === item.item_id ? (
                        <div>
                          <div
                            ref={editInputRef}
                            contentEditable
                            className="text-slate-700 leading-relaxed outline-none border-b-2 border-indigo-500 pb-1 whitespace-pre-wrap"
                            onInput={(e) => setEditedContent(e.currentTarget.textContent || '')}
                            dangerouslySetInnerHTML={{ __html: editedContent }}
                          />
                          <div className="flex gap-2 mt-3">
                            <button
                              onClick={handleEditSave}
                              className="px-3 py-1 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-medium rounded-lg transition-colors"
                            >
                              保存
                            </button>
                            <button
                              onClick={handleEditCancel}
                              className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors"
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p className="text-slate-700 leading-relaxed">
                          {item.content || '（待生成）'}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hashtags */}
            {hashtagItems.length > 0 && (
              <div className={`bg-white border rounded-xl p-5 group relative transition-all duration-500 ${
                highlightedItemId === hashtagItems[0]?.item_id && !editingItemId
                  ? 'ring-2 ring-amber-400 bg-amber-50/30'
                  : 'border-slate-200'
              }`}>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-indigo-600 uppercase">话题标签</span>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(hashtagItems[0]?.status || 'pending')}
                    <ActionButtons item={hashtagItems[0]} content={hashtagItems.map(h => h.content).join(' ')} itemType="话题标签" />
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {hashtagItems.map((item) => (
                    <span
                      key={item.item_id}
                      className={`px-3 py-1 text-slate-700 rounded-full text-sm hover:bg-indigo-50 hover:text-indigo-600 transition-colors cursor-pointer ${
                        highlightedItemId === item.item_id && editingItemId !== item.item_id
                          ? 'bg-amber-100 ring-2 ring-amber-400'
                          : 'bg-slate-100'
                      }`}
                      title="点击复制"
                      onClick={() => handleCopy(item.content)}
                    >
                      {item.content || '（待生成）'}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* CTA */}
            {ctaItem && (
              <div className={`bg-white border rounded-xl p-5 group relative transition-all duration-500 ${
                highlightedItemId === ctaItem.item_id && !editingItemId
                  ? 'ring-2 ring-amber-400 bg-amber-50/30'
                  : 'border-slate-200'
              }`}>
                <div className="flex items-start justify-between mb-2">
                  <span className="text-xs font-medium text-indigo-600 uppercase">互动引导</span>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(ctaItem.status)}
                    <ActionButtons item={ctaItem} content={ctaItem.content || ''} itemType="互动引导" />
                  </div>
                </div>
                {editingItemId === ctaItem.item_id ? (
                  <div>
                    <div
                      ref={editInputRef}
                      contentEditable
                      className="text-slate-700 outline-none border-b-2 border-indigo-500 pb-1"
                      onInput={(e) => setEditedContent(e.currentTarget.textContent || '')}
                      dangerouslySetInnerHTML={{ __html: editedContent }}
                    />
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={handleEditSave}
                        className="px-3 py-1 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-medium rounded-lg transition-colors"
                      >
                        保存
                      </button>
                      <button
                        onClick={handleEditCancel}
                        className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-700">
                    {ctaItem.content || '（待生成）'}
                  </p>
                )}
              </div>
            )}

            {/* Images */}
            {imageItems.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">配图</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{imageItems.length} 张</span>
                    {imageItems[0] && <ActionButtons item={imageItems[0]} content="" itemType="配图" />}
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  {imageItems.map((item) => (
                    <div key={item.item_id} className="relative aspect-square bg-slate-100 rounded-lg overflow-hidden group">
                      {item.content || item.metadata?.local_path || item.local_path ? (
                        <>
                          <img
                            src={getMediaSrc(item)}
                            alt=""
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              // 如果 file:// 加载失败，尝试直接使用 content
                              if (item.content) {
                                (e.target as HTMLImageElement).src = item.content;
                              }
                            }}
                          />
                          {/* Hover overlay with actions */}
                          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-2 transition-opacity">
                            <button
                              onClick={() => handleRegenerate(`image-${item.item_id}`)}
                              className="p-2 bg-white/90 hover:bg-white rounded-lg text-slate-700 transition-colors"
                              title="重新生成"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                              </svg>
                            </button>
                            {renderUploadButton(item, 'image/*')}
                          </div>
                        </>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-400">
                          {getStatusBadge(item.status)}
                        </div>
                      )}
                      {uploadingItemId === item.item_id && (
                        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                          <span className="text-white text-sm">上传中...</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Template Images */}
            {templateItems.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-xs font-medium text-pink-600 uppercase">模板图片</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{templateItems.length} 张</span>
                    {templateItems[0] && <ActionButtons item={templateItems[0]} content="" itemType="模板" />}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {templateItems.map((item) => (
                    <div key={item.item_id} className="relative bg-slate-100 rounded-lg overflow-hidden group">
                      {item.content || item.metadata?.local_path || item.local_path ? (
                        <>
                          <img
                            src={getMediaSrc(item)}
                            alt="模板图片"
                            className="w-full object-contain"
                            onError={(e) => {
                              if (item.content) {
                                (e.target as HTMLImageElement).src = item.content;
                              }
                            }}
                          />
                          {/* Hover overlay with actions */}
                          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-2 transition-opacity">
                            <button
                              onClick={() => handleRegenerate(`template-${item.item_id}`)}
                              className="p-2 bg-white/90 hover:bg-white rounded-lg text-slate-700 transition-colors"
                              title="重新生成"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                              </svg>
                            </button>
                            {renderUploadButton(item, 'image/*')}
                          </div>
                        </>
                      ) : (
                        <div className="w-full h-48 flex items-center justify-center text-slate-400">
                          {getStatusBadge(item.status)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Video */}
            {videoItems.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">视频</span>
                  {getStatusBadge(videoItems[0]?.status || 'pending')}
                </div>
                {videoItems[0]?.content || videoItems[0]?.metadata?.local_path || videoItems[0]?.local_path ? (
                  <div className="relative group">
                    <video
                      src={getMediaSrc(videoItems[0])}
                      controls
                      className="w-full rounded-lg"
                    />
                    {/* 悬停显示替换按钮 */}
                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {renderUploadButton(videoItems[0], 'video/*')}
                    </div>
                  </div>
                ) : (
                  <div className="aspect-video bg-slate-100 rounded-lg flex items-center justify-center">
                    <span className="text-slate-400">（待生成）</span>
                  </div>
                )}
              </div>
            )}

            {/* Audio */}
            {audioItems.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">配音</span>
                  {getStatusBadge(audioItems[0]?.status || 'pending')}
                </div>
                {audioItems[0]?.content || audioItems[0]?.metadata?.local_path || audioItems[0]?.local_path || audioItems[0]?.metadata?.audio_data ? (
                  <div className="relative">
                    <audio
                      src={getMediaSrc(audioItems[0]) || (audioItems[0]?.metadata?.audio_data ? `data:audio/mp3;base64,${audioItems[0].metadata.audio_data}` : '')}
                      controls
                      className="w-full"
                    />
                    {/* 悬停显示替换按钮 */}
                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {renderUploadButton(audioItems[0], 'audio/*')}
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-100 rounded-lg flex items-center justify-center py-8">
                    <span className="text-slate-400">（待生成）</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ContentPreview;
