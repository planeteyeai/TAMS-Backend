"""Enterprise asset API — DB-backed with mock fallback."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services import asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


class EnterpriseAssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    asset_code: Optional[str] = None
    asset_type: str = "tower"
    type_code: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    status: str = "InService"
    criticality: str = "Medium"
    manufacturer: Optional[str] = None
    serial_number: Optional[str] = None
    voltage_level_kv: Optional[float] = None
    capacity_rating: Optional[float] = None
    parent_asset_id: Optional[str] = None
    metadata: Optional[dict] = None


class EnterpriseAssetUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    criticality: Optional[str] = None
    manufacturer: Optional[str] = None
    serial_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    metadata: Optional[dict] = None


class AckBody(BaseModel):
    notes: Optional[str] = None


def _wrap(data, pagination: Optional[PaginationMeta] = None) -> ApiResponse:
    return ApiResponse(data=data, meta=ResponseMeta(pagination=pagination))


@router.get("", response_model=ApiResponse)
async def list_assets(
    asset_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    criticality: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    state: Optional[str] = Query(None, description="Filter by Indian state e.g. Gujarat"),
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    include_towers: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=20000),
    session: AsyncSession = Depends(get_session),
):
    items, total = await asset_service.list_assets(
        session,
        asset_type=asset_type,
        category=category,
        status=status,
        criticality=criticality,
        search=search,
        state=state,
        bbox=bbox,
        include_towers=include_towers,
        page=page,
        page_size=page_size,
    )
    return _wrap(
        items,
        PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
    )


@router.get("/{asset_id}", response_model=ApiResponse)
async def get_asset(asset_id: str, session: AsyncSession = Depends(get_session)):
    asset = await asset_service.get_asset(session, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _wrap(asset)


@router.post("", response_model=ApiResponse, status_code=201)
async def create_asset(payload: EnterpriseAssetCreate, session: AsyncSession = Depends(get_session)):
    try:
        asset = await asset_service.create_asset_record(session, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _wrap(asset)


@router.put("/{asset_id}", response_model=ApiResponse)
async def update_asset(
    asset_id: str,
    payload: EnterpriseAssetUpdate,
    session: AsyncSession = Depends(get_session),
):
    asset = await asset_service.update_asset_record(
        session, asset_id, payload.model_dump(exclude_none=True)
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _wrap(asset)


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: str, session: AsyncSession = Depends(get_session)):
    ok = await asset_service.deactivate_asset(session, asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Asset not found")


@router.get("/{asset_id}/hierarchy", response_model=ApiResponse)
async def asset_hierarchy(asset_id: str, session: AsyncSession = Depends(get_session)):
    tree = await asset_service.get_hierarchy(session, asset_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _wrap(tree)


@router.get("/{asset_id}/qr", response_model=ApiResponse)
async def asset_qr(asset_id: str, session: AsyncSession = Depends(get_session)):
    asset = await asset_service.get_asset(session, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    code = asset.get("asset_code", asset["name"])
    return _wrap({"asset_id": asset_id, "qr_code_url": asset_service.generate_qr_url(code)})
