import React, { useState, useEffect } from 'react';
import { studioApi, Session, ChatMessage, PlanData, Material } from '../../api/studioApi';
import ContentPreview from './ContentPreview';
import GenerationProgress from './GenerationProgress';
import { ChatPanel } from '../chat';
import VersionHistory from './VersionHistory';

interface ToastMessage {
  type: 'success' | 'error' | 'info';
  text: string;
}

const StudioPage: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [currentPlanData, setCurrentPlanData] = useState<PlanData | null>(null);
  // Materials state that persists across messages in a session
  const [sessionMaterials, setSessionMaterials] = useState<Material[]>([]);

  // Streaming content state
  const [streamingContent, setStreamingContent] = useState<Record<string, string>>({});

  // UI state
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [selectedRollbackIndex, setSelectedRollbackIndex] = useState<number | null>(null);

  // Template preview state
  const [templatePreviewTitle, setTemplatePreviewTitle] = useState('');
  const [templatePreviewSections, setTemplatePreviewSections] = useState<any[]>([]);
  const [templatePreviewImageUrl, setTemplatePreviewImageUrl] = useState<string | null>(null);
  const [loadingTemplatePreview, setLoadingTemplatePreview] = useState(false);

  // Fetch template preview when plan is generated
  useEffect(() => {
    if (currentPlanData && activeSession?.brief?.template_image_url) {
      fetchTemplatePreview();
    }
  }, [currentPlanData, activeSession?.brief?.template_image_url]);

  // Fetch version preview when selectedRollbackIndex changes
  useEffect(() => {
    if (selectedRollbackIndex !== null && activeSession) {
      // selectedRollbackIndex = 0 means V1, 1 means V2, etc.
      const versionNumber = selectedRollbackIndex + 1;
      fetchVersionPreview(versionNumber);
    }
  }, [selectedRollbackIndex, activeSession]);

  const fetchVersionPreview = async (versionNumber: number) => {
    if (!activeSession) return;

    setLoadingTemplatePreview(true);
    try {
      // 获取指定版本的内容
      const versionContent = await studioApi.getVersionContent(activeSession.session_id, versionNumber);
      console.log('[StudioPage] Fetched version content:', versionContent);

      // 从 versionContent.items 中提取文本内容和预览图
      const titleItem = versionContent.items?.find(i => i.item_type === 'title' || i.item_type === 'headline');
      const textItems = versionContent.items?.filter(i => i.item_type === 'text');
      const imageItems = versionContent.items?.filter(i => i.item_type === 'image');
      const hashtagItems = versionContent.items?.filter(i => i.item_type === 'hashtag');
      const ctaItems = versionContent.items?.filter(i => i.item_type === 'cta');

      // 更新标题
      if (titleItem?.content) {
        setTemplatePreviewTitle(titleItem.content);
      }

      // 更新文本段落
      if (textItems && textItems.length > 0) {
        const sections = textItems.map((item, idx) => ({
          section_id: item.item_id || `section_${idx}`,
          section_type: 'text',
          content: item.content || '',
        }));
        setTemplatePreviewSections(sections);
      }

      // 更新预览图（如果有）
      if (imageItems && imageItems.length > 0 && imageItems[0].content) {
        setTemplatePreviewImageUrl(imageItems[0].content);
      } else if (activeSession.brief?.template_image_url) {
        // 如果版本内容中没有预览图，使用模板图片生成
        const textResult = await studioApi.previewText(activeSession.session_id, versionContent.plan || currentPlanData);
        if (textResult.success) {
          const templateResult = await studioApi.previewTemplate(
            activeSession.session_id,
            textResult.text_sections?.map((s: any, idx: number) => ({
              item_id: s.section_id || `section_${idx}`,
              item_type: s.section_type || 'text',
              content: s.content || '',
              metadata: {},
              status: 'pending',
              generation_prompt: '',
              position: 0,
            })) || [],
            activeSession.brief.template_image_url
          );
          if (templateResult.success && templateResult.preview_image_url) {
            setTemplatePreviewImageUrl(templateResult.preview_image_url);
          }
        }
      }
    } catch (error) {
      console.error('[StudioPage] Failed to fetch version preview:', error);
    } finally {
      setLoadingTemplatePreview(false);
    }
  };

  const fetchTemplatePreview = async () => {
    if (!currentPlanData || !activeSession?.brief?.template_image_url) return;

    // 优先从会话 metadata 中读取已保存的预览图
    if (activeSession?.metadata?.preview_image_url) {
      console.log('[StudioPage] Using cached preview from session metadata');
      setTemplatePreviewImageUrl(activeSession.metadata.preview_image_url);
      if (activeSession.metadata.preview_title) {
        setTemplatePreviewTitle(activeSession.metadata.preview_title);
      }
      if (activeSession.metadata.preview_text_sections) {
        setTemplatePreviewSections(activeSession.metadata.preview_text_sections);
      }
      return;
    }

    setLoadingTemplatePreview(true);
    try {
      const textResult = await studioApi.previewText(activeSession.session_id, currentPlanData);
      if (textResult.success) {
        setTemplatePreviewTitle(textResult.title);
        setTemplatePreviewSections(textResult.text_sections || []);

        const templateResult = await studioApi.previewTemplate(
          activeSession.session_id,
          textResult.text_sections.map((s: any) => ({
            item_id: s.section_id,
            item_type: s.section_type,
            content: s.content,
            metadata: {},
            status: 'pending',
            generation_prompt: '',
            position: 0,
          })),
          activeSession.brief.template_image_url
        );

        if (templateResult.success && templateResult.preview_image_url) {
          setTemplatePreviewImageUrl(templateResult.preview_image_url);
        }
      }
    } catch (error) {
      console.error('Failed to fetch template preview:', error);
    } finally {
      setLoadingTemplatePreview(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  // Load toasts when active session changes
  useEffect(() => {
    if (activeSession) {
      setChatMessages(activeSession.messages || []);
      // 从 activeSession 的 messages 中提取 plan_data
      if (activeSession.messages && activeSession.messages.length > 0) {
        const planMsg = activeSession.messages.find(msg => msg.metadata?.plan_data);
        if (planMsg?.metadata?.plan_data) {
          setCurrentPlanData(planMsg.metadata.plan_data);
        } else {
          setCurrentPlanData(null);
        }
      } else {
        setCurrentPlanData(null);
      }
    } else {
      setChatMessages([]);
      setCurrentPlanData(null);
    }
  }, [activeSession]);

  const loadSessions = async () => {
    try {
      const data = await studioApi.listSessions();
      const sessionList: Session[] = data.sessions.map((s) => ({
        session_id: s.session_id,
        status: s.status,
        current_version: s.current_version,
        brief: s.brief as any,
        plan: {} as any,
        items: [],
        created_at: s.created_at,
        updated_at: s.updated_at,
        versions: [],
        messages: [],
      }));
      setSessions(sessionList);
    } catch (error) {
      console.error('加载会话列表失败:', error);
      setSessions([]);
    }
  };

  // Handle chat message send - uses sessionMaterials for persistent materials
  const handleSendMessage = async (message: string, materials?: Material[]) => {
    if (!activeSession) {
      setToast({ type: 'error', text: '请先点击"新建会话"创建会话' });
      setTimeout(() => setToast(null), 3000);
      return;
    }

    // Add user message to local state immediately
    const userMsg: ChatMessage = {
      message_id: `temp_${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };
    setChatMessages(prev => [...prev, userMsg]);
    setIsTyping(true);

    // Use sessionMaterials (persistent) instead of locally passed materials
    const materialsToSend = sessionMaterials.length > 0 ? sessionMaterials : materials;

    try {
      const response = await studioApi.chat(activeSession.session_id, message, materialsToSend);
      if (response.success) {
        const updated = await studioApi.getSession(activeSession.session_id);
        setActiveSession(updated);
        setChatMessages(updated.messages || []);

        // 优先使用 response 中的 plan_data（直接从后端获取）
        if (response.plan_data) {
          setCurrentPlanData(response.plan_data);
        } else if (updated.messages && updated.messages.length > 0) {
          // 备用：从消息 metadata 中提取
          const lastMsg = updated.messages[updated.messages.length - 1];
          if (lastMsg.metadata?.plan_data) {
            setCurrentPlanData(lastMsg.metadata.plan_data);
          }
        }

        // 【重要修复】如果 Agent 返回了 preview_image_url，直接使用它
        // 这样可以避免前端重新调用 preview_template API 生成新的预览图
        if (response.preview_image_url) {
          console.log('[StudioPage] Using preview_image_url from Agent response:', response.preview_image_url);
          setTemplatePreviewImageUrl(response.preview_image_url);
        }
        if (response.preview_title) {
          setTemplatePreviewTitle(response.preview_title);
        }
        if (response.preview_text_sections) {
          setTemplatePreviewSections(response.preview_text_sections);
        }
      } else {
        setToast({ type: 'error', text: response.error || '发送消息失败' });
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      setToast({ type: 'error', text: '发送消息失败' });
    } finally {
      setIsTyping(false);
    }
  };

  const handleGenerate = async () => {
    if (!activeSession) return;

    setLoading(true);
    setStreamingContent({});
    try {
      const pollInterval = setInterval(async () => {
        try {
          const updated = await studioApi.getSession(activeSession.session_id);
          if (updated.status !== 'generating') {
            clearInterval(pollInterval);
            setActiveSession(updated);
            setStreamingContent({});
            if (updated.status === 'completed') {
              setToast({ type: 'success', text: '生成完成' });
            }
          }
        } catch (e) {
          console.error('Polling error:', e);
        }
      }, 1000);

      const response = await studioApi.generate(activeSession.session_id);
      clearInterval(pollInterval);

      if (response.success) {
        const updated = await studioApi.getSession(activeSession.session_id);
        setActiveSession(updated);
        setStreamingContent({});
        setToast({ type: 'success', text: `生成完成 (${response.items_count} 项内容)` });
      } else {
        setToast({ type: 'error', text: response.error || '生成失败' });
      }
    } catch (error) {
      setToast({ type: 'error', text: '生成内容失败' });
    } finally {
      setLoading(false);
      setTimeout(() => setToast(null), 3000);
    }
  };

  const handleTokenStream = (itemId: string, token: string, done: boolean) => {
    if (done) {
      setStreamingContent(prev => {
        const newContent = { ...prev };
        delete newContent[itemId];
        return newContent;
      });
    } else {
      setStreamingContent(prev => {
        const currentContent = (prev[itemId] || '') + token;
        if (currentContent.includes('Final Text:')) {
          const parts = currentContent.split('Final Text:');
          return { ...prev, [itemId]: parts[parts.length - 1].trim() };
        }
        return { ...prev, [itemId]: currentContent };
      });
    }
  };

  const handleGenerationComplete = () => {
    if (activeSession) {
      studioApi.getSession(activeSession.session_id).then(updated => {
        setActiveSession(updated);
        setStreamingContent({});
      });
    }
  };

  const handleReview = async () => {
    if (!activeSession) return;

    setLoading(true);
    try {
      const response = await studioApi.review(activeSession.session_id);
      if (response.passed) {
        setToast({ type: 'success', text: `审核通过 (评分: ${response.score.toFixed(1)}/10)` });
      } else {
        setToast({ type: 'error', text: `审核未通过: ${response.overall_comment}` });
      }
    } catch (error) {
      setToast({ type: 'error', text: '审核失败' });
    } finally {
      setLoading(false);
      setTimeout(() => setToast(null), 3000);
    }
  };

  const handlePublish = async () => {
    if (!activeSession) return;

    setLoading(true);
    try {
      const response = await studioApi.publish(activeSession.session_id, 'simulate');
      if (response.success) {
        setToast({ type: 'success', text: '发布成功' });
      } else {
        setToast({ type: 'error', text: response.error || '发布失败' });
      }
    } catch (error) {
      setToast({ type: 'error', text: '发布失败' });
    } finally {
      setLoading(false);
      setTimeout(() => setToast(null), 3000);
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    try {
      const session = await studioApi.getSession(sessionId);
      setActiveSession(session);
      // 从新会话的 messages 中提取 plan_data
      if (session.messages && session.messages.length > 0) {
        const planMsg = session.messages.find(msg => msg.metadata?.plan_data);
        if (planMsg?.metadata?.plan_data) {
          setCurrentPlanData(planMsg.metadata.plan_data);
        } else {
          setCurrentPlanData(null);
        }
      } else {
        setCurrentPlanData(null);
      }
    } catch (error) {
      setToast({ type: 'error', text: '获取会话失败' });
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await studioApi.deleteSession(sessionId);
      setSessions(sessions.filter(s => s.session_id !== sessionId));
      if (activeSession?.session_id === sessionId) {
        setActiveSession(null);
        setCurrentPlanData(null);
      }
      setToast({ type: 'success', text: '会话已删除' });
    } catch (error) {
      setToast({ type: 'error', text: '删除失败' });
    }
    setTimeout(() => setToast(null), 3000);
  };

  const handlePlanDataUpdate = (planData: PlanData) => {
    setCurrentPlanData(planData);
  };

  const handleRestoreVersion = (version: number) => {
    console.log('Restoring to version:', version);
    // Handle version restore logic here
  };

  const statusLabels: Record<string, { text: string; color: string }> = {
    created: { text: '已创建', color: 'bg-slate-100 text-slate-700' },
    planning: { text: '规划中', color: 'bg-blue-100 text-blue-700' },
    confirmed: { text: '已确认', color: 'bg-teal-100 text-teal-700' },
    generating: { text: '生成中', color: 'bg-indigo-100 text-indigo-700' },
    reviewing: { text: '审核中', color: 'bg-amber-100 text-amber-700' },
    iterating: { text: '迭代中', color: 'bg-purple-100 text-purple-700' },
    completed: { text: '已完成', color: 'bg-emerald-100 text-emerald-700' },
    published: { text: '已发布', color: 'bg-green-100 text-green-700' },
    cancelled: { text: '已取消', color: 'bg-red-100 text-red-700' },
  };

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Left Sidebar - Fixed width w-96 */}
      <div className={`${leftPanelCollapsed ? 'w-12' : 'w-96'} border-r flex flex-col bg-white transition-all duration-300`}>
        {/* Collapse toggle */}
        <button
          onClick={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
          className="absolute top-4 -right-3 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-sm z-10 hover:bg-slate-50"
        >
          <svg className={`w-3 h-3 text-slate-500 transition-transform ${leftPanelCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {!leftPanelCollapsed && (
          <>
            {/* Logo/Header area */}
            <div className="p-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-500 rounded-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-base font-bold text-slate-800">小红书 Studio</h1>
                  <p className="text-xs text-slate-500">AI 内容创作</p>
                </div>
              </div>
            </div>

            {/* New Session Button */}
            <div className="p-4 border-b border-slate-100">
              <button
                onClick={async () => {
                  try {
                    setLoading(true);
                    const response = await studioApi.createSession({
                      user_input: '',
                      materials: [],
                      auto_generate: false,
                    });
                    if (response.success && response.session_id) {
                      const session = await studioApi.getSession(response.session_id);
                      setSessions(prev => [session, ...prev]);
                      setActiveSession(session);
                      setChatMessages([]);
                      setCurrentPlanData(null);
                      setToast({ type: 'success', text: '会话已创建' });
                    } else {
                      setToast({ type: 'error', text: '创建会话失败' });
                    }
                  } catch (error) {
                    console.error('创建会话失败:', error);
                    setToast({ type: 'error', text: '创建会话失败' });
                  } finally {
                    setLoading(false);
                    setTimeout(() => setToast(null), 3000);
                  }
                }}
                className="w-full px-4 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
                新建会话
              </button>
            </div>

            {/* Session List */}
            <div className="flex-1 overflow-y-auto border-b border-slate-100">
              {sessions.length === 0 ? (
                <div className="p-4 text-center text-slate-500 text-sm">
                  暂无会话记录
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {sessions.map((session) => (
                    <div
                      key={session.session_id}
                      className={`p-4 cursor-pointer hover:bg-slate-50 transition-colors ${
                        activeSession?.session_id === session.session_id ? 'bg-indigo-50' : ''
                      }`}
                      onClick={() => handleSelectSession(session.session_id)}
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
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusLabels[session.status]?.color || 'bg-slate-100 text-slate-700'}`}>
                          {statusLabels[session.status]?.text || session.status}
                        </span>
                      </div>
                      <div className="flex gap-2 mt-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSession(session.session_id);
                          }}
                          className="text-xs text-red-500 hover:text-red-600"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Plan Preview */}
            <div className="border-b border-slate-100">
              <div className="p-4">
                {/* 版本标签栏 */}
                {activeSession?.versions && activeSession.versions.length > 0 && (
                  <div className="flex items-center gap-1 px-2 py-1 bg-slate-50 rounded-lg mb-2">
                    {activeSession.versions.map(v => (
                      <button
                        key={v.version_number}
                        onClick={() => setSelectedRollbackIndex(v.version_number - 1)}
                        className={`px-2 py-1 text-xs rounded-full transition-colors ${
                          selectedRollbackIndex === v.version_number - 1
                            ? 'bg-indigo-500 text-white'
                            : 'bg-white text-slate-600 hover:bg-indigo-100 border border-slate-200'
                        }`}
                      >
                        V{v.version_number}
                      </button>
                    ))}
                  </div>
                )}
                <h3 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
                  <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  当前方案
                </h3>

                {/* Template Preview Section */}
                {activeSession?.brief?.template_image_url && (
                  <div className="mb-3">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-medium text-purple-600 flex items-center gap-1">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        文案模板预览
                        {loadingTemplatePreview && (
                          <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                        )}
                      </h4>
                      <button
                        onClick={fetchTemplatePreview}
                        disabled={loadingTemplatePreview || !currentPlanData}
                        className="px-2 py-1 bg-purple-500 hover:bg-purple-600 text-white text-xs font-medium rounded transition-colors disabled:opacity-50 flex items-center gap-1"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        重新生成
                      </button>
                    </div>
                    {templatePreviewImageUrl ? (
                      <img src={templatePreviewImageUrl} alt="模板预览" className="w-full rounded-lg border border-slate-200" />
                    ) : (
                      <div className="w-full h-32 bg-slate-100 rounded-lg flex items-center justify-center">
                        <span className="text-slate-400 text-xs">{currentPlanData ? '点击生成预览' : '等待方案生成...'}</span>
                      </div>
                    )}
                    {templatePreviewSections.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <p className="text-xs font-medium text-slate-500">文案内容</p>
                        {templatePreviewTitle && (
                          <div className="flex items-center gap-1 text-xs">
                            <span className="px-1.5 py-0.5 bg-rose-100 text-rose-600 rounded text-[10px]">标题</span>
                            <span className="text-slate-600 truncate flex-1">{templatePreviewTitle}</span>
                          </div>
                        )}
                        {templatePreviewSections.slice(0, 3).map((section, idx) => (
                          <div key={section.section_id || idx} className="flex items-center gap-1 text-xs">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                              section.section_type === 'headline' ? 'bg-amber-100 text-amber-600' :
                              section.section_type === 'hashtag' ? 'bg-emerald-100 text-emerald-600' :
                              'bg-blue-100 text-blue-600'
                            }`}>
                              {section.section_type === 'title' ? '标题' :
                               section.section_type === 'headline' ? '小标题' :
                               section.section_type === 'text' ? '正文' :
                               section.section_type === 'hashtag' ? '标签' :
                               section.section_type}
                            </span>
                            <span className="text-slate-500 truncate flex-1">{section.content?.slice(0, 20)}...</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {currentPlanData ? (
                  <div className="bg-slate-50 rounded-lg p-3 space-y-2">
                    <p className="text-sm font-medium text-slate-800">{currentPlanData.title}</p>

                    {/* 文本模块 */}
                    {currentPlanData.text_sections && currentPlanData.text_sections.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-slate-600 mb-1">文本模块 ({currentPlanData.text_sections.length})</p>
                        <div className="space-y-1">
                          {currentPlanData.text_sections.map((section, idx) => (
                            <div key={section.section_id || idx} className="flex items-center gap-2 text-xs text-slate-500">
                              <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-600 rounded text-[10px]">
                                {section.section_type === 'headline' ? '标题' :
                                 section.section_type === 'text' ? '正文' :
                                 section.section_type === 'hashtag' ? '标签' :
                                 section.section_type === 'cta' ? '行动' : section.section_type}
                              </span>
                              <span className="flex-1 truncate">
                                {section.content ? section.content.slice(0, 30) + (section.content.length > 30 ? '...' : '') : `约${section.content_words}字`}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 图片计划 */}
                    {currentPlanData.image_plan && (
                      <div className="mt-2 pt-2 border-t border-slate-200">
                        <p className="text-xs font-medium text-slate-600 mb-1">图片计划 ({currentPlanData.image_plan.count}张)</p>
                        <p className="text-xs text-slate-400 line-clamp-2">
                          {currentPlanData.image_plan.style}
                        </p>
                        {currentPlanData.image_plan.elements && currentPlanData.image_plan.elements.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {currentPlanData.image_plan.elements.slice(0, 2).map((el, idx) => (
                              <span key={idx} className="text-[10px] px-1.5 py-0.5 bg-slate-200 text-slate-600 rounded">
                                {el.length > 15 ? el.slice(0, 15) + '...' : el}
                              </span>
                            ))}
                            {currentPlanData.image_plan.elements.length > 2 && (
                              <span className="text-[10px] text-slate-400">+{currentPlanData.image_plan.elements.length - 2}</span>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 视频计划 */}
                    {currentPlanData.video_plan && (
                      <div className="mt-2 pt-2 border-t border-slate-200">
                        <p className="text-xs font-medium text-slate-600 mb-1">视频计划 ({currentPlanData.video_plan.duration}s)</p>
                        <p className="text-xs text-slate-400 line-clamp-2">
                          {currentPlanData.video_plan.voiceover || currentPlanData.video_plan.style || '已生成视频脚本'}
                        </p>
                        {currentPlanData.video_plan.scenes && currentPlanData.video_plan.scenes.length > 0 && (
                          <p className="text-[10px] text-slate-400 mt-1">
                            {currentPlanData.video_plan.scenes.length} 个场景
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 bg-slate-50 rounded-lg p-3 text-center">
                    {activeSession ? '方案生成中...' : '在右侧输入需求生成方案'}
                  </p>
                )}
              </div>
            </div>

            {/* Active Session Content Preview */}
            {activeSession && activeSession.items && activeSession.items.length > 0 && (
              <div className="border-b border-slate-100">
                <div className="p-4">
                  <h3 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
                    <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    内容预览
                  </h3>
                  <p className="text-xs text-slate-500">
                    {activeSession.items.length} 项内容
                  </p>
                </div>
              </div>
            )}

            {/* Version History (collapsible) */}
            {activeSession && activeSession.versions && activeSession.versions.length > 0 && (
              <div className="flex-1 overflow-y-auto">
                <div className="p-4">
                  <VersionHistory
                    session={activeSession}
                    onRollback={handleRestoreVersion}
                    onRestoreVersion={handleRestoreVersion}
                    onRollbackVersionSelect={(index) => {
                      setSelectedRollbackIndex(index);
                    }}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Right Side - Chat Window */}
      <div className="flex-1 flex flex-col">
        {/* Simplified Header */}
        <header className="bg-white border-b border-slate-100 px-6 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {activeSession && (
                <>
                  <h2 className="text-sm font-medium text-slate-700">
                    {activeSession.brief?.raw_input?.slice(0, 40) || '新会话'}
                  </h2>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusLabels[activeSession.status]?.color || 'bg-slate-100 text-slate-700'}`}>
                    {statusLabels[activeSession.status]?.text || activeSession.status}
                  </span>
                </>
              )}
              {!activeSession && (
                <h2 className="text-sm font-medium text-slate-700">新会话</h2>
              )}
            </div>
            {activeSession && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleGenerate}
                  disabled={loading || activeSession.status === 'generating'}
                  className="px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  生成
                </button>
                <button
                  onClick={handleReview}
                  disabled={loading}
                  className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors border border-slate-200 flex items-center gap-1.5"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  审核
                </button>
                <button
                  onClick={handlePublish}
                  disabled={loading}
                  className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  发布
                </button>
              </div>
            )}
          </div>
        </header>

        {/* Toast Messages */}
        {toast && (
          <div className={`mx-6 mt-4 px-4 py-3 rounded-lg text-sm flex items-center gap-2 ${
            toast.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
            toast.type === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
            'bg-blue-50 text-blue-700 border border-blue-200'
          }`}>
            {toast.type === 'success' && (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
            )}
            {toast.type === 'error' && (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
            {toast.text}
          </div>
        )}

        {/* Main Content */}
        {activeSession ? (
          activeSession.status === 'generating' ? (
            <div className="flex-1 p-6">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full">
                <GenerationProgress
                  sessionId={activeSession.session_id}
                  onComplete={handleGenerationComplete}
                  onTokenStream={handleTokenStream}
                />
                {Object.keys(streamingContent).length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                    <div className="px-4 py-3 bg-gradient-to-r from-indigo-500 to-purple-600">
                      <h3 className="text-sm font-semibold text-white">实时预览</h3>
                    </div>
                    <div className="p-4">
                      {Object.entries(streamingContent).map(([itemId, content]) => (
                        <div key={itemId} className="mb-4">
                          <p className="text-xs font-medium text-slate-500 mb-1">{itemId}</p>
                          <div className="bg-slate-900 rounded-lg p-3">
                            <p className="text-sm text-slate-100 font-mono whitespace-pre-wrap">
                              {content}
                              <span className="inline-block w-2 h-4 bg-indigo-400 animate-pulse ml-1" />
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : activeSession.items && activeSession.items.length > 0 ? (
            <div className="flex-1 overflow-hidden">
              <ContentPreview
                session={activeSession}
                onSessionUpdate={(updated) => setActiveSession(updated)}
              />
            </div>
          ) : (
            <div className="flex-1">
              <ChatPanel
                messages={chatMessages}
                isTyping={isTyping}
                onSendMessage={handleSendMessage}
                onPlanDataUpdate={handlePlanDataUpdate}
                materials={sessionMaterials}
                setMaterials={setSessionMaterials}
              />
            </div>
          )
        ) : (
          /* No active session - show welcome/chat panel */
          <div className="flex-1 flex flex-col">
            <div className="flex-1">
              <ChatPanel
                messages={chatMessages}
                isTyping={isTyping}
                onSendMessage={handleSendMessage}
                onPlanDataUpdate={handlePlanDataUpdate}
                materials={sessionMaterials}
                setMaterials={setSessionMaterials}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StudioPage;
