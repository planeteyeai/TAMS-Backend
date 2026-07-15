"""Work order and maintenance API."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services import maintenance_service

router = APIRouter(prefix="/workorders", tags=["workorders"])
maint_router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class WorkOrderCreate(BaseModel):
    asset_id: str
    maintenance_type: str = Field(..., pattern="^(PM|PdM|CM|EM)$")
    priority: str = "Medium"
    description: Optional[str] = None
    assigned_crew: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    estimated_cost: Optional[float] = None


def _wrap(data, pagination: Optional[PaginationMeta] = None) -> ApiResponse:
    return ApiResponse(data=data, meta=ResponseMeta(pagination=pagination))


@router.get("", response_model=ApiResponse)
async def list_work_orders(
    status: Optional[str] = Query(None),
    maintenance_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    items, total = await maintenance_service.list_work_orders(
        session, status=status, maintenance_type=maintenance_type, page=page, page_size=page_size
    )
    return _wrap(
        items,
        PaginationMeta(page=page, page_size=page_size, total=total, total_pages=max(1, (total + page_size - 1) // page_size)),
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_work_order(payload: WorkOrderCreate, session: AsyncSession = Depends(get_session)):
    wo = await maintenance_service.create_work_order(session, payload.model_dump())
    return _wrap(wo)


@router.get("/{work_order_id}", response_model=ApiResponse)
async def get_work_order(work_order_id: str, session: AsyncSession = Depends(get_session)):
    wo = await maintenance_service.get_work_order(session, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return _wrap(wo)


@maint_router.get("/assets/{asset_id}/history", response_model=ApiResponse)
async def maintenance_history(asset_id: str, session: AsyncSession = Depends(get_session)):
    items, _ = await maintenance_service.list_work_orders(session, page=1, page_size=100)
    history = [w for w in items if w.get("asset_id") == asset_id]
    return _wrap(history)
