import React from 'react';

interface TypingIndicatorProps {
  visible: boolean;
}

const TypingIndicator: React.FC<TypingIndicatorProps> = ({ visible }) => {
  if (!visible) return null;

  return (
    <div className="flex items-center gap-1.5 px-4 py-3 bg-slate-100 rounded-2xl rounded-tl-sm max-w-fit">
      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
    </div>
  );
};

export default TypingIndicator;