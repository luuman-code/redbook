import React, { useMemo } from 'react';

interface DiffViewerProps {
  original: string;
  modified: string;
  title?: string;
}

interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  content: string;
  lineNumber?: number;
}

const DiffViewer: React.FC<DiffViewerProps> = ({ original, modified, title = '内容对比' }) => {
  // Compute diff between original and modified
  const diffLines = useMemo(() => {
    const originalLines = original.split('\n');
    const modifiedLines = modified.split('\n');
    const result: DiffLine[] = [];

    // Simple line-by-line diff algorithm
    const maxLines = Math.max(originalLines.length, modifiedLines.length);

    for (let i = 0; i < maxLines; i++) {
      const origLine = originalLines[i];
      const modLine = modifiedLines[i];

      if (origLine === undefined) {
        // Line added in modified
        result.push({ type: 'added', content: modLine, lineNumber: i + 1 });
      } else if (modLine === undefined) {
        // Line removed from original
        result.push({ type: 'removed', content: origLine, lineNumber: i + 1 });
      } else if (origLine !== modLine) {
        // Line changed
        result.push({ type: 'removed', content: origLine, lineNumber: i + 1 });
        result.push({ type: 'added', content: modLine, lineNumber: i + 1 });
      } else {
        // Line unchanged
        result.push({ type: 'unchanged', content: origLine, lineNumber: i + 1 });
      }
    }

    return result;
  }, [original, modified]);

  // Calculate stats
  const stats = useMemo(() => {
    const added = diffLines.filter(l => l.type === 'added').length;
    const removed = diffLines.filter(l => l.type === 'removed').length;
    return { added, removed };
  }, [diffLines]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1 text-emerald-600">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
              +{stats.added}
            </span>
            <span className="flex items-center gap-1 text-red-600">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 12H4" />
              </svg>
              -{stats.removed}
            </span>
          </div>
        </div>
        <button
          onClick={() => {
            // Copy modified content to clipboard
            navigator.clipboard.writeText(modified);
          }}
          className="px-3 py-1 text-xs text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors flex items-center gap-1"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
          </svg>
          复制修改后内容
        </button>
      </div>

      {/* Diff Content */}
      <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
        <table className="w-full text-sm font-mono">
          <tbody>
            {diffLines.map((line, index) => (
              <tr
                key={index}
                className={`${
                  line.type === 'added'
                    ? 'bg-emerald-50'
                    : line.type === 'removed'
                    ? 'bg-red-50'
                    : 'bg-white'
                }`}
              >
                {/* Line number */}
                <td className="w-12 px-2 py-0.5 text-right text-xs text-slate-400 border-r border-slate-100 select-none">
                  {line.lineNumber}
                </td>
                {/* Change indicator */}
                <td className="w-6 px-1 py-0.5 text-center select-none">
                  {line.type === 'added' && (
                    <span className="text-emerald-500 font-bold">+</span>
                  )}
                  {line.type === 'removed' && (
                    <span className="text-red-500 font-bold">-</span>
                  )}
                </td>
                {/* Content */}
                <td className="px-2 py-0.5 whitespace-pre-wrap break-all text-slate-700">
                  {line.type === 'removed' ? (
                    <span className="line-through text-red-600">{line.content}</span>
                  ) : (
                    line.content
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Empty state */}
      {diffLines.length === 0 && (
        <div className="p-8 text-center text-slate-500 text-sm">
          无内容差异
        </div>
      )}
    </div>
  );
};

export default DiffViewer;