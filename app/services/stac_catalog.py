"""
Unified STAC catalog for multi-source satellite imagery.

Supports Sentinel-1 (SAR), Sentinel-2 (optical), Landsat 9 (optical/thermal),
and Sentinel-2 night campaign via CDSE STAC with reference fallbacks.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.schemas.monitoring import ImageryModality, SatelliteSource, SceneSummary

logger = logging.getLogger(__name__)

COLLECTION_MAP: dict[SatelliteSource, dict[str, str]] = {
    SatelliteSource.SENTINEL_1: {
        "collection": "sentinel-1-grd",
        "modality": ImageryModality.SAR.value,
    },
    SatelliteSource.SENTINEL_2: {
        "collection": "sentinel-2-l2a",
        "modality": ImageryModality.OPTICAL.value,
    },
    SatelliteSource.LANDSAT_9: {
        "collection": "landsat-c2-l2",
        "modality": ImageryModality.OPTICAL.value,
    },
    SatelliteSource.SENTINEL_2_NIGHT: {
        "collection": settings.CDSE_NIGHT_COLLECTION,
        "modality": ImageryModality.THERMAL.value,
    },
}

REFERENCE_SCENES: dict[SatelliteSource, list[dict[str, Any]]] = {
    SatelliteSource.SENTINEL_2: [
        {
            "scene_id": "S2A_MSIL2A_20250601T165921",
            "datetime": "2025-06-01T16:59:21Z",
            "bbox": [-97.9, 29.5, -95.0, 33.0],
            "cloud_cover": 8.2,
            "notes": "Texas transmission corridor — optical baseline",
        },
        {
            "scene_id": "S2A_MSIL2A_20250605T165921",
            "datetime": "2025-06-05T16:59:21Z",
            "bbox": [-105.2, 39.4, -104.5, 40.1],
            "cloud_cover": 5.1,
            "notes": "Denver corridor — vegetation monitoring",
        },
    ],
    SatelliteSource.SENTINEL_1: [
        {
            "scene_id": "S1A_IW_GRDH_20250602T120000",
            "datetime": "2025-06-02T12:00:00Z",
            "bbox": [-97.9, 29.5, -95.0, 33.0],
            "cloud_cover": 0.0,
            "notes": "Texas corridor SAR — flood/change detection",
        },
    ],
    SatelliteSource.LANDSAT_9: [
        {
            "scene_id": "LC09_L2SP_029039_20250603",
            "datetime": "2025-06-03T17:12:00Z",
            "bbox": [-97.9, 29.5, -95.0, 33.0],
            "cloud_cover": 12.0,
            "notes": "Landsat 9 OLI/TIRS — thermal + optical",
        },
    ],
}


def _parse_bbox(bbox_str: Optional[str]) -> Optional[list[float]]:
    if not bbox_str:
        return None
    parts = [float(x.strip()) for x in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    return parts


def _bbox_intersects(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _feature_to_scene(feature: dict[str, Any], source: SatelliteSource) -> SceneSummary:
    props = feature.get("properties", {})
    meta = COLLECTION_MAP[source]
    bbox = feature.get("bbox") or list(props.get("bbox", []))
    if not bbox:
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [[]])[0] if geom.get("type") == "Polygon" else []
        if coords:
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            bbox = [min(lons), min(lats), max(lons), max(lats)]

    dt = props.get("datetime") or props.get("start_datetime") or props.get("end_datetime")
    cloud = props.get("eo:cloud_cover") or props.get("cloud_cover")

    return SceneSummary(
        scene_id=feature.get("id", "unknown"),
        source=source,
        modality=ImageryModality(meta["modality"]),
        datetime=datetime.fromisoformat(dt.replace("Z", "+00:00")) if dt else datetime.utcnow(),
        bbox=bbox or [-180, -90, 180, 90],
        cloud_cover=float(cloud) if cloud is not None else None,
        collection=meta["collection"],
        stac_url=next(
            (link.get("href") for link in feature.get("links", []) if link.get("rel") == "self"),
            None,
        ),
        properties=props,
    )


def _reference_scenes(
    source: SatelliteSource,
    bbox: Optional[str],
    limit: int,
) -> list[SceneSummary]:
    parsed = _parse_bbox(bbox)
    meta = COLLECTION_MAP[source]
    scenes: list[SceneSummary] = []
    for ref in REFERENCE_SCENES.get(source, [])[:limit]:
        if parsed and not _bbox_intersects(parsed, ref["bbox"]):
            continue
        scenes.append(
            SceneSummary(
                scene_id=ref["scene_id"],
                source=source,
                modality=ImageryModality(meta["modality"]),
                datetime=datetime.fromisoformat(ref["datetime"].replace("Z", "+00:00")),
                bbox=ref["bbox"],
                cloud_cover=ref.get("cloud_cover"),
                collection=meta["collection"],
                stac_url=f"{settings.CDSE_STAC_URL}/collections/{meta['collection']}/items/{ref['scene_id']}",
                properties={"notes": ref.get("notes", "")},
            )
        )
    return scenes


async def search_scenes(
    source: SatelliteSource,
    bbox: Optional[str] = None,
    datetime_from: Optional[datetime] = None,
    datetime_to: Optional[datetime] = None,
    limit: int = 10,
) -> tuple[list[SceneSummary], str]:
    """Search STAC for scenes; fall back to reference catalog on failure."""
    if source == SatelliteSource.SENTINEL_2_NIGHT:
        from app.services import sentinel2_night

        night_scenes, src = await sentinel2_night.search_night_scenes(
            bbox=bbox, datetime_from=datetime_from, datetime_to=datetime_to, limit=limit
        )
        return [
            SceneSummary(
                scene_id=s.scene_id,
                source=SatelliteSource.SENTINEL_2_NIGHT,
                modality=ImageryModality.THERMAL,
                datetime=s.datetime,
                bbox=s.bbox,
                cloud_cover=None,
                collection=settings.CDSE_NIGHT_COLLECTION,
                stac_url=s.stac_url,
                properties=s.properties,
            )
            for s in night_scenes
        ], src

    if not settings.ENABLE_CDSE_STAC:
        return _reference_scenes(source, bbox, limit), "reference"

    meta = COLLECTION_MAP[source]
    params: dict[str, Any] = {"limit": limit}
    parsed_bbox = _parse_bbox(bbox)
    if parsed_bbox:
        params["bbox"] = ",".join(str(v) for v in parsed_bbox)

    datetime_range: list[str] = []
    if datetime_from:
        datetime_range.append(datetime_from.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if datetime_to:
        if not datetime_range:
            datetime_range.append("..")
        datetime_range.append(datetime_to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if datetime_range:
        params["datetime"] = "/".join(datetime_range)

    url = f"{settings.CDSE_STAC_URL}/collections/{meta['collection']}/items"

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            features = response.json().get("features", [])
            if features:
                return [_feature_to_scene(f, source) for f in features], "cdse_stac"
    except Exception as exc:
        logger.warning("STAC search failed for %s: %s", source.value, exc)

    return _reference_scenes(source, bbox, limit), "reference"


def asset_bbox(assets: list[dict[str, Any]], padding: float = 0.5) -> str:
    """Build a bounding box around asset coordinates with padding (degrees)."""
    lats = [a["latitude"] for a in assets]
    lons = [a["longitude"] for a in assets]
    return f"{min(lons) - padding},{min(lats) - padding},{max(lons) + padding},{max(lats) + padding}"


def scenes_for_assets(
    scenes: list[SceneSummary],
    assets: list[dict[str, Any]],
) -> list[SceneSummary]:
    """Filter scenes that intersect any asset location."""
    if not assets:
        return scenes
    matched: list[SceneSummary] = []
    for scene in scenes:
        sb = scene.bbox
        for asset in assets:
            point_bbox = [
                asset["longitude"] - 0.05,
                asset["latitude"] - 0.05,
                asset["longitude"] + 0.05,
                asset["latitude"] + 0.05,
            ]
            if _bbox_intersects(sb, point_bbox):
                matched.append(scene)
                break
    return matched or scenes[:1]
