"""Geotechnical investigation API — enter/edit field data + generate reports."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services import geotech_service

router = APIRouter(prefix="/geotech", tags=["geotech"])


class SoilLayer(BaseModel):
    depth_from_m: float = 0
    depth_to_m: float = 0.5
    gravel_pct: Optional[float] = None
    sand_pct: Optional[float] = None
    silt_pct: Optional[float] = None
    clay_pct: Optional[float] = None
    ll: Optional[float] = None
    pl: Optional[float] = None
    pi: Optional[float] = None
    soil_class: Optional[str] = None
    mdd: Optional[float] = None
    omc: Optional[float] = None
    dry_density: Optional[float] = None
    fsi: Optional[float] = None
    bulk_density: Optional[float] = None
    ucs: Optional[float] = None
    sg: Optional[float] = None
    sbc: Optional[float] = None
    cbr: Optional[float] = None
    remarks: Optional[str] = None


class GeotechCreate(BaseModel):
    site_code: str = Field(..., min_length=1, max_length=50)
    site_name: str = Field(..., min_length=1, max_length=255)
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    purpose: Optional[str] = None
    region: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    investigation_depth_m: float = Field(2.0, gt=0, le=50)
    groundwater_note: Optional[str] = None
    soil_layers: Optional[list[dict[str, Any]]] = None
    design_params: Optional[dict[str, Any]] = None
    sbc_by_depth: Optional[list[dict[str, Any]]] = None
    pile_capacities: Optional[list[dict[str, Any]]] = None
    cbr_by_depth: Optional[list[dict[str, Any]]] = None
    resistivity: Optional[dict[str, Any]] = None
    recommendations: Optional[dict[str, Any]] = None
    remarks: Optional[str] = None


class GeotechUpdate(BaseModel):
    site_code: Optional[str] = Field(None, min_length=1, max_length=50)
    site_name: Optional[str] = Field(None, min_length=1, max_length=255)
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    purpose: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    investigation_depth_m: Optional[float] = Field(None, gt=0, le=50)
    groundwater_note: Optional[str] = None
    soil_layers: Optional[list[dict[str, Any]]] = None
    design_params: Optional[dict[str, Any]] = None
    sbc_by_depth: Optional[list[dict[str, Any]]] = None
    pile_capacities: Optional[list[dict[str, Any]]] = None
    cbr_by_depth: Optional[list[dict[str, Any]]] = None
    resistivity: Optional[dict[str, Any]] = None
    recommendations: Optional[dict[str, Any]] = None
    remarks: Optional[str] = None


@router.get("", response_model=ApiResponse)
async def list_geotech(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    await geotech_service.ensure_nirona_seed(session)
    items, total = await geotech_service.list_investigations(
        session, page=page, page_size=page_size, q=q
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


@router.get("/nearest", response_model=ApiResponse)
async def nearest_geotech(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    max_km: float = Query(5.0, gt=0, le=50),
    session: AsyncSession = Depends(get_session),
):
    """Lookup nearest field investigation for tower suitability wiring."""
    await geotech_service.ensure_nirona_seed(session)
    hit = await geotech_service.nearest_investigation(session, lat=lat, lon=lon, max_km=max_km)
    return ApiResponse(
        data=hit,
        meta=ResponseMeta(),
        errors=None if hit else ["No geotech investigation within search radius"],
    )


@router.get("/{geotech_id}", response_model=ApiResponse)
async def get_geotech(geotech_id: str, session: AsyncSession = Depends(get_session)):
    item = await geotech_service.get_investigation(session, geotech_id)
    if not item:
        raise HTTPException(status_code=404, detail="Geotech investigation not found")
    return ApiResponse(data=item, meta=ResponseMeta())


@router.get("/{geotech_id}/report", response_class=HTMLResponse)
async def geotech_report(geotech_id: str, session: AsyncSession = Depends(get_session)):
    item = await geotech_service.get_investigation(session, geotech_id)
    if not item:
        raise HTTPException(status_code=404, detail="Geotech investigation not found")
    return HTMLResponse(content=geotech_service.build_report_html(item))


@router.post("", response_model=ApiResponse, status_code=201)
async def create_geotech(payload: GeotechCreate, session: AsyncSession = Depends(get_session)):
    row = await geotech_service.create_investigation(session, payload.model_dump())
    return ApiResponse(data=row, meta=ResponseMeta())


@router.put("/{geotech_id}", response_model=ApiResponse)
async def update_geotech(
    geotech_id: str, payload: GeotechUpdate, session: AsyncSession = Depends(get_session)
):
    row = await geotech_service.update_investigation(
        session, geotech_id, payload.model_dump(exclude_unset=True)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Geotech investigation not found")
    return ApiResponse(data=row, meta=ResponseMeta())


@router.delete("/{geotech_id}", response_model=ApiResponse)
async def delete_geotech(geotech_id: str, session: AsyncSession = Depends(get_session)):
    ok = await geotech_service.delete_investigation(session, geotech_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Geotech investigation not found")
    return ApiResponse(data={"deleted": True, "id": geotech_id}, meta=ResponseMeta())
