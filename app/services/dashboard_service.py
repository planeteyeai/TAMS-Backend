"""Dashboard and analytics aggregation."""

from app.db.init_db import is_db_ready
from app.services.alarm_service import alarm_summary
from app.services.asset_service import list_assets
from app.services.health_service import portfolio_health
from app.services.maintenance_service import list_work_orders
from app.services.mock_data import MOCK_ANALYTICS, MOCK_RISK_SUMMARY
from sqlalchemy.ext.asyncio import AsyncSession


async def operations_dashboard(session: AsyncSession | None) -> dict:
    from app.db.init_db import is_db_ready
    from app.services.kml_loader import get_region_stats

    if not is_db_ready() or session is None:
        stats = get_region_stats()
        total_count = stats["total"]
    else:
        _, total_count = await list_assets(session, page=1, page_size=1)
    assets, _ = await list_assets(session, page=1, page_size=1)
    alarms = await alarm_summary(session)
    health = await portfolio_health(session)

    return {
        "active_alarms": alarms.get("active", 0),
        "alarms_by_severity": alarms.get("by_severity", {}),
        "assets_monitored": total_count,
        "average_health_score": health.get("average_health_score", 0),
        "critical_assets": health.get("distribution", {}).get("critical", 0),
    }


async def maintenance_dashboard(session: AsyncSession | None) -> dict:
    open_statuses = ["Draft", "Approved", "Scheduled", "Assigned", "InProgress"]
    all_wos, total = await list_work_orders(session, page=1, page_size=500)
    open_wos = [w for w in all_wos if w.get("status") in open_statuses]
    pm = [w for w in all_wos if w.get("maintenance_type") == "PM"]
    completed_pm = [w for w in pm if w.get("status") in ("Completed", "Closed")]

    return {
        "open_work_orders": len(open_wos),
        "total_work_orders": total,
        "pm_compliance_pct": round(len(completed_pm) / len(pm) * 100, 1) if pm else 100.0,
        "by_type": {
            t: sum(1 for w in all_wos if w.get("maintenance_type") == t)
            for t in ("PM", "PdM", "CM", "EM")
        },
    }


async def executive_dashboard(session: AsyncSession | None) -> dict:
    health = await portfolio_health(session)
    maint = await maintenance_dashboard(session)
    ops = await operations_dashboard(session)

    return {
        "average_health_score": health.get("average_health_score"),
        "health_distribution": health.get("distribution"),
        "top_risk_assets": health.get("top_risk_assets", [])[:5],
        "active_alarms": ops.get("active_alarms"),
        "open_work_orders": maint.get("open_work_orders"),
        "assets_monitored": ops.get("assets_monitored"),
        "kpi": {
            "saidi_minutes": 45.2,
            "saifi": 1.82,
            "availability_pct": 99.4,
            "mtbf_hours": 8420,
            "mttr_hours": 4.2,
        },
    }


async def analytics_overview(session: AsyncSession | None) -> dict:
    if not is_db_ready() or session is None:
        return MOCK_ANALYTICS

    _, total = await list_assets(session, page=1, page_size=10000)
    items, _ = await list_assets(session, page=1, page_size=10000)
    alarms = await alarm_summary(session)
    health = await portfolio_health(session)

    return {
        "total_assets": total,
        "assets_by_type": {
            t: sum(1 for a in items if a.get("asset_type") == t)
            for t in ("tower", "line", "substation")
        },
        "health_distribution": health.get("distribution"),
        "open_alerts": alarms.get("active", 0),
        "average_health_score": health.get("average_health_score"),
    }


async def risk_summary(session: AsyncSession | None) -> dict:
    if not is_db_ready() or session is None:
        return MOCK_RISK_SUMMARY

    health = await portfolio_health(session)
    dist = health.get("distribution", {})
    return {
        "asset_risk": {
            "low": dist.get("excellent", 0),
            "medium": dist.get("good", 0) + dist.get("fair", 0),
            "high": dist.get("poor", 0),
            "critical": dist.get("critical", 0),
        },
        "top_risk_assets": health.get("top_risk_assets", []),
        "outage_probability_90d": 0.12,
    }


async def predictive_recommendations(session: AsyncSession | None) -> list[dict]:
    health = await portfolio_health(session)
    recs = []
    for i, asset in enumerate(health.get("top_risk_assets", [])[:10]):
        recs.append(
            {
                "recommendation_id": f"rec-{i + 1}",
                "asset_id": asset.get("asset_id"),
                "asset_code": asset.get("asset_code"),
                "recommendation_type": "Inspection",
                "recommended_action": "Schedule condition assessment within 30 days",
                "confidence_score": 0.75 + i * 0.02,
                "risk_probability": asset.get("risk_score", 50) / 100,
                "priority_rank": i + 1,
                "rul_months": 18,
                "model_version": "heuristic-v1",
            }
        )
    if not recs and not is_db_ready():
        return MOCK_ANALYTICS.get("maintenance_recommendations", [])
    return recs
