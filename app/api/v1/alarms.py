"""Enterprise alarm API (/alarms) + legacy alerts."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services import alarm_service

router = APIRouter(prefix="/alarms", tags=["alarms"])
legacy_router = APIRouter(prefix="/alerts", tags=["alerts"])


class CloseAlarmBody(BaseModel):
    closure_notes: Optional[str] = None
    create_work_order: bool = False


class AckAlarmBody(BaseModel):
    notes: Optional[str] = None


def _wrap(data, pagination: Optional[PaginationMeta] = None) -> ApiResponse:
    return ApiResponse(data=data, meta=ResponseMeta(pagination=pagination))


@router.get("", response_model=ApiResponse)
async def list_alarms(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    asset_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    items, total = await alarm_service.list_alarms(
        session, status=status, severity=severity, asset_id=asset_id, page=page, page_size=page_size
    )
    return _wrap(
        items,
        PaginationMeta(page=page, page_size=page_size, total=total, total_pages=max(1, (total + page_size - 1) // page_size)),
    )


@router.get("/summary", response_model=ApiResponse)
async def alarms_summary(session: AsyncSession = Depends(get_session)):
    return _wrap(await alarm_service.alarm_summary(session))


@router.get("/{alarm_id}", response_model=ApiResponse)
async def get_alarm(alarm_id: str, session: AsyncSession = Depends(get_session)):
    alarm = await alarm_service.get_alarm(session, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return _wrap(alarm)


@router.post("/{alarm_id}/acknowledge", response_model=ApiResponse)
async def acknowledge_alarm(
    alarm_id: str, body: AckAlarmBody, session: AsyncSession = Depends(get_session)
):
    alarm = await alarm_service.acknowledge_alarm(session, alarm_id, body.notes)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return _wrap(alarm)


@router.post("/{alarm_id}/close", response_model=ApiResponse)
async def close_alarm(
    alarm_id: str, body: CloseAlarmBody, session: AsyncSession = Depends(get_session)
):
    alarm = await alarm_service.close_alarm(session, alarm_id, body.closure_notes)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return _wrap(alarm)


# Legacy /alerts endpoints (backward compatible)
@legacy_router.get("", response_model=ApiResponse)
async def list_alerts(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    items, total = await alarm_service.list_alarms(
        session, status=status, severity=priority, page=1, page_size=200
    )
    return _wrap(items, PaginationMeta(page=1, page_size=200, total=total, total_pages=1))


@legacy_router.patch("/{alert_id}/acknowledge", response_model=ApiResponse)
async def acknowledge_alert(alert_id: str, session: AsyncSession = Depends(get_session)):
    alarm = await alarm_service.acknowledge_alarm(session, alert_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _wrap(alarm)
