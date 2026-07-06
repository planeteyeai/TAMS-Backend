"""Alert management API endpoints."""

from datetime import datetime, timezone

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.response import ApiResponse, ResponseMeta
from app.services.mock_data import MOCK_ALERTS

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=ApiResponse)
async def list_alerts(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    """List system alerts with optional filters."""
    items = MOCK_ALERTS
    if status:
        items = [a for a in items if a["status"] == status]
    if priority:
        items = [a for a in items if a["priority"] == priority]
    return ApiResponse(data=items, meta=ResponseMeta())


@router.patch("/{alert_id}/acknowledge", response_model=ApiResponse)
async def acknowledge_alert(alert_id: str):
    """Acknowledge an open alert."""
    alert = next((a for a in MOCK_ALERTS if a["id"] == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert["status"] = "acknowledged"
    alert["acknowledged_at"] = datetime.now(timezone.utc)
    return ApiResponse(data=alert, meta=ResponseMeta())
