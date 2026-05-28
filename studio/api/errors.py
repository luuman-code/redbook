"""Unified error response schemas"""
from pydantic import BaseModel
from typing import Optional

class APIError(BaseModel):
    error: str
    message: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[dict] = None
