"""GIS API."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, ResponseMeta
from app.services import gis_service

router = APIRouter(prefix="/gis", tags=["gis"])


class ProximityRequest(BaseModel):
    center_lat: float
    center_lon: float
    radius_km: float = 5.0
    asset_types: Optional[list[str]] = None


@router.get("/layers", response_model=ApiResponse)
async def gis_layers():
    return ApiResponse(
        data={
            "layers": [
                {"id": "lines", "name": "Transmission Lines", "geometry": "LineString"},
                {"id": "towers", "name": "Towers", "geometry": "Point"},
                {"id": "substations", "name": "Substations", "geometry": "Point/Polygon"},
                {"id": "faults", "name": "Fault Locations", "geometry": "Point"},
                {"id": "alarms", "name": "Active Alarms", "geometry": "Point"},
            ],
            "basemaps": ["ArcGIS Satellite", "OpenStreetMap", "Google Maps"],
        },
        meta=ResponseMeta(),
    )


@router.get("/features", response_model=ApiResponse)
async def gis_features(
    layer: Optional[str] = Query(None),
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    asset_type: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    data = await gis_service.get_features(
        session, layer=layer, bbox=bbox, asset_type=asset_type, state=state
    )
    return ApiResponse(data=data, meta=ResponseMeta())


@router.get("/towers", response_model=ApiResponse)
async def gis_towers(
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    state: Optional[str] = Query(None),
    limit: int = Query(5000, ge=1, le=10000),
):
    try:
        data = await gis_service.get_viewport_towers(bbox=bbox, state=state, limit=limit)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=data, meta=ResponseMeta())


@router.get("/stats", response_model=ApiResponse)
async def gis_stats(
    place_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
):
    try:
        data = await gis_service.get_region_asset_stats(
            place_id=place_id, state=state, bbox=bbox
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=data, meta=ResponseMeta())


@router.get("/stats/places", response_model=ApiResponse)
async def gis_places_stats():
    data = await gis_service.get_places_asset_stats()
    return ApiResponse(data=data, meta=ResponseMeta())


@router.post("/analytics/proximity", response_model=ApiResponse)
async def proximity(body: ProximityRequest, session: AsyncSession = Depends(get_session)):
    data = await gis_service.proximity_analysis(
        session,
        center_lat=body.center_lat,
        center_lon=body.center_lon,
        radius_km=body.radius_km,
        asset_types=body.asset_types,
    )
    return ApiResponse(data=data, meta=ResponseMeta())
