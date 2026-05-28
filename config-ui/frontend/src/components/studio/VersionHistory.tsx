import React, { useState } from 'react';
import { Session, studioApi, ContentItem } from '../../api/studioApi';
import DiffViewer from './DiffViewer';

interface VersionHistoryProps {
  session: Session;
  onRollback: (version: number) => void;
  onRestoreVersion?: (version: number) => void;
  // 新增：
  onRollbackVersionSelect?: (index: number) => void;  // 用户选择回滚版本时触发
}

const VersionHistory: React.FC<VersionHistoryProps> = ({
  session,
  onRollback,
  onRestoreVersion,
  onRollbackVersionSelect  // 新增
}) => {
  const { versions, current_version } = session;
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [selectedRollbackIndex, setSelectedRollbackIndex] = useState<number | null>(null);
  const [previewItems, setPreviewItems] = useState<ContentItem[] | null>(null);
  const [loading, setLoading] = useState(false);

  // Compare mode state
  const [compareMode, setCompareMode] = useState(false);
  const [compareVersionA, setCompareVersionA] = useState<number | null>(null);
  const [compareVersionB, setCompareVersionB] = useState<number | null>(null);
  const [compareItemsA, setCompareItemsA] = useState<ContentItem[] | null>(null);
  const [compareItemsB, setCompareItemsB] = useState<ContentItem[] | null>(null);

  // Composite mode state
  const [compositeMode, setCompositeMode] = useState(false);
  const [compositeSelections, setCompositeSelections] = useState<Record<string, number>>({}); // item_type_position -> version_number
  const [compositePreviewItems, setCompositePreviewItems] = useState<ContentItem[] | null>(null);
  const [versionContents, setVersionContents] = useState<Record<number, ContentItem[]>>({});

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getCreatorLabel = (creator: string) => {
    const labels: Record<string, { text: string; bg: string; textColor: string }> = {
      orchestrator: { text: '系统', bg: 'bg-indigo-100', textColor: 'text-indigo-700' },
      iterator: { text: '迭代', bg: 'bg-purple-100', textColor: 'text-purple-700' },
      user: { text: '用户', bg: 'bg-blue-100', textColor: 'text-blue-700' },
      system: { text: '系统', bg: 'bg-slate-100', textColor: 'text-slate-700' },
    };
    return labels[creator] || labels.system;
  };

  const handlePreview = async (versionNumber: number) => {
    setLoading(true);
    try {
      const content = await studioApi.getVersionContent(session.session_id, versionNumber);
      setPreviewItems(content.items);
      setSelectedVersion(versionNumber);
    } catch (error) {
      console.error('获取版本内容失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCompareSelect = async (versionNumber: number) => {
    if (!compareMode) return;

    if (compareVersionA === null) {
      setCompareVersionA(versionNumber);
      const content = await studioApi.getVersionContent(session.session_id, versionNumber);
      setCompareItemsA(content.items);
    } else if (compareVersionB === null && versionNumber !== compareVersionA) {
      setCompareVersionB(versionNumber);
      const content = await studioApi.getVersionContent(session.session_id, versionNumber);
      setCompareItemsB(content.items);
    }
  };

  const startCompareMode = () => {
    setCompareMode(true);
    setCompareVersionA(null);
    setCompareVersionB(null);
    setCompareItemsA(null);
    setCompareItemsB(null);
  };

  const exitCompareMode = () => {
    setCompareMode(false);
    setCompareVersionA(null);
    setCompareVersionB(null);
    setCompareItemsA(null);
    setCompareItemsB(null);
  };

  // Composite mode functions
  const startCompositeMode = async () => {
    setCompositeMode(true);
    // 初始化选择：默认都选当前版本
    const initialSelections: Record<string, number> = {};
    items.forEach((item, idx) => {
      initialSelections[`${item.item_type}-${idx}`] = current_version;
    });
    setCompositeSelections(initialSelections);

    // 预加载所有版本的 contents
    const contents: Record<number, ContentItem[]> = {};
    for (const v of versions) {
      try {
        const content = await studioApi.getVersionContent(session.session_id, v.version_number);
        contents[v.version_number] = content.items;
      } catch (error) {
        console.error(`获取版本 ${v.version_number} 内容失败:`, error);
      }
    }
    setVersionContents(contents);
  };

  const exitCompositeMode = () => {
    setCompositeMode(false);
    setCompositeSelections({});
    setCompositePreviewItems(null);
    setVersionContents({});
  };

  const updateCompositeSelection = (itemKey: string, version: number) => {
    setCompositeSelections(prev => ({
      ...prev,
      [itemKey]: version
    }));
    // 更新预览
    updateCompositePreview({ ...compositeSelections, [itemKey]: version });
  };

  const updateCompositePreview = async (selections: Record<string, number>) => {
    // 根据选择构建预览内容
    const previewItemsList: ContentItem[] = [];
    items.forEach((item, idx) => {
      const itemKey = `${item.item_type}-${idx}`;
      const selectedVersion = selections[itemKey] || current_version;
      const versionItems = versionContents[selectedVersion];
      if (versionItems) {
        const matchedItem = versionItems.find(vi => vi.item_type === item.item_type && vi.position === item.position)
          || versionItems.find(vi => vi.item_type === item.item_type)
          || item;
        previewItemsList.push({
          ...matchedItem,
          item_id: item.item_id, // 保留当前 session 的 item_id
        });
      }
    });
    setCompositePreviewItems(previewItemsList);
  };

  const handleRestore = async (versionNumber: number) => {
    if (onRestoreVersion) {
      onRestoreVersion(versionNumber);
    } else {
      // 默认回退行为
      onRollback(versionNumber);
    }
    setSelectedVersion(null);
    setPreviewItems(null);
  };

  const closePreview = () => {
    setSelectedVersion(null);
    setPreviewItems(null);
  };

  const getContentSummary = (items: ContentItem[]) => {
    const imageCount = items.filter(i => i.item_type === 'image').length;
    const textCount = items.filter(i => ['title', 'headline', 'text', 'hashtag', 'cta'].includes(i.item_type)).length;
    const videoCount = items.filter(i => i.item_type === 'video').length;
    const audioCount = items.filter(i => i.item_type === 'audio').length;

    const parts = [];
    if (imageCount > 0) parts.push(`${imageCount}张图`);
    if (textCount > 0) parts.push(`${textCount}段文`);
    if (videoCount > 0) parts.push(`${videoCount}个视频`);
    if (audioCount > 0) parts.push(`${audioCount}段音频`);

    return parts.join('、') || '无内容';
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-slate-800">版本历史</h3>
        <div className="flex items-center gap-3">
          {versions.length >= 2 && (
            <>
              {compareMode || compositeMode ? (
                <button
                  onClick={() => {
                    if (compareMode) exitCompareMode();
                    if (compositeMode) exitCompositeMode();
                  }}
                  className="px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                >
                  退出
                </button>
              ) : (
                <>
                  <button
                    onClick={startCompareMode}
                    className="px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                  >
                    对比
                  </button>
                  <button
                    onClick={startCompositeMode}
                    className="px-3 py-1.5 text-sm text-purple-600 hover:bg-purple-50 rounded-lg transition-colors"
                  >
                    组合
                  </button>
                </>
              )}
            </>
          )}
          <span className="text-sm text-slate-500">
            共 {versions.length} 个版本
          </span>
      </div>

      {versions.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
          <p className="text-slate-500 text-sm">暂无版本记录</p>
        </div>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-slate-200" />

          {/* Version items */}
          <div className="space-y-4 pl-10">
            {[...versions].reverse().map((version) => {
              const isCurrentVersion = version.version_number === current_version;
              const label = getCreatorLabel(version.created_by);

              return (
                <div key={version.version_number} className="relative">
                  {/* Timeline dot */}
                  <div className={`absolute -left-10 top-1 w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                    isCurrentVersion
                      ? 'bg-indigo-500 border-indigo-500'
                      : 'bg-white border-slate-300'
                  }`}>
                    {isCurrentVersion && (
                      <div className="w-2 h-2 bg-white rounded-full" />
                    )}
                  </div>

                  {/* Version card */}
                  <div className={`bg-white border rounded-xl p-4 ${
                    isCurrentVersion ? 'border-indigo-300 shadow-sm' : 'border-slate-200'
                  } ${compareMode ? 'cursor-pointer hover:border-indigo-300' : ''} ${
                    compareVersionA === version.version_number || compareVersionB === version.version_number
                      ? 'ring-2 ring-indigo-500'
                      : ''
                  }`}
                  onClick={() => compareMode && handleCompareSelect(version.version_number)}>
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-800">
                            V{version.version_number}
                          </span>
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${label.bg} ${label.textColor}`}>
                            {label.text}
                          </span>
                          {isCurrentVersion && (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">
                              当前版本
                            </span>
                          )}
                          {compareMode && (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700">
                              {compareVersionA === version.version_number ? '版本A' :
                               compareVersionB === version.version_number ? '版本B' : '点击选择'}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-600 mt-1">
                          {version.change_summary || '无描述'}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">
                          {formatDate(version.created_at)}
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* 预览按钮 */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handlePreview(version.version_number);
                          }}
                          disabled={loading}
                          className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
                        >
                          预览
                        </button>

                        {!isCurrentVersion && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRestore(version.version_number);
                            }}
                            className="px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                          >
                            加载此版本
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {selectedVersion !== null && previewItems && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <h3 className="text-lg font-bold text-slate-800">
                V{selectedVersion} 版本预览
              </h3>
              <button
                onClick={closePreview}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1">
              {/* 内容摘要 */}
              <div className="bg-slate-50 rounded-lg p-3 mb-4">
                <span className="text-sm text-slate-600">
                  {getContentSummary(previewItems)}
                </span>
              </div>

              {/* 文本内容预览 */}
              {previewItems.filter(i => i.item_type === 'title' || i.item_type === 'headline').map(item => (
                <div key={item.item_id} className="mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">
                    {item.item_type === 'title' ? '标题' : '开头'}
                  </span>
                  <p className="text-lg font-bold text-slate-800 mt-1">{item.content}</p>
                </div>
              ))}

              {previewItems.filter(i => i.item_type === 'text').map((item, index) => (
                <div key={item.item_id} className="mb-4">
                  <span className="text-xs text-slate-400">正文 {index + 1}</span>
                  <p className="text-slate-700 mt-1">{item.content}</p>
                </div>
              ))}

              {previewItems.filter(i => i.item_type === 'hashtag').map(item => (
                <div key={item.item_id} className="mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">话题标签</span>
                  <p className="text-slate-700 mt-1">{item.content}</p>
                </div>
              ))}

              {previewItems.filter(i => i.item_type === 'cta').map(item => (
                <div key={item.item_id} className="mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">互动引导</span>
                  <p className="text-slate-700 mt-1">{item.content}</p>
                </div>
              ))}

              {/* 图片预览 */}
              {previewItems.filter(i => i.item_type === 'image').length > 0 && (
                <div className="mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">
                    配图 ({previewItems.filter(i => i.item_type === 'image').length}张)
                  </span>
                  <div className="grid grid-cols-3 gap-2 mt-2">
                    {previewItems.filter(i => i.item_type === 'image').map(item => (
                      <div key={item.item_id} className="aspect-square bg-slate-100 rounded-lg overflow-hidden">
                        {item.content ? (
                          <img
                            src={item.content}
                            alt=""
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
                            无内容
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 视频预览 */}
              {previewItems.filter(i => i.item_type === 'video').map(item => (
                <div key={item.item_id} className="mb-4">
                  <span className="text-xs font-medium text-indigo-600 uppercase">视频</span>
                  {item.content ? (
                    <video
                      src={item.content}
                      controls
                      className="w-full rounded-lg mt-2"
                    />
                  ) : (
                    <div className="aspect-video bg-slate-100 rounded-lg flex items-center justify-center mt-2">
                      <span className="text-slate-400">无内容</span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="p-4 border-t border-slate-200 flex justify-end gap-2">
              <button
                onClick={closePreview}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                关闭
              </button>
              <button
                onClick={() => handleRestore(selectedVersion)}
                className="px-4 py-2 text-sm bg-indigo-600 text-white hover:bg-indigo-700 rounded-lg transition-colors"
              >
                加载此版本
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compare Modal */}
      {compareMode && compareVersionA !== null && compareVersionB !== null && compareItemsA && compareItemsB && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[80vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <div className="flex items-center gap-4">
                <h3 className="text-lg font-bold text-slate-800">
                  版本对比
                </h3>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700">
                    V{compareVersionA} (版本A)
                  </span>
                  <span className="text-slate-400">vs</span>
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
                    V{compareVersionB} (版本B)
                  </span>
                </div>
              </div>
              <button
                onClick={exitCompareMode}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-6">
              {/* Title comparison */}
              {(() => {
                const titleA = compareItemsA.find(i => i.item_type === 'title' || i.item_type === 'headline');
                const titleB = compareItemsB.find(i => i.item_type === 'title' || i.item_type === 'headline');
                if (titleA && titleB && titleA.content !== titleB.content) {
                  return (
                    <div>
                      <h4 className="text-sm font-medium text-slate-700 mb-2">标题对比</h4>
                      <DiffViewer
                        original={titleA.content}
                        modified={titleB.content}
                        title="标题"
                      />
                    </div>
                  );
                }
                return null;
              })()}

              {/* Text sections comparison - compare all text items */}
              {(() => {
                const textsA = compareItemsA.filter(i => i.item_type === 'text');
                const textsB = compareItemsB.filter(i => i.item_type === 'text');
                if (textsA.length > 0 && textsB.length > 0) {
                  const combinedA = textsA.map(t => t.content).join('\n\n');
                  const combinedB = textsB.map(t => t.content).join('\n\n');
                  if (combinedA !== combinedB) {
                    return (
                      <div>
                        <h4 className="text-sm font-medium text-slate-700 mb-2">正文对比</h4>
                        <DiffViewer
                          original={combinedA}
                          modified={combinedB}
                          title="正文内容"
                        />
                      </div>
                    );
                  }
                }
                return null;
              })()}

              {/* Hashtags comparison */}
              {(() => {
                const hashA = compareItemsA.filter(i => i.item_type === 'hashtag').map(t => t.content).join(' ');
                const hashB = compareItemsB.filter(i => i.item_type === 'hashtag').map(t => t.content).join(' ');
                if (hashA && hashB && hashA !== hashB) {
                  return (
                    <div>
                      <h4 className="text-sm font-medium text-slate-700 mb-2">话题标签对比</h4>
                      <DiffViewer
                        original={hashA}
                        modified={hashB}
                        title="话题标签"
                      />
                    </div>
                  );
                }
                return null;
              })()}

              {/* CTA comparison */}
              {(() => {
                const ctaA = compareItemsA.find(i => i.item_type === 'cta');
                const ctaB = compareItemsB.find(i => i.item_type === 'cta');
                if (ctaA && ctaB && ctaA.content !== ctaB.content) {
                  return (
                    <div>
                      <h4 className="text-sm font-medium text-slate-700 mb-2">互动引导对比</h4>
                      <DiffViewer
                        original={ctaA.content}
                        modified={ctaB.content}
                        title="互动引导"
                      />
                    </div>
                  );
                }
                return null;
              })()}
            </div>

            <div className="p-4 border-t border-slate-200 flex justify-end gap-2">
              <button
                onClick={exitCompareMode}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Composite Mode Modal */}
      {compositeMode && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[85vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-gradient-to-r from-purple-500 to-indigo-600">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-bold text-white">版本组合</h3>
                <span className="px-2 py-0.5 bg-white/20 text-white text-xs rounded-full">
                  选择各内容项的来源版本
                </span>
              </div>
              <button
                onClick={exitCompositeMode}
                className="p-1 text-white/80 hover:text-white rounded"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex flex-1 overflow-hidden">
              {/* Left: Selection Panel */}
              <div className="w-1/2 border-r border-slate-200 overflow-y-auto p-4">
                <h4 className="text-sm font-semibold text-slate-700 mb-3">选择内容来源</h4>
                <div className="space-y-4">
                  {items.map((item, idx) => {
                    const itemKey = `${item.item_type}-${idx}`;
                    const itemLabel = item.item_type === 'title' || item.item_type === 'headline' ? '标题' :
                      item.item_type === 'text' ? `正文${idx}` :
                      item.item_type === 'hashtag' ? '话题标签' :
                      item.item_type === 'cta' ? '互动引导' :
                      item.item_type === 'image' ? `配图${idx}` :
                      item.item_type === 'video' ? '视频' :
                      item.item_type === 'audio' ? '配音' : item.item_type;

                    return (
                      <div key={itemKey} className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-medium text-indigo-600 uppercase">{itemLabel}</span>
                          <span className="text-xs text-slate-400">当前: V{compositeSelections[itemKey] || current_version}</span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {versions.map(v => (
                            <button
                              key={v.version_number}
                              onClick={() => updateCompositeSelection(itemKey, v.version_number)}
                              className={`px-2 py-1 text-xs rounded transition-colors ${
                                compositeSelections[itemKey] === v.version_number
                                  ? 'bg-purple-500 text-white'
                                  : 'bg-white text-slate-600 hover:bg-purple-100 border border-slate-200'
                              }`}
                            >
                              V{v.version_number}
                            </button>
                          ))}
                        </div>
                        {/* Show content preview from selected version */}
                        {versionContents[compositeSelections[itemKey]] && (
                          <p className="text-xs text-slate-500 mt-2 line-clamp-2">
                            {versionContents[compositeSelections[itemKey]].find(vi => vi.item_type === item.item_type)?.content || '（无内容）'}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right: Preview Panel */}
              <div className="w-1/2 overflow-y-auto p-4 bg-slate-50">
                <h4 className="text-sm font-semibold text-slate-700 mb-3">组合预览</h4>
                {compositePreviewItems && compositePreviewItems.length > 0 ? (
                  <div className="space-y-3">
                    {/* Title */}
                    {compositePreviewItems.find(i => i.item_type === 'title' || i.item_type === 'headline') && (
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <span className="text-xs font-medium text-indigo-600 uppercase">标题</span>
                        <p className="text-base font-bold text-slate-800 mt-1">
                          {compositePreviewItems.find(i => i.item_type === 'title' || i.item_type === 'headline')?.content || '（无内容）'}
                        </p>
                      </div>
                    )}
                    {/* Text sections */}
                    {compositePreviewItems.filter(i => i.item_type === 'text').length > 0 && (
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <span className="text-xs font-medium text-indigo-600 uppercase">正文</span>
                        <div className="mt-1 space-y-2">
                          {compositePreviewItems.filter(i => i.item_type === 'text').map((item, idx) => (
                            <p key={idx} className="text-sm text-slate-700">{item.content || '（无内容）'}</p>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Hashtags */}
                    {compositePreviewItems.filter(i => i.item_type === 'hashtag').length > 0 && (
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <span className="text-xs font-medium text-indigo-600 uppercase">话题标签</span>
                        <p className="text-sm text-slate-700 mt-1">
                          {compositePreviewItems.filter(i => i.item_type === 'hashtag').map(h => h.content).join(' ')}
                        </p>
                      </div>
                    )}
                    {/* CTA */}
                    {compositePreviewItems.find(i => i.item_type === 'cta') && (
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <span className="text-xs font-medium text-indigo-600 uppercase">互动引导</span>
                        <p className="text-sm text-slate-700 mt-1">
                          {compositePreviewItems.find(i => i.item_type === 'cta')?.content || '（无内容）'}
                        </p>
                      </div>
                    )}
                    {/* Images */}
                    {compositePreviewItems.filter(i => i.item_type === 'image').length > 0 && (
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <span className="text-xs font-medium text-indigo-600 uppercase">配图</span>
                        <div className="grid grid-cols-3 gap-2 mt-2">
                          {compositePreviewItems.filter(i => i.item_type === 'image').map((item, idx) => (
                            <div key={idx} className="aspect-square bg-slate-100 rounded overflow-hidden">
                              {item.content ? (
                                <img src={item.content} alt="" className="w-full h-full object-cover" />
                              ) : (
                                <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">无内容</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-white rounded-lg p-8 text-center">
                    <p className="text-slate-500 text-sm">正在加载预览...</p>
                  </div>
                )}
              </div>
            </div>

            <div className="p-4 border-t border-slate-200 flex justify-between items-center bg-slate-50">
              <div className="text-xs text-slate-500">
                当前选择包含 {Object.keys(compositeSelections).filter(k => compositeSelections[k] !== current_version).length} 项来自非当前版本
              </div>
              <div className="flex gap-2">
                <button
                  onClick={exitCompositeMode}
                  className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    alert('版本组合功能需要后端 API 支持，当前仅实现预览功能。\n\n如需保存组合版本，请联系后端开发人员。');
                  }}
                  className="px-4 py-2 text-sm bg-gradient-to-r from-purple-500 to-indigo-600 text-white hover:from-purple-600 hover:to-indigo-700 rounded-lg transition-colors flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                  </svg>
                  保存组合版本
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Rollback warning */}
      {versions.length > 1 && !compositeMode && (
        <div className="mt-6 bg-slate-50 border border-slate-200 rounded-xl p-4">
          <h4 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            版本回退说明
          </h4>
          <p className="text-sm text-slate-600">
            回退到旧版本会创建一个新的版本记录，不会删除中间的版本。所有修改历史都会被保留。
          </p>
        </div>
      )}
    </div>
    </div>
  );
};

export default VersionHistory;
