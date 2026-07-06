"""Sentinel-2 night imagery schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ImageryProductType(str, Enum):
    ORTHORECTIFIED = "orthorectified"
    SENSOR_GEOMETRY = "sensor_geometry"
    L1B_RAW = "l1b_raw"


class ProcessingStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class NightSceneSummary(BaseModel):
    """Summary of a Sentinel-2 night acquisition scene."""

    scene_id: str
    datetime: datetime
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    platform: str = "sentinel-2a"
    mode: Optional[str] = None
    scenario: Optional[str] = None
    stac_url: Optional[str] = None
    s3_prefix: Optional[str] = None
    product_types: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class ProcessingStep(BaseModel):
    """One step in the ESA L1B → orthorectified radiance pipeline."""

    step: int
    name: str
    tool: str
    description: str
    status: ProcessingStepStatus = ProcessingStepStatus.NOT_CONFIGURED
    reference: Optional[str] = None


class ImagerySearchParams(BaseModel):
    bbox: Optional[str] = Field(None, description="minLon,minLat,maxLon,maxLat")
    datetime_from: Optional[datetime] = None
    datetime_to: Optional[datetime] = None
    limit: int = Field(20, ge=1, le=100)
