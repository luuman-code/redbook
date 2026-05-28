import React, { useRef, useEffect } from 'react';
import ChatBubble, { ChatMessage } from './ChatBubble';
import TypingIndicator from './TypingIndicator';
import { PlanData } from './ChatBubble';

interface MessageListProps {
  messages: ChatMessage[];
  isTyping: boolean;
  onPlanDataUpdate?: (planData: PlanData) => void;
}

const MessageList: React.FC<MessageListProps> = ({
  messages,
  isTyping,
  onPlanDataUpdate,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  // Notify parent when plan_data is received
  useEffect(() => {
    messages.forEach(msg => {
      if (msg.metadata?.plan_data) {
        onPlanDataUpdate?.(msg.metadata.plan_data);
      }
    });
  }, [messages, onPlanDataUpdate]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-4 py-4"
      style={{ scrollBehavior: 'smooth' }}
    >
      {/* Welcome message for empty state */}
      {messages.length === 0 && !isTyping && (
        <div className="flex flex-col items-center justify-center h-full text-center">
          <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
            <svg
              className="w-8 h-8 text-indigo-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-slate-800 mb-2">开始聊天</h3>
          <p className="text-sm text-slate-500 max-w-xs">
            告诉我你想创作什么类型的内容，我会帮你完成
          </p>
        </div>
      )}

      {/* Messages */}
      {messages.map((message) => (
        <ChatBubble
          key={message.message_id}
          message={message}
        />
      ))}

      {/* Typing indicator */}
      {isTyping && (
        <div className="flex justify-start mb-4">
          <div className="bg-white border border-slate-200 px-4 py-3 rounded-2xl rounded-tl-sm">
            <TypingIndicator visible={true} />
          </div>
        </div>
      )}
    </div>
  );
};

export default MessageList;