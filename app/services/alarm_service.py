"""Alarm management service."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import is_db_ready
from app.models import Alarm, Asset
from app.services.mock_data import MOCK_ALERTS


def _alarm_to_dict(alarm: Alarm, asset: Asset | None = None) -> dict:
    return {
        "id": str(alarm.alarm_id),
        "alarm_id": str(alarm.alarm_id),
        "asset_id": str(alarm.asset_id),
        "asset_code": asset.asset_code if asset else None,
        "alarm_code": alarm.alarm_code,
        "title": alarm.title,
        "description": alarm.description,
        "severity": alarm.severity,
        "priority": alarm.severity.lower(),
        "status": alarm.status,
        "alert_type": alarm.alarm_code,
        "message": alarm.description,
        "trigger_value": alarm.trigger_value,
        "threshold_value": alarm.threshold_value,
        "generated_at": alarm.generated_at,
        "acknowledged_at": alarm.acknowledged_at,
        "closed_at": alarm.closed_at,
        "closure_notes": alarm.closure_notes,
        "escalation_level": alarm.escalation_level,
    }


async def list_alarms(
    session: AsyncSession | None,
    *,
    status: str | None = None,
    severity: str | None = None,
    asset_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    if not is_db_ready() or session is None:
        items = MOCK_ALERTS
        if status:
            items = [a for a in items if a.get("status") == status]
        if severity:
            items = [a for a in items if a.get("priority") == severity.lower()]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    stmt = select(Alarm).options(selectinload(Alarm.asset))
    if status:
        status_map = {"open": "Active", "acknowledged": "Acknowledged", "closed": "Closed"}
        stmt = stmt.where(Alarm.status == status_map.get(status, status))
    if severity:
        stmt = stmt.where(Alarm.severity == severity.capitalize())
    if asset_id:
        stmt = stmt.where(Alarm.asset_id == UUID(asset_id))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(Alarm.generated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.scalars(stmt)).all()
    return [_alarm_to_dict(r, r.asset) for r in rows], int(total or 0)


async def get_alarm(session: AsyncSession | None, alarm_id: str) -> dict | None:
    if not is_db_ready() or session is None:
        return next((a for a in MOCK_ALERTS if a["id"] == alarm_id), None)

    try:
        uid = UUID(alarm_id)
    except ValueError:
        return None

    alarm = await session.scalar(
        select(Alarm).options(selectinload(Alarm.asset)).where(Alarm.alarm_id == uid)
    )
    return _alarm_to_dict(alarm, alarm.asset) if alarm else None


async def acknowledge_alarm(session: AsyncSession | None, alarm_id: str, notes: str | None = None) -> dict | None:
    if not is_db_ready() or session is None:
        alert = next((a for a in MOCK_ALERTS if a["id"] == alarm_id), None)
        if alert:
            alert["status"] = "acknowledged"
            alert["acknowledged_at"] = datetime.now(timezone.utc)
        return alert

    try:
        uid = UUID(alarm_id)
    except ValueError:
        return None

    alarm = await session.scalar(select(Alarm).options(selectinload(Alarm.asset)).where(Alarm.alarm_id == uid))
    if not alarm:
        return None
    alarm.status = "Acknowledged"
    alarm.acknowledged_at = datetime.now(timezone.utc)
    if notes:
        alarm.description = (alarm.description or "") + f"\nAck notes: {notes}"
    await session.commit()
    return _alarm_to_dict(alarm, alarm.asset)


async def close_alarm(
    session: AsyncSession | None, alarm_id: str, closure_notes: str | None = None
) -> dict | None:
    if not is_db_ready() or session is None:
        alert = next((a for a in MOCK_ALERTS if a["id"] == alarm_id), None)
        if alert:
            alert["status"] = "closed"
        return alert

    try:
        uid = UUID(alarm_id)
    except ValueError:
        return None

    alarm = await session.scalar(select(Alarm).options(selectinload(Alarm.asset)).where(Alarm.alarm_id == uid))
    if not alarm:
        return None
    alarm.status = "Closed"
    alarm.closed_at = datetime.now(timezone.utc)
    alarm.closure_notes = closure_notes
    await session.commit()
    return _alarm_to_dict(alarm, alarm.asset)


async def alarm_summary(session: AsyncSession | None) -> dict:
    if not is_db_ready() or session is None:
        active = [a for a in MOCK_ALERTS if a.get("status") == "open"]
        by_sev: dict[str, int] = {}
        for a in active:
            sev = a.get("priority", "medium").capitalize()
            by_sev[sev] = by_sev.get(sev, 0) + 1
        return {"active": len(active), "by_severity": by_sev}

    rows = await session.execute(
        select(Alarm.severity, func.count())
        .where(Alarm.status.in_(["Active", "Acknowledged", "InProgress"]))
        .group_by(Alarm.severity)
    )
    by_sev = {sev: count for sev, count in rows.all()}
    active = sum(by_sev.values())
    return {"active": active, "by_severity": by_sev}
