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
    sync: bool = Query(
        False,
        description="Run detect/corridor sync before returning (slow; off by default)",
    ),
):
    try:
        data = await gis_service.get_viewport_towers(
            bbox=bbox, state=state, limit=limit, sync=sync
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=data, meta=ResponseMeta())


@router.get("/corridor/walk", response_model=ApiResponse)
async def gis_corridor_walk(
    lat: float = Query(..., description="Seed tower latitude"),
    lon: float = Query(..., description="Seed tower longitude"),
    persist: bool = Query(False, description="Upsert walked corridor into the database"),
):
    """
    From a detected tower position, follow connected lines until substations
    or dead-end endpoints. Multi-line junction towers expose adjacent towers
    per line.
    """
    from app.services.corridor_graph import walk_corridor_from_tower
    from app.services.kml_db_import import upsert_corridors_from_seed_towers

    seed = {
        "id": f"seed-{lon:.5f}-{lat:.5f}",
        "name": "Detected tower",
        "latitude": lat,
        "longitude": lon,
        "asset_type": "tower",
        "metadata": {},
    }
    walk = walk_corridor_from_tower(seed)
    payload: dict = {
        "walk": {
            "seed_tower_id": walk.get("seed_tower_id"),
            "stats": walk.get("stats"),
            "endpoints": walk.get("endpoints"),
            "junction_tower_ids": walk.get("junction_tower_ids"),
            "adjacencies": walk.get("adjacencies"),
            "lines_at_tower": walk.get("lines_at_tower"),
            "tower_count": len(walk.get("towers") or []),
            "line_count": len(walk.get("lines") or []),
            "substation_count": len(walk.get("substations") or []),
        }
    }
    if persist:
        payload["persist"] = await upsert_corridors_from_seed_towers([seed], max_seeds=1)
    return ApiResponse(data=payload, meta=ResponseMeta())


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
