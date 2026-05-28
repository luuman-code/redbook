const API_BASE = '/api/logs';

export interface LogFileInfo {
  name: string;
  filename: string;
  size: number;
  modified_time: string;
  entry_count: number;
}

export interface LogListResponse {
  files: LogFileInfo[];
}

export interface LogEntry {
  _line_number?: number;
  timestamp: string;
  type: string;
  session_id?: string;
  [key: string]: unknown;
}

export interface LogEntriesResponse {
  entries: LogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface LogFilterParams {
  type?: string;
  session_id?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

export async function listLogFiles(): Promise<LogListResponse> {
  const response = await fetch(API_BASE);
  if (!response.ok) {
    throw new Error(`Failed to list log files: ${response.statusText}`);
  }
  return response.json();
}

export async function getLogEntries(
  filename: string,
  filters?: LogFilterParams
): Promise<LogEntriesResponse> {
  const params = new URLSearchParams();
  if (filters?.type) params.set('type', filters.type);
  if (filters?.session_id) params.set('session_id', filters.session_id);
  if (filters?.keyword) params.set('keyword', filters.keyword);
  if (filters?.page) params.set('page', String(filters.page));
  if (filters?.page_size) params.set('page_size', String(filters.page_size));

  const queryString = params.toString();
  const url = `${API_BASE}/${filename}${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to get log entries: ${response.statusText}`);
  }
  return response.json();
}

export async function getLogEntry(filename: string, lineNumber: number): Promise<LogEntry> {
  const response = await fetch(`${API_BASE}/${filename}/entry/${lineNumber}`);
  if (!response.ok) {
    throw new Error(`Failed to get log entry: ${response.statusText}`);
  }
  return response.json();
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}
