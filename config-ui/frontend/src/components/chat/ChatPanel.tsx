import React, { useCallback } from 'react';
import MessageList from './MessageList';
import ChatInput, { Material } from './ChatInput';
import { ChatMessage, PlanData } from './ChatBubble';

interface ChatPanelProps {
  messages: ChatMessage[];
  isTyping: boolean;
  onSendMessage: (message: string, materials?: Material[]) => void;
  onStop?: () => void;
  onPlanDataUpdate?: (planData: PlanData) => void;
  materials?: Material[];
  setMaterials?: (materials: Material[]) => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  isTyping,
  onSendMessage,
  onStop,
  onPlanDataUpdate,
  materials,
  setMaterials,
}) => {
  const handleSend = useCallback(
    (message: string, mats?: Material[]) => {
      onSendMessage(message, mats);
    },
    [onSendMessage]
  );

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 bg-white border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-500 rounded-xl flex items-center justify-center">
            <svg
              className="w-5 h-5 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-base font-semibold text-slate-800">AI 内容助手</h3>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              <span className="text-xs text-slate-500">在线</span>
            </div>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <MessageList
        messages={messages}
        isTyping={isTyping}
        onPlanDataUpdate={onPlanDataUpdate}
      />

      {/* Input area */}
      <ChatInput
        onSend={handleSend}
        onStop={onStop}
        disabled={isTyping}
        materials={materials}
        setMaterials={setMaterials}
      />
    </div>
  );
};

export default ChatPanel;