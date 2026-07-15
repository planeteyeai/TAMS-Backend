"""API v1 router initialization."""

from fastapi import APIRouter

from app.api.v1 import (
    alarms,
    assets,
    dashboard,
    gis,
    health,
    imagery,
    inspections,
    monitoring,
    workorders,
)
from app.db.init_db import is_db_ready
from app.schemas.response import ApiResponse, ResponseMeta

router = APIRouter(tags=["v1"])

router.include_router(assets.router)
router.include_router(alarms.router)
router.include_router(alarms.legacy_router)
router.include_router(health.router)
router.include_router(workorders.router)
router.include_router(workorders.maint_router)
router.include_router(inspections.router)
router.include_router(gis.router)
router.include_router(dashboard.router)
router.include_router(dashboard.analytics_router)
router.include_router(dashboard.risk_router)
router.include_router(dashboard.predictive_router)
router.include_router(imagery.router)
router.include_router(monitoring.router)


@router.get("/status", response_model=ApiResponse)
async def api_status():
    """API status endpoint."""
    db = is_db_ready()
    return ApiResponse(
        data={
            "status": "operational",
            "version": "1.0.0",
            "phase": "1-mvp" if db else "2",
            "capabilities": {
                "asset_registry": True,
                "asset_hierarchy": True,
                "gis_module": True,
                "alarm_management": True,
                "health_monitoring": True,
                "maintenance_work_orders": True,
                "inspection_management": True,
                "predictive_maintenance": "heuristic",
                "dashboard_analytics": True,
                "satellite_sources": ["sentinel-1", "sentinel-2", "landsat-9", "sentinel-2-night"],
                "monitoring_pipeline": True,
                "change_detection": True,
                "alert_generation": True,
                "ml_inference": "heuristic",
                "database": db,
            },
        },
        meta=ResponseMeta(),
    )
