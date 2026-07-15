"""
Mock data for development (no database required).
Transmission assets are loaded from indian_KML at application startup — see kml_loader.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

# Populated at startup from KML (lines + substations). Towers load via /gis/towers bbox API.
MOCK_ASSETS: list[dict[str, Any]] = []

MOCK_ALERTS: list[dict[str, Any]] = []

MOCK_RISK_SUMMARY: dict[str, Any] = {
    "asset_risk": {"low": 0, "medium": 0, "high": 0, "critical": 0},
    "corridor_risk": {"low": 0, "medium": 0, "high": 0, "critical": 0},
    "regional_risk": {"low": 0, "medium": 0, "high": 0, "critical": 0},
    "weather_risk_score": 42,
    "wildfire_risk_score": 28,
    "outage_probability_90d": 0.06,
}

MOCK_ANALYTICS: dict[str, Any] = {
    "total_assets": 0,
    "assets_by_type": {"tower": 0, "line": 0, "substation": 0},
    "substations_by_region": {"India": 0},
    "health_distribution": {"healthy": 0, "attention_required": 0, "critical": 0},
    "open_alerts": 0,
    "maintenance_recommendations": [],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def rebuild_derived_mock_data() -> None:
    """Rebuild alerts and analytics from KML-loaded MOCK_ASSETS."""
    global MOCK_RISK_SUMMARY, MOCK_ANALYTICS

    from app.services.kml_loader import get_region_stats

    india_stats = get_region_stats()
    gujarat_stats = get_region_stats(state="Gujarat")

    MOCK_ALERTS.clear()

    gujarat_lines = [
        a
        for a in MOCK_ASSETS
        if a["asset_type"] == "line"
        and str(a.get("metadata", {}).get("country_or_state", "")).lower() == "gujarat"
    ]
    gujarat_subs = [
        a
        for a in MOCK_ASSETS
        if a["asset_type"] == "substation"
        and str(a.get("metadata", {}).get("country_or_state", "")).lower() == "gujarat"
    ]
    high_voltage_lines = sorted(
        gujarat_lines,
        key=lambda a: int(a.get("metadata", {}).get("voltage_kv") or 0),
        reverse=True,
    )

    if high_voltage_lines:
        line = high_voltage_lines[0]
        MOCK_ALERTS.append(
            {
                "id": "alert-gj-001",
                "asset_id": line["id"],
                "alert_type": "vegetation_encroachment",
                "priority": "medium",
                "title": "ROW vegetation near 400 kV corridor",
                "message": f"Corridor analysis flagged vegetation encroachment along {line['name']}.",
                "status": "open",
                "created_at": _now() - timedelta(hours=6),
            }
        )

    if len(high_voltage_lines) > 1:
        line2 = high_voltage_lines[1]
        MOCK_ALERTS.append(
            {
                "id": "alert-gj-002",
                "asset_id": line2["id"],
                "alert_type": "thermal_anomaly",
                "priority": "high",
                "title": "Thermal hotspot on transmission corridor",
                "message": f"Sentinel-2 night imaging detected elevated thermal signature on {line2['name']}.",
                "status": "open",
                "created_at": _now() - timedelta(hours=3),
            }
        )

    if gujarat_subs:
        sub = gujarat_subs[0]
        MOCK_ALERTS.append(
            {
                "id": "alert-gj-003",
                "asset_id": sub["id"],
                "alert_type": "scada_abnormality",
                "priority": "high",
                "title": f"Substation loading alert — {sub['name']}",
                "message": f"SCADA reports elevated load at {sub['name']} ({sub.get('metadata', {}).get('voltage_kv', '?')} kV).",
                "status": "open",
                "created_at": _now() - timedelta(hours=2),
            }
        )

    towers_total = india_stats["towers"]
    lines = india_stats["lines"]
    subs = india_stats["substations"]
    gujarat_lines_n = gujarat_stats["lines"]

    MOCK_RISK_SUMMARY = {
        "asset_risk": {
            "low": max(1, gujarat_lines_n // 3),
            "medium": max(1, gujarat_lines_n // 5),
            "high": max(1, open_alerts_high()),
            "critical": 0,
        },
        "corridor_risk": {
            "low": max(1, lines // 4),
            "medium": max(1, lines // 6),
            "high": 1,
            "critical": 0,
        },
        "regional_risk": {
            "low": 2,
            "medium": 1,
            "high": 1,
            "critical": 0,
        },
        "weather_risk_score": 38,
        "wildfire_risk_score": 22,
        "outage_probability_90d": 0.05,
    }

    MOCK_ANALYTICS = {
        "total_assets": india_stats["total"],
        "assets_by_type": {
            "tower": towers_total,
            "line": lines,
            "substation": subs,
        },
        "substations_by_region": {
            "India": subs,
        },
        "health_distribution": {
            "healthy": india_stats["total"] - len(MOCK_ALERTS),
            "attention_required": len([a for a in MOCK_ALERTS if a["priority"] in ("medium", "high")]),
            "critical": len([a for a in MOCK_ALERTS if a["priority"] == "critical"]),
        },
        "open_alerts": sum(1 for a in MOCK_ALERTS if a["status"] == "open"),
        "maintenance_recommendations": [
            {
                "asset_id": a["asset_id"],
                "priority": a["priority"],
                "action": a["message"],
            }
            for a in MOCK_ALERTS[:3]
        ],
    }


def open_alerts_high() -> int:
    return sum(1 for a in MOCK_ALERTS if a["priority"] in ("high", "critical"))


def create_asset(payload: dict[str, Any]) -> dict[str, Any]:
    asset = {
        "id": f"asset-{uuid4().hex[:8]}",
        **payload,
        "health_score": payload.get("health_score", "healthy"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    MOCK_ASSETS.append(asset)
    rebuild_derived_mock_data()
    return asset
