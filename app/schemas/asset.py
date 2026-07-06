"""
Asset schemas for request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class AssetTypeEnum(str, Enum):
    """Asset types"""
    TOWER = "tower"
    LINE = "line"
    SUBSTATION = "substation"


class AssetStatusEnum(str, Enum):
    """Asset status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class HealthScoreEnum(str, Enum):
    """Health score categories"""
    HEALTHY = "healthy"
    ATTENTION_REQUIRED = "attention_required"
    CRITICAL = "critical"


class AssetCreate(BaseModel):
    """Asset creation schema"""
    name: str = Field(..., min_length=1, max_length=255)
    asset_type: AssetTypeEnum
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    status: AssetStatusEnum = AssetStatusEnum.ACTIVE
    description: Optional[str] = None
    metadata: Optional[dict] = Field(default_factory=dict)


class AssetUpdate(BaseModel):
    """Asset update schema"""
    name: Optional[str] = None
    status: Optional[AssetStatusEnum] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None


class AssetResponse(AssetCreate):
    """Asset response schema"""
    id: str
    health_score: Optional[HealthScoreEnum] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
