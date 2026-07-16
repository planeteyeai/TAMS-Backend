"""GIS feature service."""

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker
from app.db.init_db import is_db_ready
from app.models import Asset, AssetType
from app.services.asset_service import list_assets
from app.services.kml_loader import (
    get_all_place_stats,
    get_region_stats,
    get_stats_for_place,
    get_towers_in_bbox,
)


async def get_features(
    session: AsyncSession | None,
    *,
    layer: str | None = None,
    bbox: str | None = None,
    asset_type: str | None = None,
    state: str | None = None,
) -> dict:
    page_size = 15000 if not is_db_ready() else 5000
    items, _total = await list_assets(
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
        "source": "database" if is_db_ready() and session is not None else "indian_KML",
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

    if is_db_ready():
        async with async_session_maker() as session:
            # Single round-trip: join asset_types instead of separate type_id lookup.
            map_meta = func.jsonb_build_object(
                "country_or_state",
                Asset.metadata_["country_or_state"],
                "region",
                Asset.metadata_["region"],
                "voltage_kv",
                Asset.metadata_["voltage_kv"],
            )
            stmt = (
                select(
                    Asset.asset_id,
                    Asset.name,
                    Asset.latitude,
                    Asset.longitude,
                    map_meta,
                )
                .join(AssetType, Asset.asset_type_id == AssetType.asset_type_id)
                .where(
                    AssetType.type_code == "TOWER",
                    Asset.is_active.is_(True),
                    Asset.latitude >= min_lat,
                    Asset.latitude <= max_lat,
                    Asset.longitude >= min_lon,
                    Asset.longitude <= max_lon,
                )
                .limit(limit)
            )
            if state and state.lower() not in ("gujarat", "india"):
                stmt = stmt.where(Asset.metadata_["country_or_state"].astext.ilike(state))

            rows = (await session.execute(stmt)).all()
            features = [
                {
                    "type": "Feature",
                    "id": str(asset_id),
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat],
                    },
                    "properties": {
                        "asset_id": str(asset_id),
                        "name": name,
                        "asset_type": "tower",
                        "metadata": meta or {},
                    },
                }
                for asset_id, name, lat, lon, meta in rows
            ]
            return {
                "type": "FeatureCollection",
                "features": features,
                "total": len(features),
                "source": "database",
            }

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

    async with async_session_maker() as session:
        # If import still empty, fall back to KML stats
        total = await session.scalar(select(func.count()).select_from(Asset).where(Asset.is_active.is_(True))) or 0
        if total == 0:
            if place_id:
                return get_stats_for_place(place_id)
            return get_region_stats(state=state)

        type_counts = (
            await session.execute(
                select(AssetType.type_code, func.count())
                .join(Asset, Asset.asset_type_id == AssetType.asset_type_id)
                .where(Asset.is_active.is_(True))
                .group_by(AssetType.type_code)
            )
        ).all()
        by_type = {code: int(n) for code, n in type_counts}

        line_km = await session.scalar(
            select(
                func.coalesce(
                    func.sum(cast(Asset.metadata_["length_km"].astext, Float)),
                    0,
                )
            )
            .select_from(Asset)
            .join(AssetType)
            .where(Asset.is_active.is_(True), AssetType.type_code == "LINE")
        )

        return {
            "towers": by_type.get("TOWER", 0),
            "lines": by_type.get("LINE", 0),
            "substations": by_type.get("SUBSTATION", 0),
            "total": int(total),
            "line_km": round(float(line_km or 0), 1),
            "source": "database",
        }


async def get_places_asset_stats() -> dict[str, dict]:
    if not is_db_ready():
        return get_all_place_stats()
    # Prefer DB India/Gujarat totals; keep KML place breakdown for UX until fully mapped
    india = await get_region_asset_stats()
    return {
        "india": {"total": india.get("total", 0), **india},
        "gujarat": {"total": india.get("total", 0), **india},
    }
