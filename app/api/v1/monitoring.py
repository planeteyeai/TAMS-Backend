"""Monitoring workflow API — acquire, detect, compare, alert pipeline."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.monitoring import MonitoringRunRequest, SatelliteSource
from app.schemas.response import ApiResponse, ResponseMeta
from app.services import monitoring_workflow, stac_catalog

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/workflow", response_model=ApiResponse)
async def get_workflow():
    """Return the canonical monitoring workflow definition for UI and docs."""
    return ApiResponse(
        data=monitoring_workflow.get_workflow_definition(),
        meta=ResponseMeta(),
    )


@router.post("/run", response_model=ApiResponse)
async def run_monitoring_cycle(request: MonitoringRunRequest):
    """
    Execute a full monitoring cycle for selected assets.

    Pipeline: Acquire satellite scenes → AI detection → change comparison → alert generation.
    """
    result = await monitoring_workflow.run_monitoring(request)
    return ApiResponse(data=result.model_dump(), meta=ResponseMeta())


@router.get("/runs", response_model=ApiResponse)
async def list_monitoring_runs(limit: int = Query(10, ge=1, le=50)):
    """List recent monitoring run history."""
    runs = monitoring_workflow.RUN_HISTORY[:limit]
    return ApiResponse(
        data={
            "runs": [r.model_dump() for r in runs],
            "count": len(runs),
        },
        meta=ResponseMeta(),
    )


@router.get("/runs/{run_id}", response_model=ApiResponse)
async def get_monitoring_run(run_id: str):
    """Get details for a specific monitoring run."""
    run = next((r for r in monitoring_workflow.RUN_HISTORY if r.run_id == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Monitoring run not found")
    return ApiResponse(data=run.model_dump(), meta=ResponseMeta())


@router.get("/catalog", response_model=ApiResponse)
async def search_satellite_catalog(
    source: SatelliteSource = Query(SatelliteSource.SENTINEL_2),
    bbox: Optional[str] = Query(
        None,
        description="Bounding box: minLon,minLat,maxLon,maxLat (WGS84)",
    ),
    limit: int = Query(10, ge=1, le=50),
):
    """Search satellite imagery catalog by source (Sentinel-1/2, Landsat 9, S2 night)."""
    try:
        scenes, catalog_source = await stac_catalog.search_scenes(
            source=source, bbox=bbox, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApiResponse(
        data={
            "source": source.value,
            "modality": scenes[0].modality.value if scenes else None,
            "scenes": [s.model_dump() for s in scenes],
            "count": len(scenes),
            "catalog": catalog_source,
        },
        meta=ResponseMeta(),
    )


@router.get("/sources", response_model=ApiResponse)
async def list_satellite_sources():
    """List supported satellite data sources and modalities."""
    return ApiResponse(
        data={
            "sources": [
                {
                    "id": SatelliteSource.SENTINEL_2.value,
                    "name": "Sentinel-2",
                    "modality": "optical",
                    "revisit_days": 5,
                    "use_cases": ["vegetation", "construction", "corridor_mapping"],
                },
                {
                    "id": SatelliteSource.SENTINEL_1.value,
                    "name": "Sentinel-1",
                    "modality": "sar",
                    "revisit_days": 6,
                    "use_cases": ["flooding", "landslide", "ground_deformation", "all-weather"],
                },
                {
                    "id": SatelliteSource.LANDSAT_9.value,
                    "name": "Landsat 9",
                    "modality": "optical+thermal",
                    "revisit_days": 16,
                    "use_cases": ["thermal_anomaly", "long_term_trends"],
                },
                {
                    "id": SatelliteSource.SENTINEL_2_NIGHT.value,
                    "name": "Sentinel-2 Night Campaign",
                    "modality": "thermal",
                    "revisit_days": "campaign",
                    "use_cases": ["night_thermal", "equipment_overheating"],
                },
            ]
        },
        meta=ResponseMeta(),
    )
