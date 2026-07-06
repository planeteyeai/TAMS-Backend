"""Sentinel-2 night imagery catalog and processing API."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.imagery import ImageryProductType
from app.schemas.response import ApiResponse, ResponseMeta
from app.services import sentinel2_night

router = APIRouter(prefix="/imagery", tags=["imagery"])


@router.get("/night/catalog", response_model=ApiResponse)
async def search_night_imagery(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box: minLon,minLat,maxLon,maxLat (WGS84)",
        examples=["-117.5,32.4,-116.8,33.2"],
    ),
    datetime_from: Optional[datetime] = Query(None),
    datetime_to: Optional[datetime] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Search Sentinel-2A night-time acquisition campaign scenes.

    Queries CDSE STAC (`sentinel-2-night-time-acquisitions`) with fallback
    to reference scenes from ESA TN ESA-EOPSM-S2A-TN-5021.
    """
    try:
        scenes, source = await sentinel2_night.search_night_scenes(
            bbox=bbox,
            datetime_from=datetime_from,
            datetime_to=datetime_to,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApiResponse(
        data={
            "scenes": [s.model_dump() for s in scenes],
            "count": len(scenes),
            "source": source,
        },
        meta=ResponseMeta(),
    )


@router.get("/night/access", response_model=ApiResponse)
async def night_data_access():
    """CDSE S3/STAC access information for Sentinel-2 night data."""
    return ApiResponse(
        data=sentinel2_night.get_data_access_info(),
        meta=ResponseMeta(),
    )


@router.get("/night/pipeline", response_model=ApiResponse)
async def night_processing_pipeline():
    """
    ESA L1B → orthorectified radiance processing pipeline.

    Steps map to Sen2VM, GDAL, and Sentinel2_Night_Processing notebooks.
    """
    pipeline = sentinel2_night.get_processing_pipeline()
    return ApiResponse(
        data={
            "pipeline": [step.model_dump() for step in pipeline],
            "tams_status": "catalog_only",
            "note": (
                "TAMS currently catalogs night scenes. Full L1B reprocessing "
                "requires Sen2VM (Java 8 + GDAL 3.6.2) or pre-processed "
                "orthorectified products from CDSE S3."
            ),
        },
        meta=ResponseMeta(),
    )


@router.get("/night/products", response_model=ApiResponse)
async def night_product_types():
    """Available Sentinel-2 night product types per ESA data description."""
    return ApiResponse(
        data={
            "products": [
                {
                    "type": ImageryProductType.ORTHORECTIFIED.value,
                    "description": "ESA reprocessed orthorectified radiance GeoTIFF per band",
                    "stac_asset": "orthorectified-product",
                    "s3_path": "s3://eodata/Sentinel-2/MSI/S2MSI_NIGHT/",
                    "units": "W/m2/sr/um",
                    "available": True,
                },
                {
                    "type": ImageryProductType.SENSOR_GEOMETRY.value,
                    "description": "Sensor geometry product (L1B-based)",
                    "stac_asset": "senson-geometry-product",
                    "available": True,
                },
                {
                    "type": ImageryProductType.L1B_RAW.value,
                    "description": "Original L1B — expert users only, 14-day online retention",
                    "available": False,
                    "requires": "CDSE expert user registration",
                },
            ],
            "modes": {
                "NOM": "Full swath, all bands (12 detectors per band)",
                "RAW": "Partial swath, compression disabled (4 detectors per band)",
            },
        },
        meta=ResponseMeta(),
    )
