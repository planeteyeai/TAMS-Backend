"""Monitoring workflow and change-detection schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SatelliteSource(str, Enum):
    SENTINEL_1 = "sentinel-1"
    SENTINEL_2 = "sentinel-2"
    LANDSAT_9 = "landsat-9"
    SENTINEL_2_NIGHT = "sentinel-2-night"


class ImageryModality(str, Enum):
    OPTICAL = "optical"
    SAR = "sar"
    THERMAL = "thermal"


class DetectionType(str, Enum):
    TOWER = "tower"
    POWER_LINE = "power_line"
    SUBSTATION = "substation"
    VEGETATION = "vegetation"
    CONSTRUCTION = "construction"
    THERMAL_ANOMALY = "thermal_anomaly"
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    MISSING_ASSET = "missing_asset"


class WorkflowStage(str, Enum):
    ACQUIRE = "acquire"
    DETECT = "detect"
    COMPARE = "compare"
    ALERT = "alert"
    COMPLETE = "complete"


class WorkflowStageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class SceneSummary(BaseModel):
    scene_id: str
    source: SatelliteSource
    modality: ImageryModality
    datetime: datetime
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    cloud_cover: Optional[float] = None
    collection: str
    stac_url: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)


class DetectionResult(BaseModel):
    detection_type: DetectionType
    asset_id: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    severity: str = "low"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    details: dict[str, Any] = Field(default_factory=dict)


class ChangeFinding(BaseModel):
    change_type: str
    asset_id: str
    severity: str
    confidence: float
    baseline_date: Optional[datetime] = None
    current_date: datetime
    description: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class WorkflowStageResult(BaseModel):
    stage: WorkflowStage
    status: WorkflowStageStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    summary: str = ""
    output: dict[str, Any] = Field(default_factory=dict)


class MonitoringRunRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    sources: list[SatelliteSource] = Field(
        default_factory=lambda: [
            SatelliteSource.SENTINEL_2,
            SatelliteSource.SENTINEL_1,
        ]
    )
    bbox: Optional[str] = Field(None, description="minLon,minLat,maxLon,maxLat")
    generate_alerts: bool = True


class MonitoringRunResult(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    assets_monitored: int
    scenes_acquired: int
    detections: list[DetectionResult]
    changes: list[ChangeFinding]
    alerts_generated: list[str]
    stages: list[WorkflowStageResult]
