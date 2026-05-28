import { useState, useEffect, useCallback } from 'react';
import {
  listLogFiles,
  getLogEntries,
  LogFileInfo,
  LogEntry,
  LogEntriesResponse,
  formatFileSize,
} from '../api/logApi';

const LOG_TYPES = ['api_request', 'api_response', 'tool_call'];

export default function LogViewerPage() {
  const [logFiles, setLogFiles] = useState<LogFileInfo[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [sessionIdFilter, setSessionIdFilter] = useState('');
  const [keywordFilter, setKeywordFilter] = useState('');

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // Expanded entry
  const [expandedEntry, setExpandedEntry] = useState<number | null>(null);

  // Load log files on mount
  useEffect(() => {
    loadLogFiles();
  }, []);

  // Load entries when file or filters change
  useEffect(() => {
    if (selectedFile) {
      loadEntries();
    }
  }, [selectedFile, page, selectedTypes, sessionIdFilter, keywordFilter]);

  const loadLogFiles = async () => {
    try {
      setLoading(true);
      const response = await listLogFiles();
      setLogFiles(response.files);
      if (response.files.length > 0 && !selectedFile) {
        setSelectedFile(response.files[0].filename);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load log files');
    } finally {
      setLoading(false);
    }
  };

  const loadEntries = async () => {
    try {
      setLoading(true);
      setError(null);
      const filters = {
        type: selectedTypes.length === 1 ? selectedTypes[0] : undefined,
        session_id: sessionIdFilter || undefined,
        keyword: keywordFilter || undefined,
        page,
        page_size: pageSize,
      };

      const response: LogEntriesResponse = await getLogEntries(selectedFile, filters);
      setEntries(response.entries);
      setTotalPages(response.total_pages);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load log entries');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  const handleTypeToggle = (type: string) => {
    setSelectedTypes((prev) => {
      if (prev.includes(type)) {
        return prev.filter((t) => t !== type);
      }
      if (prev.length === 1) {
        return [type];
      }
      return [...prev, type];
    });
    setPage(1);
  };

  const handleResetFilters = () => {
    setSelectedTypes([]);
    setSessionIdFilter('');
    setKeywordFilter('');
    setPage(1);
  };

  const getEntrySummary = (entry: LogEntry): string => {
    switch (entry.type) {
      case 'api_request':
        return `Messages: ${entry.message_count || 0}, Tools: ${entry.tool_count || 0}`;
      case 'api_response':
        return entry.success ? `Success (${entry.latency_ms?.toFixed(0)}ms)` : `Error: ${entry.error}`;
      case 'tool_call':
        return `${entry.tool_name} - ${entry.success ? 'Success' : 'Failed'}`;
      default:
        return JSON.stringify(entry).slice(0, 100);
    }
  };

  const renderEntryContent = (entry: LogEntry) => {
    return (
      <div className="mt-4 p-4 bg-gray-900 rounded-lg overflow-auto max-h-96">
        <pre className="text-sm text-green-400 whitespace-pre-wrap break-all">
          {JSON.stringify(entry, null, 2)}
        </pre>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-white mb-2">日志查看器</h1>
          <p className="text-gray-400">查看和管理系统日志</p>
        </div>

        {/* File Selector */}
        <div className="mb-6 bg-gray-900 rounded-lg p-4">
          <div className="flex items-center gap-4">
            <label className="text-gray-300 font-medium">日志文件:</label>
            <select
              value={selectedFile}
              onChange={(e) => {
                setSelectedFile(e.target.value);
                setPage(1);
                setExpandedEntry(null);
              }}
              className="bg-gray-800 text-white px-4 py-2 rounded border border-gray-700 focus:border-blue-500 focus:outline-none min-w-64"
            >
              {logFiles.map((file) => (
                <option key={file.filename} value={file.filename}>
                  {file.name} ({formatFileSize(file.size)}, {file.entry_count} 条)
                </option>
              ))}
            </select>
            <button
              onClick={loadLogFiles}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors"
            >
              刷新
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="mb-6 bg-gray-900 rounded-lg p-4">
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <span className="text-gray-300 font-medium">类型过滤:</span>
            {LOG_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedTypes.includes(type)}
                  onChange={() => handleTypeToggle(type)}
                  className="w-4 h-4 accent-blue-500"
                />
                <span className="text-gray-300">{type}</span>
              </label>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4 mb-4">
            <label className="flex items-center gap-2">
              <span className="text-gray-300">Session ID:</span>
              <input
                type="text"
                value={sessionIdFilter}
                onChange={(e) => {
                  setSessionIdFilter(e.target.value);
                  setPage(1);
                }}
                placeholder="输入 Session ID"
                className="bg-gray-800 text-white px-3 py-1.5 rounded border border-gray-700 focus:border-blue-500 focus:outline-none w-64"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-4 mb-4">
            <label className="flex items-center gap-2">
              <span className="text-gray-300">关键词搜索:</span>
              <input
                type="text"
                value={keywordFilter}
                onChange={(e) => {
                  setKeywordFilter(e.target.value);
                  setPage(1);
                }}
                placeholder="输入关键词"
                className="bg-gray-800 text-white px-3 py-1.5 rounded border border-gray-700 focus:border-blue-500 focus:outline-none w-64"
              />
            </label>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => {
                setPage(1);
                loadEntries();
              }}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors"
            >
              应用过滤
            </button>
            <button
              onClick={handleResetFilters}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors"
            >
              重置
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-300">
            {error}
          </div>
        )}

        {/* Results Summary */}
        <div className="mb-4 text-gray-400">
          共 {total} 条记录，第 {page}/{totalPages} 页
        </div>

        {/* Log Entries Table */}
        <div className="bg-gray-900 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-300 font-medium">#</th>
                  <th className="px-4 py-3 text-left text-gray-300 font-medium">时间戳</th>
                  <th className="px-4 py-3 text-left text-gray-300 font-medium">类型</th>
                  <th className="px-4 py-3 text-left text-gray-300 font-medium">Session ID</th>
                  <th className="px-4 py-3 text-left text-gray-300 font-medium">摘要</th>
                  <th className="px-4 py-3 text-left text-gray-300 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      加载中...
                    </td>
                  </tr>
                ) : entries.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      暂无日志记录
                    </td>
                  </tr>
                ) : (
                  entries.map((entry, index) => (
                    <>
                      <tr
                        key={`${entry.timestamp}-${index}`}
                        className="hover:bg-gray-800/50 transition-colors"
                      >
                        <td className="px-4 py-3 text-gray-500 text-sm">
                          {entry._line_number || (page - 1) * pageSize + index + 1}
                        </td>
                        <td className="px-4 py-3 text-gray-300 text-sm font-mono">
                          {entry.timestamp}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`px-2 py-1 rounded text-xs font-medium ${
                              entry.type === 'api_request'
                                ? 'bg-blue-900 text-blue-300'
                                : entry.type === 'api_response'
                                ? 'bg-green-900 text-green-300'
                                : 'bg-yellow-900 text-yellow-300'
                            }`}
                          >
                            {entry.type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-400 text-sm font-mono truncate max-w-32">
                          {entry.session_id || '-'}
                        </td>
                        <td className="px-4 py-3 text-gray-400 text-sm">
                          {getEntrySummary(entry)}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() =>
                              setExpandedEntry(expandedEntry === index ? null : index)
                            }
                            className="text-blue-400 hover:text-blue-300 text-sm"
                          >
                            {expandedEntry === index ? '收起' : '展开'}
                          </button>
                        </td>
                      </tr>
                      {expandedEntry === index && (
                        <tr key={`expanded-${index}`}>
                          <td colSpan={6} className="px-4 py-2 bg-gray-950">
                            {renderEntryContent(entry)}
                          </td>
                        </tr>
                      )}
                    </>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-center gap-2">
            <button
              onClick={() => setPage(1)}
              disabled={page === 1}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              首页
            </button>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              上一页
            </button>
            <span className="px-4 py-1.5 text-gray-300">
              第 {page} / {totalPages} 页
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              下一页
            </button>
            <button
              onClick={() => setPage(totalPages)}
              disabled={page === totalPages}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              末页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
