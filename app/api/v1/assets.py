"""Asset management API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.asset import AssetCreate, AssetResponse, AssetTypeEnum
from app.schemas.response import ApiResponse, PaginationMeta, ResponseMeta
from app.services.mock_data import MOCK_ASSETS, create_asset

router = APIRouter(prefix="/assets", tags=["assets"])


def _wrap(data, pagination: Optional[PaginationMeta] = None) -> ApiResponse:
    return ApiResponse(
        data=data,
        meta=ResponseMeta(pagination=pagination),
    )


@router.get("", response_model=ApiResponse)
async def list_assets(
    asset_type: Optional[AssetTypeEnum] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    """List transmission assets with optional filtering."""
    items = MOCK_ASSETS
    if asset_type:
        items = [a for a in items if a["asset_type"] == asset_type.value]

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = items[start:end]

    return _wrap(
        paginated,
        PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
    )


@router.get("/{asset_id}", response_model=ApiResponse)
async def get_asset(asset_id: str):
    """Get a single asset by ID."""
    asset = next((a for a in MOCK_ASSETS if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _wrap(asset)


@router.post("", response_model=ApiResponse, status_code=201)
async def create_asset_endpoint(payload: AssetCreate):
    """Create a new asset."""
    asset = create_asset(payload.model_dump())
    return _wrap(AssetResponse(**asset))
