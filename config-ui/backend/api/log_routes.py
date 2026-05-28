"""Log viewing API routes"""
import os
import json
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/logs", tags=["logs"])

# Log directory path
# __file__ = config-ui/backend/api/log_routes.py
# Need to go up 4 levels: api -> backend -> config-ui -> redbook -> data/logs
LOGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data", "logs"
)


class LogEntry(BaseModel):
    """Single log entry"""
    timestamp: str
    type: str
    session_id: Optional[str] = None
    content: dict


class LogFileInfo(BaseModel):
    """Log file information"""
    name: str
    filename: str
    size: int
    modified_time: str
    entry_count: int


class LogListResponse(BaseModel):
    """Response for log list"""
    files: List[LogFileInfo]


class LogEntriesResponse(BaseModel):
    """Response for log entries"""
    entries: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


def parse_log_file(filepath: str) -> List[dict]:
    """Parse a JSON lines log file"""
    entries = []
    if not os.path.exists(filepath):
        return entries

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry['_line_number'] = line_num
                    entries.append(entry)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")

    return entries


def get_available_log_files() -> List[LogFileInfo]:
    """Get list of available log files"""
    files = []
    if not os.path.exists(LOGS_DIR):
        return files

    for filename in os.listdir(LOGS_DIR):
        if filename.endswith('.log'):
            filepath = os.path.join(LOGS_DIR, filename)
            stat = os.stat(filepath)
            modified_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            # Count entries
            entry_count = 0
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    entry_count = sum(1 for line in f if line.strip())
            except:
                pass

            files.append(LogFileInfo(
                name=filename.replace('.log', ''),
                filename=filename,
                size=stat.st_size,
                modified_time=modified_time,
                entry_count=entry_count
            ))

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x.modified_time, reverse=True)
    return files


@router.get("", response_model=LogListResponse)
async def list_log_files():
    """Get list of available log files"""
    files = get_available_log_files()
    return LogListResponse(files=files)


@router.get("/{filename}", response_model=LogEntriesResponse)
async def get_log_entries(
    filename: str,
    type: Optional[str] = Query(None, description="Filter by log type (api_request, api_response, tool_call)"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    keyword: Optional[str] = Query(None, description="Search keyword in log content"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get log entries from a specific log file with filtering"""
    # Validate filename
    if not filename.endswith('.log'):
        filename = filename + '.log'

    filepath = os.path.join(LOGS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Log file not found: {filename}")

    # Parse log file
    entries = parse_log_file(filepath)

    # Apply filters
    filtered_entries = []
    for entry in entries:
        # Type filter
        if type and entry.get('type') != type:
            continue

        # Session ID filter
        if session_id and entry.get('session_id') != session_id:
            continue

        # Keyword filter - search in all values recursively
        if keyword:
            keyword_lower = keyword.lower()
            found = False
            def search_in_dict(d, search_term):
                if isinstance(d, dict):
                    for v in d.values():
                        if search_in_dict(v, search_term):
                            return True
                elif isinstance(d, list):
                    return any(search_in_dict(item, search_term) for item in d)
                elif isinstance(d, str) and search_term in d.lower():
                    return True
                return False

            if search_in_dict(entry, keyword_lower):
                found = True

            if not found:
                continue

        filtered_entries.append(entry)

    # Sort by timestamp (newest first)
    filtered_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    # Calculate pagination
    total = len(filtered_entries)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_entries = filtered_entries[start_idx:end_idx]

    return LogEntriesResponse(
        entries=paginated_entries,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{filename}/entry/{line_number}")
async def get_log_entry(filename: str, line_number: int):
    """Get a specific log entry by line number"""
    if not filename.endswith('.log'):
        filename = filename + '.log'

    filepath = os.path.join(LOGS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Log file not found: {filename}")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for current_line, line in enumerate(f, 1):
                if current_line == line_number:
                    line = line.strip()
                    if not line:
                        raise HTTPException(status_code=404, detail="Empty line")
                    try:
                        entry = json.loads(line)
                        return entry
                    except json.JSONDecodeError:
                        raise HTTPException(status_code=404, detail="Invalid JSON")

        raise HTTPException(status_code=404, detail="Line number out of range")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
