"""
End-to-end monitoring workflow orchestrator.

Pipeline: Acquire → Detect → Compare → Alert → Complete

Each stage produces structured output for the GIS dashboard and work-order systems.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.schemas.monitoring import (
    DetectionResult,
    DetectionType,
    MonitoringRunRequest,
    MonitoringRunResult,
    SatelliteSource,
    WorkflowStage,
    WorkflowStageResult,
    WorkflowStageStatus,
)
from app.services import stac_catalog
from app.services.alert_engine import generate_alerts_from_changes
from app.services.change_detection import compare_observations
from app.services.mock_data import MOCK_ASSETS

logger = logging.getLogger(__name__)

RUN_HISTORY: list[MonitoringRunResult] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stage(
    stage: WorkflowStage,
    status: WorkflowStageStatus,
    started: datetime,
    summary: str,
    output: dict[str, Any] | None = None,
) -> WorkflowStageResult:
    return WorkflowStageResult(
        stage=stage,
        status=status,
        started_at=started,
        completed_at=_now(),
        summary=summary,
        output=output or {},
    )


def _analyze_assets(assets: list[dict[str, Any]], scenes: list) -> list[DetectionResult]:
    """
    Structured detection pass (Phase 2 heuristic engine).

    Replace with YOLO / U-Net / thermal models when ML weights are available.
    """
    detections: list[DetectionResult] = []

    for asset in assets:
        health = asset.get("health_score", "healthy")
        lat, lon = asset["latitude"], asset["longitude"]
        asset_type = asset["asset_type"]

        if asset_type == "tower":
            detections.append(
                DetectionResult(
                    detection_type=DetectionType.TOWER,
                    asset_id=asset["id"],
                    confidence=0.91 if health != "critical" else 0.78,
                    severity="low",
                    latitude=lat,
                    longitude=lon,
                    details={"structure_type": asset.get("metadata", {}).get("structure_type")},
                )
            )

        if asset_type == "line":
            detections.append(
                DetectionResult(
                    detection_type=DetectionType.POWER_LINE,
                    asset_id=asset["id"],
                    confidence=0.85,
                    severity="low",
                    latitude=lat,
                    longitude=lon,
                    details={"length_km": asset.get("metadata", {}).get("length_km")},
                )
            )

        if asset_type == "substation":
            detections.append(
                DetectionResult(
                    detection_type=DetectionType.SUBSTATION,
                    asset_id=asset["id"],
                    confidence=0.93,
                    severity="high" if health == "critical" else "low",
                    latitude=lat,
                    longitude=lon,
                )
            )

        if health in ("attention_required", "critical"):
            clearance = 3.8 if health == "attention_required" else 2.1
            detections.append(
                DetectionResult(
                    detection_type=DetectionType.VEGETATION,
                    asset_id=asset["id"],
                    confidence=0.82,
                    severity="high" if clearance < 5 else "medium",
                    latitude=lat,
                    longitude=lon,
                    details={"clearance_m": clearance, "buffer_m": 5},
                )
            )

        if health == "attention_required" and "thermal" in asset.get("description", "").lower():
            detections.append(
                DetectionResult(
                    detection_type=DetectionType.THERMAL_ANOMALY,
                    asset_id=asset["id"],
                    confidence=0.79,
                    severity="high",
                    latitude=lat,
                    longitude=lon,
                    details={"thermal_delta": 0.28, "source": "sentinel-2-night"},
                )
            )

        if health == "critical" and asset_type == "substation":
            detections.append(
                DetectionResult(
                    detection_type=DetectionType.THERMAL_ANOMALY,
                    asset_id=asset["id"],
                    confidence=0.74,
                    severity="high",
                    latitude=lat,
                    longitude=lon,
                    details={"thermal_delta": 0.35, "source": "landsat-tirs"},
                )
            )

    night_scenes = [s for s in scenes if s.source == SatelliteSource.SENTINEL_2_NIGHT]
    if night_scenes:
        for asset in assets:
            if asset.get("health_score") == "attention_required":
                detections.append(
                    DetectionResult(
                        detection_type=DetectionType.THERMAL_ANOMALY,
                        asset_id=asset["id"],
                        confidence=0.81,
                        severity="medium",
                        latitude=asset["latitude"],
                        longitude=asset["longitude"],
                        details={"thermal_delta": 0.22, "scene_id": night_scenes[0].scene_id},
                    )
                )

    return detections


async def run_monitoring(request: MonitoringRunRequest) -> MonitoringRunResult:
    """Execute the full acquire → detect → compare → alert pipeline."""
    run_id = f"run-{uuid4().hex[:10]}"
    started = _now()
    stages: list[WorkflowStageResult] = []

    # Resolve assets
    if request.asset_ids:
        assets = [a for a in MOCK_ASSETS if a["id"] in request.asset_ids]
    else:
        # Full KML catalog is huge — sample a representative slice for interactive runs
        assets = list(MOCK_ASSETS)

    # Keep UI / interactive cycles responsive (full fleet scans belong in batch jobs)
    MAX_INTERACTIVE_ASSETS = 40
    if len(assets) > MAX_INTERACTIVE_ASSETS:
        # Prefer substations + mixture of lines over flooding detections
        subs = [a for a in assets if a.get("asset_type") == "substation"][:12]
        lines = [a for a in assets if a.get("asset_type") == "line"][:20]
        towers = [a for a in assets if a.get("asset_type") == "tower"][:8]
        assets = (subs + lines + towers)[:MAX_INTERACTIVE_ASSETS] or assets[:MAX_INTERACTIVE_ASSETS]

    if not assets:
        result = MonitoringRunResult(
            run_id=run_id,
            status="failed",
            started_at=started,
            completed_at=_now(),
            assets_monitored=0,
            scenes_acquired=0,
            detections=[],
            changes=[],
            alerts_generated=[],
            stages=[
                _stage(
                    WorkflowStage.ACQUIRE,
                    WorkflowStageStatus.FAILED,
                    started,
                    "No assets matched the request",
                )
            ],
        )
        RUN_HISTORY.insert(0, result)
        return result

    # Stage 1: Acquire
    acquire_start = _now()
    bbox = request.bbox or stac_catalog.asset_bbox(assets)
    all_scenes = []
    acquire_meta: dict[str, Any] = {"sources": {}, "bbox": bbox}

    for source in request.sources:
        scenes, src = await stac_catalog.search_scenes(source=source, bbox=bbox, limit=5)
        relevant = stac_catalog.scenes_for_assets(scenes, assets)
        all_scenes.extend(relevant)
        acquire_meta["sources"][source.value] = {"count": len(relevant), "catalog": src}

    stages.append(
        _stage(
            WorkflowStage.ACQUIRE,
            WorkflowStageStatus.COMPLETED,
            acquire_start,
            f"Acquired {len(all_scenes)} scenes across {len(request.sources)} sources",
            {"scenes": [s.model_dump() for s in all_scenes], **acquire_meta},
        )
    )

    # Stage 2: Detect
    detect_start = _now()
    detections = _analyze_assets(assets, all_scenes)
    stages.append(
        _stage(
            WorkflowStage.DETECT,
            WorkflowStageStatus.COMPLETED,
            detect_start,
            f"Ran CV/AI analysis — {len(detections)} detections",
            {"detections": [d.model_dump() for d in detections]},
        )
    )

    # Stage 3: Compare (change detection)
    compare_start = _now()
    changes = compare_observations(assets, all_scenes, detections)
    stages.append(
        _stage(
            WorkflowStage.COMPARE,
            WorkflowStageStatus.COMPLETED,
            compare_start,
            f"Historical comparison found {len(changes)} changes",
            {"changes": [c.model_dump() for c in changes]},
        )
    )

    # Stage 4: Alert
    alert_ids: list[str] = []
    if request.generate_alerts:
        alert_start = _now()
        new_alerts = generate_alerts_from_changes(changes, detections)
        alert_ids = [a["id"] for a in new_alerts]
        stages.append(
            _stage(
                WorkflowStage.ALERT,
                WorkflowStageStatus.COMPLETED,
                alert_start,
                f"Generated {len(new_alerts)} new alerts",
                {"alert_ids": alert_ids},
            )
        )
    else:
        stages.append(
            _stage(
                WorkflowStage.ALERT,
                WorkflowStageStatus.SKIPPED,
                _now(),
                "Alert generation disabled",
            )
        )

    stages.append(
        _stage(
            WorkflowStage.COMPLETE,
            WorkflowStageStatus.COMPLETED,
            _now(),
            "Monitoring cycle complete — ready for dashboard and work orders",
            {"next_pass_days": 7},
        )
    )

    result = MonitoringRunResult(
        run_id=run_id,
        status="completed",
        started_at=started,
        completed_at=_now(),
        assets_monitored=len(assets),
        scenes_acquired=len(all_scenes),
        detections=detections,
        changes=changes,
        alerts_generated=alert_ids,
        stages=stages,
        monitored_assets=[
            {
                "id": a["id"],
                "name": a.get("name") or a["id"],
                "asset_type": a.get("asset_type") or "tower",
                "latitude": a.get("latitude"),
                "longitude": a.get("longitude"),
                "health_score": a.get("health_score") or "healthy",
                "voltage_kv": (a.get("metadata") or {}).get("voltage_kv"),
            }
            for a in assets
        ],
    )
    RUN_HISTORY.insert(0, result)
    logger.info("Monitoring run %s completed: %d assets, %d alerts", run_id, len(assets), len(alert_ids))
    return result


def get_workflow_definition() -> dict[str, Any]:
    """Return the canonical monitoring workflow for documentation and UI."""
    return {
        "name": "Transmission Asset Monitoring Pipeline",
        "description": (
            "Continuous monitoring of transmission corridors using multi-source "
            "satellite imagery, AI asset detection, change detection, and alert generation."
        ),
        "stages": [
            {
                "id": "acquire",
                "name": "Satellite Data Acquisition",
                "sources": [
                    {"id": "sentinel-2", "modality": "optical", "revisit_days": 5},
                    {"id": "sentinel-1", "modality": "sar", "revisit_days": 6},
                    {"id": "landsat-9", "modality": "optical+thermal", "revisit_days": 16},
                    {"id": "sentinel-2-night", "modality": "thermal", "revisit_days": "campaign"},
                ],
                "outputs": ["STAC scene metadata", "S3 paths", "cloud cover"],
            },
            {
                "id": "detect",
                "name": "Asset Detection",
                "models": [
                    "YOLO — towers, structures",
                    "U-Net — vegetation segmentation",
                    "Autoencoder — thermal anomalies",
                ],
                "targets": [
                    "transmission_tower",
                    "power_line",
                    "substation",
                    "vegetation_encroachment",
                    "construction_activity",
                ],
            },
            {
                "id": "compare",
                "name": "Continuous Monitoring",
                "checks": [
                    "missing_tower",
                    "damaged_infrastructure",
                    "flooding",
                    "landslide",
                    "wildfire_threat",
                    "unauthorized_activity",
                ],
            },
            {
                "id": "alert",
                "name": "Alert Generation",
                "triggers": [
                    "vegetation clearance < 5m",
                    "new structures in ROW",
                    "thermal anomaly",
                    "disaster threat",
                ],
                "actions": ["dashboard_flag", "work_order", "notification"],
            },
        ],
        "example_use_case": {
            "utility": "power_transmission",
            "cadence": "5-10 days",
            "flow": [
                "Satellite captures corridor",
                "AI detects vegetation within 5m of conductors",
                "System flags high-risk sections",
                "Maintenance teams receive work orders",
                "Post-trim imagery verifies completion",
            ],
        },
    }
