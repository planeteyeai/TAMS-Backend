"""Inspection management API."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services import inspection_service

router = APIRouter(prefix="/inspections", tags=["inspections"])


class InspectionCreate(BaseModel):
    asset_id: str
    inspection_type: str = Field(..., pattern="^(Manual|Drone|Thermal|Visual)$")
    inspector_name: Optional[str] = None
    scheduled_date: Optional[str] = None
    summary: Optional[str] = None
    overall_score: Optional[float] = Field(None, ge=0, le=100)


@router.get("", response_model=ApiResponse)
async def list_inspections(
    status: Optional[str] = Query(None),
    inspection_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    items, total = await inspection_service.list_inspections(
        session, status=status, inspection_type=inspection_type, page=page, page_size=page_size
    )
    return ApiResponse(
        data=items,
        meta=ResponseMeta(
            pagination=PaginationMeta(
                page=page, page_size=page_size, total=total, total_pages=max(1, (total + page_size - 1) // page_size)
            )
        ),
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_inspection(payload: InspectionCreate, session: AsyncSession = Depends(get_session)):
    row = await inspection_service.create_inspection(session, payload.model_dump())
    return ApiResponse(data=row, meta=ResponseMeta())


@router.post("/{inspection_id}/analyze", response_model=ApiResponse, status_code=202)
async def analyze_inspection(inspection_id: str):
    return ApiResponse(
        data={
            "analysis_job_id": f"job-{inspection_id[:8]}",
            "status": "Processing",
            "estimated_completion_seconds": 120,
            "defects_detected": [],
            "note": "AI analysis queued (Azure Custom Vision integration pending)",
        },
        meta=ResponseMeta(),
    )
