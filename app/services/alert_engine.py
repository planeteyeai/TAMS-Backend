"""
Rule-based alert generation from monitoring findings.

Maps change detections and AI outputs to actionable alerts for field crews.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.schemas.monitoring import ChangeFinding, DetectionResult
from app.services.mock_data import MOCK_ALERTS

ALERT_RULES: list[dict[str, Any]] = [
    {
        "change_type": "vegetation_encroachment",
        "alert_type": "vegetation_encroachment",
        "priority_map": {"high": "high", "medium": "medium", "low": "low"},
        "title": "Vegetation within safety clearance",
        "message_template": (
            "Satellite analysis detected vegetation within {clearance_m}m of conductors. "
            "Schedule trimming per ROW maintenance policy."
        ),
    },
    {
        "change_type": "thermal_anomaly",
        "alert_type": "thermal_anomaly",
        "priority_map": {"high": "high", "medium": "medium"},
        "title": "Thermal anomaly detected",
        "message_template": (
            "Night/optical thermal analysis shows elevated signature (delta {thermal_delta:.2f}). "
            "Correlate with SCADA loading data."
        ),
    },
    {
        "change_type": "sar_backscatter_change",
        "alert_type": "flooding",
        "priority_map": {"medium": "medium", "high": "high"},
        "title": "SAR change — possible flooding or ground disturbance",
        "message_template": (
            "Sentinel-1 SAR detected backscatter change ({backscatter_delta_db:.1f} dB). "
            "Inspect for flooding, landslide, or unauthorized ground activity."
        ),
    },
    {
        "change_type": "structural_attention",
        "alert_type": "maintenance_verification",
        "priority_map": {"medium": "medium"},
        "title": "Post-maintenance verification required",
        "message_template": (
            "Asset is in maintenance status. Acquire follow-up imagery within "
            "{maintenance_window_days} days to verify completion."
        ),
    },
    {
        "detection_type": "construction",
        "alert_type": "unauthorized_activity",
        "priority_map": {"high": "high", "medium": "medium"},
        "title": "New structure near transmission corridor",
        "message_template": "Computer vision detected new construction activity within the ROW buffer.",
    },
    {
        "detection_type": "missing_asset",
        "alert_type": "missing_tower",
        "priority_map": {"high": "critical", "medium": "high"},
        "title": "Possible missing or damaged tower",
        "message_template": "Historical comparison suggests tower may be missing or structurally compromised.",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _existing_alert_key(asset_id: str, alert_type: str) -> bool:
    return any(
        a["asset_id"] == asset_id
        and a["alert_type"] == alert_type
        and a["status"] in ("open", "acknowledged")
        for a in MOCK_ALERTS
    )


def generate_alerts_from_changes(
    changes: list[ChangeFinding],
    detections: list[DetectionResult] | None = None,
) -> list[dict[str, Any]]:
    """Create alerts from change findings; skip duplicates for open alerts."""
    created: list[dict[str, Any]] = []
    detections = detections or []

    for change in changes:
        rule = next((r for r in ALERT_RULES if r.get("change_type") == change.change_type), None)
        if not rule:
            continue
        if _existing_alert_key(change.asset_id, rule["alert_type"]):
            continue

        metrics = change.metrics
        message = rule["message_template"].format(**{k: metrics.get(k, 0) for k in metrics})
        priority = rule["priority_map"].get(change.severity, "medium")

        alert = {
            "id": f"alert-{uuid4().hex[:8]}",
            "asset_id": change.asset_id,
            "alert_type": rule["alert_type"],
            "priority": priority,
            "title": rule["title"],
            "message": message,
            "status": "open",
            "created_at": _now(),
            "source": "monitoring_pipeline",
            "confidence": change.confidence,
        }
        MOCK_ALERTS.insert(0, alert)
        created.append(alert)

    for detection in detections:
        rule = next(
            (r for r in ALERT_RULES if r.get("detection_type") == detection.detection_type.value),
            None,
        )
        if not rule or not detection.asset_id:
            continue
        if _existing_alert_key(detection.asset_id, rule["alert_type"]):
            continue
        if detection.confidence < 0.6:
            continue

        priority = rule["priority_map"].get(detection.severity, "medium")
        alert = {
            "id": f"alert-{uuid4().hex[:8]}",
            "asset_id": detection.asset_id,
            "alert_type": rule["alert_type"],
            "priority": priority,
            "title": rule["title"],
            "message": rule["message_template"],
            "status": "open",
            "created_at": _now(),
            "source": "monitoring_pipeline",
            "confidence": detection.confidence,
        }
        MOCK_ALERTS.insert(0, alert)
        created.append(alert)

    return created
