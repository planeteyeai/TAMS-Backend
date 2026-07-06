"""API v1 router initialization."""

from fastapi import APIRouter

from app.api.v1 import alerts, analytics, assets, imagery, monitoring
from app.schemas.response import ApiResponse, ResponseMeta

router = APIRouter(tags=["v1"])

router.include_router(assets.router)
router.include_router(alerts.router)
router.include_router(analytics.router)
router.include_router(imagery.router)
router.include_router(monitoring.router)


@router.get("/status", response_model=ApiResponse)
async def api_status():
    """API status endpoint."""
    return ApiResponse(
        data={
            "status": "operational",
            "version": "1.0.0",
            "phase": "2",
            "capabilities": {
                "satellite_sources": ["sentinel-1", "sentinel-2", "landsat-9", "sentinel-2-night"],
                "monitoring_pipeline": True,
                "change_detection": True,
                "alert_generation": True,
                "ml_inference": "heuristic",
                "database": False,
            },
        },
        meta=ResponseMeta(),
    )
