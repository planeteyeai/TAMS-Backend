"""Persist Tower Suitability site scores (DB + in-memory mock fallback)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.init_db import is_db_ready
from app.models import SiteSuitabilityScore

_MOCK: list[dict] = []


def _row_to_dict(row: SiteSuitabilityScore) -> dict:
    return {
        "id": str(row.score_id),
        "score_id": str(row.score_id),
        "site_label": row.site_label,
        "place_label": row.place_label,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "final_score": row.final_score,
        "verdict": row.verdict,
        "confidence_pct": row.confidence_pct,
        "voltage_kv": row.voltage_kv,
        "search_radius_km": row.search_radius_km,
        "summary": row.summary,
        "result_payload": row.result_payload,
        "factors": row.factors,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "source": "db",
    }


def _mock_to_dict(item: dict) -> dict:
    out = deepcopy(item)
    out["id"] = out.get("id") or out.get("score_id")
    out["source"] = "mock"
    return out


async def list_scores(
    session: AsyncSession | None,
    *,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    if not is_db_ready() or session is None:
        items = [_mock_to_dict(i) for i in _MOCK if i.get("is_active", True)]
        if q:
            ql = q.lower()
            items = [
                i
                for i in items
                if ql in (i.get("site_label") or "").lower()
                or ql in (i.get("place_label") or "").lower()
                or ql in (i.get("verdict") or "").lower()
            ]
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    stmt = select(SiteSuitabilityScore).where(SiteSuitabilityScore.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (SiteSuitabilityScore.site_label.ilike(like))
            | (SiteSuitabilityScore.place_label.ilike(like))
            | (SiteSuitabilityScore.verdict.ilike(like))
            | (SiteSuitabilityScore.summary.ilike(like))
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(await session.scalar(count_stmt) or 0)
    stmt = (
        stmt.order_by(SiteSuitabilityScore.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows], total


async def get_score(session: AsyncSession | None, score_id: str) -> dict | None:
    if not is_db_ready() or session is None:
        for item in _MOCK:
            if item.get("id") == score_id or item.get("score_id") == score_id:
                return _mock_to_dict(item) if item.get("is_active", True) else None
        return None
    try:
        uid = UUID(score_id)
    except ValueError:
        return None
    row = await session.get(SiteSuitabilityScore, uid)
    if not row or not row.is_active:
        return None
    return _row_to_dict(row)


async def create_score(session: AsyncSession | None, payload: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if not is_db_ready() or session is None:
        gid = str(uuid4())
        item = {
            "id": gid,
            "score_id": gid,
            "site_label": payload["site_label"],
            "place_label": payload.get("place_label"),
            "latitude": float(payload["latitude"]),
            "longitude": float(payload["longitude"]),
            "final_score": float(payload["final_score"]),
            "verdict": payload["verdict"],
            "confidence_pct": payload.get("confidence_pct"),
            "voltage_kv": payload.get("voltage_kv"),
            "search_radius_km": payload.get("search_radius_km"),
            "summary": payload.get("summary"),
            "result_payload": payload.get("result_payload"),
            "factors": payload.get("factors"),
            "notes": payload.get("notes"),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        _MOCK.insert(0, item)
        return _mock_to_dict(item)

    row = SiteSuitabilityScore(
        site_label=payload["site_label"],
        place_label=payload.get("place_label"),
        latitude=float(payload["latitude"]),
        longitude=float(payload["longitude"]),
        final_score=float(payload["final_score"]),
        verdict=payload["verdict"],
        confidence_pct=payload.get("confidence_pct"),
        voltage_kv=payload.get("voltage_kv"),
        search_radius_km=payload.get("search_radius_km"),
        summary=payload.get("summary"),
        result_payload=payload.get("result_payload"),
        factors=payload.get("factors"),
        notes=payload.get("notes"),
        is_active=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _row_to_dict(row)


async def delete_score(session: AsyncSession | None, score_id: str) -> bool:
    if not is_db_ready() or session is None:
        for item in _MOCK:
            if item.get("id") == score_id or item.get("score_id") == score_id:
                item["is_active"] = False
                return True
        return False
    try:
        uid = UUID(score_id)
    except ValueError:
        return False
    row = await session.get(SiteSuitabilityScore, uid)
    if not row:
        return False
    row.is_active = False
    await session.commit()
    return True
