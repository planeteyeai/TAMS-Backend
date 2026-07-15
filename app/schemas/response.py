"""
API Response schemas
"""

from pydantic import BaseModel, Field
from typing import Any, Optional, List
from datetime import datetime


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=20000)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class ResponseMeta(BaseModel):
    """Response metadata"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0"
    request_id: Optional[str] = None
    pagination: Optional[PaginationMeta] = None


class ApiResponse(BaseModel):
    """Standard API response wrapper"""
    data: Any
    meta: ResponseMeta
    errors: Optional[List[str]] = None


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
    status_code: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
