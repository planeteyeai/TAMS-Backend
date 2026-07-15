"""Dashboard, analytics, risk, and predictive APIs."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, ResponseMeta
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])
risk_router = APIRouter(prefix="/risk", tags=["risk"])
predictive_router = APIRouter(prefix="/predictive", tags=["predictive"])


@router.get("/dashboard/operations", response_model=ApiResponse)
async def operations_dashboard(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await dashboard_service.operations_dashboard(session), meta=ResponseMeta())


@router.get("/dashboard/maintenance", response_model=ApiResponse)
async def maintenance_dashboard(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await dashboard_service.maintenance_dashboard(session), meta=ResponseMeta())


@router.get("/dashboard/executive", response_model=ApiResponse)
async def executive_dashboard(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await dashboard_service.executive_dashboard(session), meta=ResponseMeta())


@analytics_router.get("/overview", response_model=ApiResponse)
async def analytics_overview(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await dashboard_service.analytics_overview(session), meta=ResponseMeta())


@analytics_router.get("/risk", response_model=ApiResponse)
async def analytics_risk(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await dashboard_service.risk_summary(session), meta=ResponseMeta())


@risk_router.get("", response_model=ApiResponse)
async def risk_portfolio(session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await dashboard_service.risk_summary(session), meta=ResponseMeta())


@predictive_router.get("/recommendations", response_model=ApiResponse)
async def predictive_recommendations(session: AsyncSession = Depends(get_session)):
    return ApiResponse(
        data=await dashboard_service.predictive_recommendations(session), meta=ResponseMeta()
    )
