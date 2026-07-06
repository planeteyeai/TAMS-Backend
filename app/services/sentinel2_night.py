"""
Sentinel-2A Night-Time Acquisition Campaign integration.

Data sources (ESA TN ESA-EOPSM-S2A-TN-5021):
  - STAC: https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-night-time-acquisitions
  - S3:   s3://eodata/Sentinel-2/MSI/S2MSI_NIGHT/

Processing pipeline (for custom L1B reprocessing):
  1. Geolocation  — Sen2VM (https://github.com/sen2vm/sen2vm-core)
  2. Resampling   — GDAL gdalwarp (https://github.com/OSGeo/gdal)
  3. Calibration  — per-band gain/offset → radiance (W/m²/sr/µm)
  4. Merge        — rasterio detector merge

Reference notebooks: https://github.com/simonrp84/Sentinel2_Night_Processing
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.schemas.imagery import NightSceneSummary, ProcessingStep, ProcessingStepStatus

logger = logging.getLogger(__name__)

# ESA December 2025 campaign — representative scenes near transmission corridors
REFERENCE_SCENES: list[dict[str, Any]] = [
    {
        "scene_id": "S2A_GEO_L1_S20251211T055825",
        "datetime": "2025-12-11T05:58:25Z",
        "bbox": [-117.5, 32.4, -116.8, 33.2],
        "mode": "NOM",
        "scenario": "Anthropogenic lights",
        "notes": "San Diego, USA — transmission corridor monitoring reference",
    },
    {
        "scene_id": "S2A_GEO_L1_S20251205T190149",
        "datetime": "2025-12-05T19:01:49Z",
        "bbox": [43.0, 22.0, 50.0, 28.0],
        "mode": "NOM",
        "scenario": "Oil and gas facilities",
        "notes": "Saudi Arabia — gas flares / thermal anomaly detection",
    },
    {
        "scene_id": "S2A_GEO_L1_S20251203T200331",
        "datetime": "2025-12-03T20:03:31Z",
        "bbox": [30.0, 29.0, 33.0, 31.5],
        "mode": "NOM",
        "scenario": "Shipping",
        "notes": "Nile delta, Suez canal — corridor infrastructure",
    },
]

PROCESSING_PIPELINE: list[ProcessingStep] = [
    ProcessingStep(
        step=1,
        name="Geolocation",
        tool="Sen2VM",
        description="Compute per-pixel geolocation grids from L1B sensor geometry using DEM (Copernicus 30m).",
        reference="https://github.com/sen2vm/sen2vm-core",
    ),
    ProcessingStep(
        step=2,
        name="Resampling",
        tool="GDAL gdalwarp",
        description="Resample L1B detector imagery to fixed geographic grid (weighted average).",
        reference="https://github.com/OSGeo/gdal",
    ),
    ProcessingStep(
        step=3,
        name="Radiometric calibration",
        tool="Python (gain/offset)",
        description="Apply per-band calibration to produce radiance (W/m²/sr/µm).",
        reference="https://github.com/simonrp84/Sentinel2_Night_Processing",
    ),
    ProcessingStep(
        step=4,
        name="Detector merge",
        tool="rasterio",
        description="Merge per-detector images into one geolocated radiance image per band.",
        reference="https://github.com/simonrp84/Sentinel2_Night_Processing",
    ),
]


def _parse_bbox(bbox_str: Optional[str]) -> Optional[list[float]]:
    if not bbox_str:
        return None
    parts = [float(x.strip()) for x in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    return parts


def _feature_to_scene(feature: dict[str, Any]) -> NightSceneSummary:
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [[]])[0] if geom.get("type") == "Polygon" else []
    bbox = feature.get("bbox") or (list(props.get("bbox", [])) if props.get("bbox") else [])
    if not bbox and coords:
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        bbox = [min(lons), min(lats), max(lons), max(lats)]

    dt = props.get("datetime") or props.get("start_datetime") or props.get("end_datetime")
    assets = list(feature.get("assets", {}).keys())

    return NightSceneSummary(
        scene_id=feature.get("id", "unknown"),
        datetime=datetime.fromisoformat(dt.replace("Z", "+00:00")) if dt else datetime.utcnow(),
        bbox=bbox or [-180, -90, 180, 90],
        platform=props.get("platform", "sentinel-2a"),
        mode=props.get("s2:datatake_type") or props.get("processing:mode"),
        scenario=props.get("title"),
        stac_url=feature.get("links", [{}])[0].get("href") if feature.get("links") else None,
        s3_prefix=f"{settings.CDSE_S3_NIGHT_PREFIX}/{feature.get('id', '')}",
        product_types=assets,
        properties=props,
    )


async def search_night_scenes(
    bbox: Optional[str] = None,
    datetime_from: Optional[datetime] = None,
    datetime_to: Optional[datetime] = None,
    limit: int = 20,
) -> tuple[list[NightSceneSummary], str]:
    """
    Search CDSE STAC for Sentinel-2 night-time acquisitions.
    Falls back to reference catalog when STAC is unreachable.
    """
    if not settings.ENABLE_CDSE_STAC:
        return _filter_reference_scenes(bbox, limit), "reference"

    params: dict[str, Any] = {"limit": limit}
    parsed_bbox = _parse_bbox(bbox)
    if parsed_bbox:
        params["bbox"] = ",".join(str(v) for v in parsed_bbox)

    datetime_range = []
    if datetime_from:
        datetime_range.append(datetime_from.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if datetime_to:
        if not datetime_range:
            datetime_range.append("..")
        datetime_range.append(datetime_to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if datetime_range:
        params["datetime"] = "/".join(datetime_range)

    url = (
        f"{settings.CDSE_STAC_URL}/collections/"
        f"{settings.CDSE_NIGHT_COLLECTION}/items"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            scenes = [_feature_to_scene(f) for f in data.get("features", [])]
            if scenes:
                return scenes, "cdse_stac"
    except Exception as exc:
        logger.warning("CDSE STAC search failed, using reference catalog: %s", exc)

    return _filter_reference_scenes(bbox, limit), "reference"


def _filter_reference_scenes(bbox: Optional[str], limit: int) -> list[NightSceneSummary]:
    parsed = _parse_bbox(bbox)
    scenes: list[NightSceneSummary] = []
    for ref in REFERENCE_SCENES[:limit]:
        if parsed:
            min_lon, min_lat, max_lon, max_lat = parsed
            sb = ref["bbox"]
            if sb[2] < min_lon or sb[0] > max_lon or sb[3] < min_lat or sb[1] > max_lat:
                continue
        scenes.append(
            NightSceneSummary(
                scene_id=ref["scene_id"],
                datetime=datetime.fromisoformat(ref["datetime"].replace("Z", "+00:00")),
                bbox=ref["bbox"],
                platform="sentinel-2a",
                mode=ref.get("mode"),
                scenario=ref.get("scenario"),
                stac_url=(
                    f"{settings.CDSE_STAC_URL}/collections/"
                    f"{settings.CDSE_NIGHT_COLLECTION}/items/{ref['scene_id']}"
                ),
                s3_prefix=f"{settings.CDSE_S3_NIGHT_PREFIX}/{ref['scene_id']}",
                product_types=["orthorectified-product"],
                properties={"notes": ref.get("notes", "")},
            )
        )
    return scenes


def get_processing_pipeline() -> list[ProcessingStep]:
    """Return ESA reprocessing pipeline steps with TAMS integration status."""
    return PROCESSING_PIPELINE


def get_data_access_info() -> dict[str, Any]:
    """Return CDSE data access endpoints and requirements."""
    return {
        "stac_catalog": (
            f"{settings.CDSE_STAC_URL}/collections/{settings.CDSE_NIGHT_COLLECTION}"
        ),
        "s3_bucket": settings.CDSE_S3_BUCKET,
        "s3_night_prefix": settings.CDSE_S3_NIGHT_PREFIX,
        "s3_docs": "https://documentation.dataspace.copernicus.eu/APIs/S3.html",
        "expert_l1b_access": "L1B requires CDSE expert user registration",
        "reprocessed_products": "Orthorectified radiance GeoTIFF per band (not L1C tile grid)",
        "campaign_period": "2025-12-03 to 2025-12-22",
        "esa_technical_note": "ESA-EOPSM-S2A-TN-5021",
        "processing_repos": {
            "sen2vm": "https://github.com/sen2vm/sen2vm-core",
            "gdal": "https://github.com/OSGeo/gdal",
            "night_processing": "https://github.com/simonrp84/Sentinel2_Night_Processing",
        },
    }
