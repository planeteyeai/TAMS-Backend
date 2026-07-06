"""Analytics and risk intelligence API endpoints."""

from fastapi import APIRouter

from app.schemas.response import ApiResponse, ResponseMeta
from app.services.mock_data import MOCK_ANALYTICS, MOCK_RISK_SUMMARY

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=ApiResponse)
async def analytics_overview():
    """Platform analytics overview for executive dashboard."""
    return ApiResponse(data=MOCK_ANALYTICS, meta=ResponseMeta())


@router.get("/risk", response_model=ApiResponse)
async def risk_summary():
    """Risk intelligence summary across assets, corridors, and regions."""
    return ApiResponse(data=MOCK_RISK_SUMMARY, meta=ResponseMeta())
