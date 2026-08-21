"""Saved Tower Suitability site scores API."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services import site_score_service

router = APIRouter(prefix="/site-scores", tags=["site-scores"])


class SiteScoreCreate(BaseModel):
    site_label: str = Field(..., min_length=1, max_length=255)
    place_label: Optional[str] = Field(None, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    final_score: float = Field(..., ge=0, le=10)
    verdict: str = Field(..., min_length=1, max_length=32)
    confidence_pct: Optional[float] = Field(None, ge=0, le=100)
    voltage_kv: Optional[float] = None
    search_radius_km: Optional[float] = Field(None, ge=0, le=200)
    summary: Optional[str] = None
    result_payload: Optional[dict[str, Any]] = None
    factors: Optional[list[dict[str, Any]]] = None
    notes: Optional[str] = None


@router.get("", response_model=ApiResponse)
async def list_site_scores(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    items, total = await site_score_service.list_scores(
        session, q=q, page=page, page_size=page_size
    )
    return ApiResponse(
        data=items,
        meta=ResponseMeta(
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=max(1, (total + page_size - 1) // page_size),
            )
        ),
    )


@router.get("/{score_id}", response_model=ApiResponse)
async def get_site_score(score_id: str, session: AsyncSession = Depends(get_session)):
    item = await site_score_service.get_score(session, score_id)
    if not item:
        raise HTTPException(status_code=404, detail="Site score not found")
    return ApiResponse(data=item, meta=ResponseMeta())


@router.post("", response_model=ApiResponse)
async def create_site_score(payload: SiteScoreCreate, session: AsyncSession = Depends(get_session)):
    row = await site_score_service.create_score(session, payload.model_dump())
    return ApiResponse(data=row, meta=ResponseMeta())


@router.delete("/{score_id}", response_model=ApiResponse)
async def delete_site_score(score_id: str, session: AsyncSession = Depends(get_session)):
    ok = await site_score_service.delete_score(session, score_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Site score not found")
    return ApiResponse(data={"deleted": True, "id": score_id}, meta=ResponseMeta())
