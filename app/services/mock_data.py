"""
Mock data for Phase 1 development (no database required).
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.services.substation_catalog import build_substation_assets


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _footprint(lon: float, lat: float, half: float = 0.006) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - half, lat + half],
            [lon + half, lat + half],
            [lon + half, lat - half],
            [lon - half, lat - half],
            [lon - half, lat + half],
        ]],
    }


_BASE_ASSETS: list[dict[str, Any]] = [
    {
        "id": "asset-001",
        "name": "Tower TX-101",
        "asset_type": "tower",
        "latitude": 32.7767,
        "longitude": -96.7970,
        "status": "active",
        "health_score": "healthy",
        "description": "Dallas corridor lattice tower",
        "metadata": {"voltage_kv": 345, "structure_type": "lattice"},
        "created_at": _now() - timedelta(days=400),
        "updated_at": _now() - timedelta(hours=2),
    },
    {
        "id": "asset-002",
        "name": "Tower TX-102",
        "asset_type": "tower",
        "latitude": 29.7604,
        "longitude": -95.3698,
        "status": "active",
        "health_score": "attention_required",
        "description": "Houston corridor — thermal anomaly detected",
        "metadata": {"voltage_kv": 345, "structure_type": "monopole"},
        "created_at": _now() - timedelta(days=380),
        "updated_at": _now() - timedelta(hours=1),
    },
    {
        "id": "asset-003",
        "name": "Line L-2201",
        "asset_type": "line",
        "latitude": 30.2672,
        "longitude": -97.7431,
        "status": "active",
        "health_score": "healthy",
        "description": "Austin–San Antonio 220kV corridor segment",
        "metadata": {"voltage_kv": 220, "length_km": 45.2},
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-98.05, 30.45],
                [-97.74, 30.27],
                [-97.35, 29.95],
                [-97.05, 29.72],
                [-96.80, 29.55],
            ],
        },
        "created_at": _now() - timedelta(days=500),
        "updated_at": _now() - timedelta(hours=6),
    },
    {
        "id": "asset-004",
        "name": "Substation SS-HOU-01",
        "asset_type": "substation",
        "latitude": 29.7499,
        "longitude": -95.3584,
        "status": "active",
        "health_score": "critical",
        "description": "Houston East substation — elevated load risk",
        "metadata": {"voltage_kv": 500, "transformer_count": 4, "region": "North America", "country_or_state": "USA"},
        "geometry": _footprint(-95.3584, 29.7499),
        "created_at": _now() - timedelta(days=600),
        "updated_at": _now() - timedelta(minutes=30),
    },
    {
        "id": "asset-005",
        "name": "Tower TX-205",
        "asset_type": "tower",
        "latitude": 35.4676,
        "longitude": -97.5164,
        "status": "maintenance",
        "health_score": "attention_required",
        "description": "Oklahoma City corridor — vegetation encroachment",
        "metadata": {"voltage_kv": 138, "structure_type": "lattice"},
        "created_at": _now() - timedelta(days=300),
        "updated_at": _now() - timedelta(hours=12),
    },
    {
        "id": "asset-006",
        "name": "Tower TX-310",
        "asset_type": "tower",
        "latitude": 39.7392,
        "longitude": -104.9903,
        "status": "active",
        "health_score": "healthy",
        "description": "Denver mountain corridor tower",
        "metadata": {"voltage_kv": 230, "structure_type": "guyed"},
        "created_at": _now() - timedelta(days=250),
        "updated_at": _now() - timedelta(hours=4),
    },
]

MOCK_ASSETS: list[dict[str, Any]] = _BASE_ASSETS + build_substation_assets(start_id=100)

# Sample alerts for India substation
_IN_ALERT = next((a for a in MOCK_ASSETS if a["name"] == "SS-KNP-ANPARA-765"), None)
_IN_ATTN = next((a for a in MOCK_ASSETS if a["name"] == "SS-MUM-KALWA-400"), None)

MOCK_ALERTS: list[dict[str, Any]] = [
    {
        "id": "alert-001",
        "asset_id": "asset-002",
        "alert_type": "thermal_anomaly",
        "priority": "high",
        "title": "Night thermal hotspot detected",
        "message": "Sentinel-2 night imaging detected elevated thermal signature near Tower TX-102.",
        "status": "open",
        "created_at": _now() - timedelta(hours=3),
    },
    {
        "id": "alert-002",
        "asset_id": "asset-005",
        "alert_type": "vegetation_encroachment",
        "priority": "medium",
        "title": "Vegetation growth in ROW corridor",
        "message": "SegFormer corridor analysis shows vegetation within clearance threshold.",
        "status": "open",
        "created_at": _now() - timedelta(hours=8),
    },
    {
        "id": "alert-003",
        "asset_id": "asset-004",
        "alert_type": "scada_abnormality",
        "priority": "critical",
        "title": "Transformer loading exceeds threshold",
        "message": "SCADA reports 94% transformer loading at SS-HOU-01.",
        "status": "open",
        "created_at": _now() - timedelta(minutes=45),
    },
    {
        "id": "alert-004",
        "asset_id": "asset-006",
        "alert_type": "wildfire_risk",
        "priority": "medium",
        "title": "Elevated wildfire risk in corridor",
        "message": "MODIS fire products indicate dry vegetation and moderate fire weather index.",
        "status": "acknowledged",
        "created_at": _now() - timedelta(days=1),
    },
]
if _IN_ALERT:
    MOCK_ALERTS.append({
        "id": "alert-005",
        "asset_id": _IN_ALERT["id"],
        "alert_type": "scada_abnormality",
        "priority": "critical",
        "title": "Anpara 765kV transformer overload",
        "message": "SCADA reports 96% loading at SS-KNP-ANPARA-765. Schedule maintenance.",
        "status": "open",
        "created_at": _now() - timedelta(hours=2),
    })
if _IN_ATTN:
    MOCK_ALERTS.append({
        "id": "alert-006",
        "asset_id": _IN_ATTN["id"],
        "alert_type": "thermal_anomaly",
        "priority": "high",
        "title": "Mumbai coastal substation thermal rise",
        "message": "Sentinel-2 analysis shows thermal elevation near SS-MUM-KALWA-400.",
        "status": "open",
        "created_at": _now() - timedelta(hours=5),
    })

MOCK_RISK_SUMMARY: dict[str, Any] = {
    "asset_risk": {"low": 2, "medium": 2, "high": 1, "critical": 1},
    "corridor_risk": {"low": 1, "medium": 2, "high": 2, "critical": 1},
    "regional_risk": {"low": 0, "medium": 3, "high": 2, "critical": 1},
    "weather_risk_score": 62,
    "wildfire_risk_score": 48,
    "outage_probability_90d": 0.12,
}

MOCK_ANALYTICS: dict[str, Any] = {
    "total_assets": len(MOCK_ASSETS),
    "assets_by_type": {
        "tower": sum(1 for a in MOCK_ASSETS if a["asset_type"] == "tower"),
        "line": sum(1 for a in MOCK_ASSETS if a["asset_type"] == "line"),
        "substation": sum(1 for a in MOCK_ASSETS if a["asset_type"] == "substation"),
    },
    "substations_by_region": {
        "India": sum(
            1 for a in MOCK_ASSETS
            if a["asset_type"] == "substation"
            and a.get("metadata", {}).get("region") == "India"
        ),
        "World": sum(
            1 for a in MOCK_ASSETS
            if a["asset_type"] == "substation"
            and a.get("metadata", {}).get("region") != "India"
        ),
    },
    "health_distribution": {
        "healthy": sum(1 for a in MOCK_ASSETS if a["health_score"] == "healthy"),
        "attention_required": sum(
            1 for a in MOCK_ASSETS if a["health_score"] == "attention_required"
        ),
        "critical": sum(1 for a in MOCK_ASSETS if a["health_score"] == "critical"),
    },
    "open_alerts": sum(1 for a in MOCK_ALERTS if a["status"] == "open"),
    "maintenance_recommendations": [
        {
            "asset_id": "asset-002",
            "priority": "high",
            "action": "Schedule thermal inspection and SCADA correlation review",
        },
        {
            "asset_id": "asset-005",
            "priority": "medium",
            "action": "Vegetation trimming within 30-day maintenance window",
        },
        {
            "asset_id": "asset-004",
            "priority": "critical",
            "action": "Reduce load or schedule transformer maintenance immediately",
        },
    ],
}


def create_asset(payload: dict[str, Any]) -> dict[str, Any]:
    asset = {
        "id": f"asset-{uuid4().hex[:8]}",
        **payload,
        "health_score": payload.get("health_score", "healthy"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    MOCK_ASSETS.append(asset)
    return asset
