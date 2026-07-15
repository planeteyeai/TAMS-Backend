"""Health and condition monitoring API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, ResponseMeta
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ApiResponse)
async def portfolio_health(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await health_service.portfolio_health(session), meta=ResponseMeta())


@router.get("/assets/{asset_id}", response_model=ApiResponse)
async def asset_health(asset_id: str, session: AsyncSession = Depends(get_session)):
    data = await health_service.asset_health(session, asset_id)
    if not data:
        raise HTTPException(status_code=404, detail="Health data not found")
    return ApiResponse(data=data, meta=ResponseMeta())
