"""GIS feature service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import asset_to_dict, is_db_ready
from app.models import Asset
from app.services.asset_service import list_assets
from app.services.kml_loader import get_towers_in_bbox, get_region_stats, get_stats_for_place, get_all_place_stats


async def get_features(
    session: AsyncSession | None,
    *,
    layer: str | None = None,
    bbox: str | None = None,
    asset_type: str | None = None,
    state: str | None = None,
) -> dict:
    page_size = 15000 if not is_db_ready() else 2000
    items, total = await list_assets(
        session, asset_type=asset_type, state=state, bbox=bbox, page=1, page_size=page_size
    )

    features = []
    for a in items:
        if layer == "lines" and a.get("asset_type") != "line":
            continue
        if layer == "towers" and a.get("asset_type") != "tower":
            continue
        if layer == "substations" and a.get("asset_type") != "substation":
            continue

        geom = a.get("geometry")
        if not geom and a.get("latitude") is not None:
            geom = {"type": "Point", "coordinates": [a["longitude"], a["latitude"]]}

        features.append(
            {
                "type": "Feature",
                "id": a["id"],
                "geometry": geom,
                "properties": {
                    "asset_id": a["id"],
                    "asset_code": a.get("asset_code", a["name"]),
                    "name": a["name"],
                    "asset_type": a["asset_type"],
                    "status": a.get("status"),
                    "criticality": a.get("criticality"),
                    "health_score": a.get("health_score"),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
        "layers": ["lines", "towers", "substations", "all"],
    }


async def proximity_analysis(
    session: AsyncSession | None,
    *,
    center_lat: float,
    center_lon: float,
    radius_km: float = 5.0,
    asset_types: list[str] | None = None,
) -> dict:
    items, _ = await list_assets(session, page=1, page_size=2000)
    results = []

    for a in items:
        lat, lon = a.get("latitude"), a.get("longitude")
        if lat is None or lon is None:
            continue
        if asset_types and a.get("asset_type") not in asset_types:
            continue
        # Haversine approximation
        dlat = (lat - center_lat) * 111.0
        dlon = (lon - center_lon) * 111.0 * max(0.1, abs(center_lat))
        dist_km = (dlat**2 + dlon**2) ** 0.5
        if dist_km <= radius_km:
            results.append({**a, "distance_km": round(dist_km, 2)})

    results.sort(key=lambda x: x["distance_km"])
    return {
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_km": radius_km,
        "count": len(results),
        "assets": results,
    }


async def get_viewport_towers(
    *,
    bbox: str,
    state: str | None = None,
    limit: int = 5000,
) -> dict:
    try:
        min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox.split(",")]
    except (ValueError, TypeError) as exc:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat") from exc

    towers = get_towers_in_bbox(
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        state=state,
        limit=limit,
    )
    features = []
    for t in towers:
        features.append(
            {
                "type": "Feature",
                "id": t["id"],
                "geometry": {"type": "Point", "coordinates": [t["longitude"], t["latitude"]]},
                "properties": {
                    "asset_id": t["id"],
                    "name": t["name"],
                    "asset_type": "tower",
                    "health_score": t.get("health_score"),
                    "metadata": t.get("metadata", {}),
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
        "source": "indian_KML/Towers_KML",
    }


async def get_region_asset_stats(
    *,
    place_id: str | None = None,
    state: str | None = None,
    bbox: str | None = None,
) -> dict:
    if not is_db_ready():
        if place_id:
            return get_stats_for_place(place_id)
        if bbox:
            try:
                min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox.split(",")]
                box = (min_lat, min_lon, max_lat, max_lon)
                return get_region_stats(bbox=box)
            except ValueError as exc:
                raise ValueError("bbox must be minLon,minLat,maxLon,maxLat") from exc
        return get_region_stats(state=state)

    _, total = await list_assets(None, page=1, page_size=1)
    items, _ = await list_assets(None, page=1, page_size=10000)
    return {
        "towers": sum(1 for a in items if a.get("asset_type") == "tower"),
        "lines": sum(1 for a in items if a.get("asset_type") == "line"),
        "substations": sum(1 for a in items if a.get("asset_type") == "substation"),
        "total": total,
        "line_km": round(
            sum(float(a.get("metadata", {}).get("length_km") or 0) for a in items if a.get("asset_type") == "line"),
            1,
        ),
        "source": "database",
    }


async def get_places_asset_stats() -> dict[str, dict]:
    if not is_db_ready():
        return get_all_place_stats()
    return {}
