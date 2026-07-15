"""Health and condition monitoring service."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import is_db_ready
from app.models import Asset, HealthScore
from app.services.mock_data import MOCK_ASSETS


async def portfolio_health(session: AsyncSession | None) -> dict:
    if not is_db_ready() or session is None:
        from app.services.kml_loader import get_region_stats

        stats = get_region_stats()
        total = stats["total"]
        scores = []
        for a in MOCK_ASSETS:
            hs = a.get("health_score", "healthy")
            if hs == "healthy":
                scores.append(88.0)
            elif hs == "attention_required":
                scores.append(62.0)
            else:
                scores.append(35.0)
        avg = sum(scores) / len(scores) if scores else 0
        return {
            "average_health_score": round(avg, 1),
            "distribution": {
                "excellent": sum(1 for s in scores if s >= 80),
                "good": sum(1 for s in scores if 60 <= s < 80),
                "fair": sum(1 for s in scores if 40 <= s < 60),
                "poor": sum(1 for s in scores if 20 <= s < 40),
                "critical": sum(1 for s in scores if s < 20),
            },
            "total_assets": total,
        }

    subq = (
        select(
            HealthScore.asset_id,
            func.max(HealthScore.computed_at).label("max_at"),
        )
        .group_by(HealthScore.asset_id)
        .subquery()
    )
    stmt = (
        select(HealthScore)
        .join(
            subq,
            (HealthScore.asset_id == subq.c.asset_id) & (HealthScore.computed_at == subq.c.max_at),
        )
        .options(selectinload(HealthScore.asset).selectinload(Asset.asset_type))
    )
    rows = (await session.scalars(stmt)).all()
    scores = [r.health_score for r in rows]
    avg = sum(scores) / len(scores) if scores else 0

    top_risk = sorted(rows, key=lambda r: r.risk_score, reverse=True)[:10]
    return {
        "average_health_score": round(avg, 1),
        "distribution": {
            "excellent": sum(1 for s in scores if s >= 80),
            "good": sum(1 for s in scores if 60 <= s < 80),
            "fair": sum(1 for s in scores if 40 <= s < 60),
            "poor": sum(1 for s in scores if 20 <= s < 40),
            "critical": sum(1 for s in scores if s < 20),
        },
        "top_risk_assets": [
            {
                "asset_id": str(r.asset_id),
                "asset_code": r.asset.asset_code if r.asset else None,
                "risk_score": r.risk_score,
                "health_score": r.health_score,
            }
            for r in top_risk
        ],
        "total_assets": len(scores),
    }


async def asset_health(session: AsyncSession | None, asset_id: str) -> dict | None:
    if not is_db_ready() or session is None:
        asset = next((a for a in MOCK_ASSETS if a["id"] == asset_id), None)
        if not asset:
            return None
        hs = {"healthy": 88, "attention_required": 62, "critical": 35}.get(asset.get("health_score"), 75)
        return {
            "asset_id": asset_id,
            "health_score": hs,
            "condition_score": 1 if hs >= 80 else 3 if hs >= 50 else 5,
            "risk_score": 100 - hs,
            "rul_months": 84 if hs >= 70 else 24,
            "factors": {
                "age_factor": 0.85,
                "loading_factor": 0.72,
                "inspection_factor": 0.80,
                "failure_history_factor": 0.90,
                "sensor_health_factor": 0.95,
                "criticality_factor": 0.70,
            },
        }

    try:
        uid = UUID(asset_id)
    except ValueError:
        return None

    row = await session.scalar(
        select(HealthScore)
        .where(HealthScore.asset_id == uid)
        .order_by(HealthScore.computed_at.desc())
        .limit(1)
    )
    if not row:
        return None
    return {
        "asset_id": asset_id,
        "health_score": row.health_score,
        "condition_score": row.condition_score,
        "risk_score": row.risk_score,
        "rul_months": row.rul_months,
        "computed_at": row.computed_at,
        "model_version": row.model_version,
        "factors": {
            "age_factor": row.age_factor,
            "loading_factor": row.loading_factor,
            "inspection_factor": row.inspection_factor,
            "failure_history_factor": row.failure_history_factor,
            "sensor_health_factor": row.sensor_health_factor,
            "criticality_factor": row.criticality_factor,
        },
    }
