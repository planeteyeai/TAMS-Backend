"""Inspection management service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import is_db_ready
from app.models import Inspection


def _insp_to_dict(row: Inspection) -> dict:
    return {
        "inspection_id": str(row.inspection_id),
        "id": str(row.inspection_id),
        "asset_id": str(row.asset_id),
        "asset_code": row.asset.asset_code if row.asset else None,
        "inspection_type": row.inspection_type,
        "status": row.status,
        "inspector_name": row.inspector_name,
        "scheduled_date": row.scheduled_date,
        "completed_date": row.completed_date,
        "overall_score": row.overall_score,
        "summary": row.summary,
        "created_at": row.created_at,
    }


_MOCK_INSPECTIONS: list[dict] = []


async def list_inspections(
    session: AsyncSession | None,
    *,
    status: str | None = None,
    inspection_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    if not is_db_ready() or session is None:
        items = _MOCK_INSPECTIONS
        if status:
            items = [i for i in items if i.get("status") == status]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    stmt = select(Inspection).options(selectinload(Inspection.asset))
    if status:
        stmt = stmt.where(Inspection.status == status)
    if inspection_type:
        stmt = stmt.where(Inspection.inspection_type == inspection_type)

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(Inspection.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.scalars(stmt)).all()
    return [_insp_to_dict(r) for r in rows], int(total or 0)


async def create_inspection(session: AsyncSession | None, payload: dict) -> dict:
    if not is_db_ready() or session is None:
        insp = {
            "inspection_id": str(uuid4()),
            "id": str(uuid4()),
            **payload,
            "status": payload.get("status", "Scheduled"),
            "created_at": datetime.now(timezone.utc),
        }
        _MOCK_INSPECTIONS.append(insp)
        return insp

    row = Inspection(
        asset_id=UUID(payload["asset_id"]),
        inspection_type=payload["inspection_type"],
        status=payload.get("status", "Scheduled"),
        inspector_name=payload.get("inspector_name"),
        scheduled_date=payload.get("scheduled_date"),
        summary=payload.get("summary"),
        overall_score=payload.get("overall_score"),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row, ["asset"])
    return _insp_to_dict(row)
