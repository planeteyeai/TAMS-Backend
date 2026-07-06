"""
Change detection between current satellite observations and asset baselines.

Phase 2 uses structured heuristics tied to asset health metadata.
Full raster differencing (GDAL/rasterio) plugs in at the compare stage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.monitoring import ChangeFinding, DetectionResult, SceneSummary, SatelliteSource

# In-memory baselines keyed by asset_id
BASELINES: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_baseline(asset: dict[str, Any]) -> dict[str, Any]:
    """Create or return monitoring baseline for an asset."""
    asset_id = asset["id"]
    if asset_id not in BASELINES:
        BASELINES[asset_id] = {
            "asset_id": asset_id,
            "established_at": _now() - timedelta(days=30),
            "tower_present": asset["asset_type"] == "tower",
            "vegetation_clearance_m": 12.0 if asset["health_score"] == "healthy" else 4.5,
            "thermal_baseline": 0.2,
            "sar_backscatter_db": -12.0,
            "last_verified_scene": None,
        }
    return BASELINES[asset_id]


def compare_observations(
    assets: list[dict[str, Any]],
    scenes: list[SceneSummary],
    detections: list[DetectionResult],
) -> list[ChangeFinding]:
    """Compare current detections and scene metadata against stored baselines."""
    findings: list[ChangeFinding] = []
    scene_date = max((s.datetime for s in scenes), default=_now())
    detection_by_asset = {d.asset_id: d for d in detections if d.asset_id}

    for asset in assets:
        baseline = ensure_baseline(asset)
        asset_id = asset["id"]

        veg = next(
            (d for d in detections if d.asset_id == asset_id and d.detection_type.value == "vegetation"),
            detection_by_asset.get(asset_id),
        )
        if veg and veg.details.get("clearance_m", 99) < baseline["vegetation_clearance_m"] - 2:
            findings.append(
                ChangeFinding(
                    change_type="vegetation_encroachment",
                    asset_id=asset_id,
                    severity="high" if veg.details.get("clearance_m", 99) < 5 else "medium",
                    confidence=veg.confidence,
                    baseline_date=baseline["established_at"],
                    current_date=scene_date,
                    description=(
                        f"Vegetation clearance reduced to {veg.details.get('clearance_m', '?')}m "
                        f"(baseline {baseline['vegetation_clearance_m']}m)"
                    ),
                    metrics={
                        "clearance_m": veg.details.get("clearance_m"),
                        "baseline_clearance_m": baseline["vegetation_clearance_m"],
                    },
                )
            )

        thermal = next(
            (d for d in detections if d.asset_id == asset_id and d.detection_type.value == "thermal_anomaly"),
            None,
        )
        if thermal:
            delta = thermal.details.get("thermal_delta", 0)
            if delta > 0.15:
                findings.append(
                    ChangeFinding(
                        change_type="thermal_anomaly",
                        asset_id=asset_id,
                        severity="high" if delta > 0.3 else "medium",
                        confidence=thermal.confidence,
                        baseline_date=baseline["established_at"],
                        current_date=scene_date,
                        description=f"Thermal signature elevated by {delta:.2f} above baseline",
                        metrics={"thermal_delta": delta},
                    )
                )

        sar_scenes = [s for s in scenes if s.source == SatelliteSource.SENTINEL_1]
        if sar_scenes and asset["health_score"] == "critical":
            findings.append(
                ChangeFinding(
                    change_type="sar_backscatter_change",
                    asset_id=asset_id,
                    severity="medium",
                    confidence=0.72,
                    baseline_date=baseline["established_at"],
                    current_date=scene_date,
                    description="SAR backscatter change detected near substation footprint",
                    metrics={"backscatter_delta_db": 3.2},
                )
            )

        if asset["asset_type"] == "tower" and asset["status"] == "maintenance":
            findings.append(
                ChangeFinding(
                    change_type="structural_attention",
                    asset_id=asset_id,
                    severity="medium",
                    confidence=0.65,
                    baseline_date=baseline["established_at"],
                    current_date=scene_date,
                    description="Tower under maintenance — schedule post-trim verification pass",
                    metrics={"maintenance_window_days": 30},
                )
            )

        baseline["last_verified_scene"] = scene_date.isoformat()

    return findings
