"""Asset business logic with DB + mock fallback."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import asset_to_dict, is_db_ready
from app.models import Asset, AssetType, HealthScore
from app.services.mock_data import MOCK_ASSETS, create_asset as mock_create_asset

# In-process cache for the map corridor catalog (lines + substations).
# Avoids re-pulling ~10k geometries from Railway on every page load.
_corridor_cache: list[dict] | None = None
_corridor_cache_key: str | None = None


def _invalidate_corridor_cache() -> None:
    global _corridor_cache, _corridor_cache_key
    _corridor_cache = None
    _corridor_cache_key = None


async def _latest_health(session: AsyncSession, asset_id: UUID) -> HealthScore | None:
    stmt = (
        select(HealthScore)
        .where(HealthScore.asset_id == asset_id)
        .order_by(HealthScore.computed_at.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def _latest_health_map(
    session: AsyncSession, asset_ids: list[UUID]
) -> dict[UUID, HealthScore]:
    """One query for latest health scores (avoids N+1 over remote Postgres)."""
    if not asset_ids:
        return {}
    stmt = (
        select(HealthScore)
        .where(HealthScore.asset_id.in_(asset_ids))
        .distinct(HealthScore.asset_id)
        .order_by(HealthScore.asset_id, HealthScore.computed_at.desc())
    )
    rows = (await session.scalars(stmt)).all()
    return {row.asset_id: row for row in rows}


async def list_assets(
    session: AsyncSession | None,
    *,
    asset_type: str | None = None,
    category: str | None = None,
    status: str | None = None,
    criticality: str | None = None,
    search: str | None = None,
    state: str | None = None,
    bbox: str | None = None,
    include_towers: bool = False,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[dict], int]:
    bbox_tuple: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            bbox_tuple = tuple(float(v) for v in bbox.split(","))  # type: ignore[assignment]
        except ValueError:
            bbox_tuple = None

    if not is_db_ready() or session is None:
        from app.services.kml_loader import list_kml_assets

        return list_kml_assets(
            asset_type=asset_type,
            state=state,
            bbox=bbox_tuple,
            search=search,
            include_towers=include_towers,
            page=page,
            page_size=page_size,
        )

    # Empty Railway DB (schema only) → serve Gujarat KML for the map
    has_any = await session.scalar(select(Asset.asset_id).where(Asset.is_active.is_(True)).limit(1))
    if not has_any:
        from app.services.kml_loader import list_kml_assets

        return list_kml_assets(
            asset_type=asset_type,
            state=state,
            bbox=bbox_tuple,
            search=search,
            include_towers=include_towers,
            page=page,
            page_size=page_size,
        )

    # Map/catalog pages: light column select (avoid ORM + count overhead)
    if page_size > 50 and not search and not status and not criticality:
        cacheable = (
            not include_towers
            and not asset_type
            and not category
            and not bbox_tuple
            and bool(state)
            and state.lower() != "india"
        )
        global _corridor_cache, _corridor_cache_key
        cache_key = f"corridor:{state or 'all'}"
        if cacheable and _corridor_cache is not None and _corridor_cache_key == cache_key:
            start = (page - 1) * page_size
            chunk = _corridor_cache[start : start + page_size]
            return chunk, len(_corridor_cache)

        items, total = await _list_assets_light(
            session,
            asset_type=asset_type,
            category=category,
            state=state,
            bbox_tuple=bbox_tuple,
            include_towers=include_towers,
            page=page,
            page_size=page_size,
        )
        if cacheable and page == 1 and len(items) < page_size:
            _corridor_cache = items
            _corridor_cache_key = cache_key
        elif cacheable and page == 1 and len(items) == page_size:
            # Full page returned — store this page; total may be higher but good enough for map
            _corridor_cache = items
            _corridor_cache_key = cache_key
        return items, total

    stmt = (
        select(Asset)
        .options(selectinload(Asset.asset_type), selectinload(Asset.substation))
        .where(Asset.is_active.is_(True))
    )
    count_stmt = select(func.count()).select_from(Asset).where(Asset.is_active.is_(True))

    if asset_type:
        legacy_map = {"tower": "TOWER", "line": "LINE", "substation": "SUBSTATION"}
        code = legacy_map.get(asset_type, asset_type.upper())
        stmt = stmt.join(AssetType).where(AssetType.type_code == code)
        count_stmt = count_stmt.join(AssetType).where(AssetType.type_code == code)
    elif category:
        stmt = stmt.join(AssetType).where(AssetType.category == category)
        count_stmt = count_stmt.join(AssetType).where(AssetType.category == category)
    elif not include_towers:
        # Match KML path: towers come from /gis/towers bbox, not the catalog page
        stmt = stmt.join(AssetType).where(AssetType.type_code != "TOWER")
        count_stmt = count_stmt.join(AssetType).where(AssetType.type_code != "TOWER")

    if status:
        stmt = stmt.where(Asset.status == status)
        count_stmt = count_stmt.where(Asset.status == status)
    if criticality:
        stmt = stmt.where(Asset.criticality == criticality)
        count_stmt = count_stmt.where(Asset.criticality == criticality)
    if search:
        q = f"%{search}%"
        stmt = stmt.where(or_(Asset.name.ilike(q), Asset.asset_code.ilike(q)))
        count_stmt = count_stmt.where(or_(Asset.name.ilike(q), Asset.asset_code.ilike(q)))
    if state and state.lower() != "india":
        stmt = stmt.where(Asset.metadata_["country_or_state"].astext.ilike(state))
        count_stmt = count_stmt.where(Asset.metadata_["country_or_state"].astext.ilike(state))
    if bbox_tuple and len(bbox_tuple) == 4:
        min_lon, min_lat, max_lon, max_lat = bbox_tuple
        stmt = stmt.where(
            Asset.latitude.is_not(None),
            Asset.longitude.is_not(None),
            Asset.latitude >= min_lat,
            Asset.latitude <= max_lat,
            Asset.longitude >= min_lon,
            Asset.longitude <= max_lon,
        )
        count_stmt = count_stmt.where(
            Asset.latitude.is_not(None),
            Asset.longitude.is_not(None),
            Asset.latitude >= min_lat,
            Asset.latitude <= max_lat,
            Asset.longitude >= min_lon,
            Asset.longitude <= max_lon,
        )

    total = await session.scalar(count_stmt) or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.scalars(stmt)).all()

    # Skip per-row health lookups on large GIS pages (too slow)
    if page_size <= 200:
        health_by_id = await _latest_health_map(session, [row.asset_id for row in rows])
        result = [asset_to_dict(row, health_by_id.get(row.asset_id)) for row in rows]
    else:
        result = [asset_to_dict(row, None) for row in rows]
    return result, int(total or 0)


async def _list_assets_light(
    session: AsyncSession,
    *,
    asset_type: str | None,
    category: str | None,
    state: str | None,
    bbox_tuple: tuple[float, float, float, float] | None,
    include_towers: bool,
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    """Fast path for map catalog: columns only, no count, no health joins."""
    map_meta = func.jsonb_build_object(
        "country_or_state",
        Asset.metadata_["country_or_state"],
        "region",
        Asset.metadata_["region"],
        "voltage_kv",
        Asset.metadata_["voltage_kv"],
        "length_km",
        Asset.metadata_["length_km"],
    )
    stmt = (
        select(
            Asset.asset_id,
            Asset.name,
            Asset.latitude,
            Asset.longitude,
            Asset.status,
            Asset.geometry,
            AssetType.type_code,
            map_meta,
        )
        .join(AssetType, Asset.asset_type_id == AssetType.asset_type_id)
        .where(Asset.is_active.is_(True))
    )

    if asset_type:
        legacy_map = {"tower": "TOWER", "line": "LINE", "substation": "SUBSTATION"}
        code = legacy_map.get(asset_type, asset_type.upper())
        stmt = stmt.where(AssetType.type_code == code)
    elif category:
        stmt = stmt.where(AssetType.category == category)
    elif not include_towers:
        stmt = stmt.where(AssetType.type_code != "TOWER")

    if state and state.lower() != "india":
        stmt = stmt.where(Asset.metadata_["country_or_state"].astext.ilike(state))
    if bbox_tuple and len(bbox_tuple) == 4:
        min_lon, min_lat, max_lon, max_lat = bbox_tuple
        stmt = stmt.where(
            Asset.latitude.is_not(None),
            Asset.longitude.is_not(None),
            Asset.latitude >= min_lat,
            Asset.latitude <= max_lat,
            Asset.longitude >= min_lon,
            Asset.longitude <= max_lon,
        )

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).all()

    result: list[dict] = []
    for asset_id, name, lat, lon, status, geom, type_code, meta in rows:
        legacy = (type_code or "TOWER").lower()
        if type_code == "LINE":
            legacy = "line"
        elif type_code == "SUBSTATION":
            legacy = "substation"
        item: dict[str, Any] = {
            "id": str(asset_id),
            "asset_id": str(asset_id),
            "name": name,
            "asset_type": legacy,
            "type_code": type_code,
            "latitude": lat,
            "longitude": lon,
            "status": status or "active",
            "health_score": "healthy",
            "metadata": meta or {},
        }
        if geom:
            item["geometry"] = geom
        result.append(item)
    return result, len(result)


async def get_asset(session: AsyncSession | None, asset_id: str) -> dict | None:
    if not is_db_ready() or session is None:
        from app.services.kml_loader import get_corridor_assets, _load_towers

        for pool in (get_corridor_assets(), _load_towers(), MOCK_ASSETS):
            found = next((a for a in pool if a["id"] == asset_id), None)
            if found:
                return found
        return None

    try:
        uid = UUID(asset_id)
    except ValueError:
        return None

    stmt = (
        select(Asset)
        .options(
            selectinload(Asset.asset_type),
            selectinload(Asset.substation),
            selectinload(Asset.sensors),
        )
        .where(Asset.asset_id == uid, Asset.is_active.is_(True))
    )
    asset = await session.scalar(stmt)
    if not asset:
        return None
    health = await _latest_health(session, asset.asset_id)
    data = asset_to_dict(asset, health)
    data["sensors"] = [
        {
            "sensor_id": str(s.sensor_id),
            "parameter": s.parameter,
            "unit": s.unit,
            "sensor_code": s.sensor_code,
        }
        for s in asset.sensors
    ]
    return data


async def create_asset_record(session: AsyncSession | None, payload: dict[str, Any]) -> dict:
    if not is_db_ready() or session is None:
        return mock_create_asset(payload)

    type_code = payload.get("type_code") or _legacy_to_code(payload.get("asset_type", "tower"))
    asset_type = await session.scalar(select(AssetType).where(AssetType.type_code == type_code))
    if not asset_type:
        raise ValueError(f"Unknown asset type: {type_code}")

    code = payload.get("asset_code") or payload.get("name", "ASSET").replace(" ", "-").upper()[:50]
    existing = await session.scalar(select(Asset).where(Asset.asset_code == code))
    if existing:
        raise ValueError(f"Asset code already exists: {code}")

    asset = Asset(
        asset_code=code,
        name=payload["name"],
        asset_type_id=asset_type.asset_type_id,
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        status=payload.get("status", "InService"),
        criticality=payload.get("criticality", "Medium"),
        manufacturer=payload.get("manufacturer"),
        serial_number=payload.get("serial_number"),
        voltage_level_kv=payload.get("voltage_level_kv"),
        capacity_rating=payload.get("capacity_rating"),
        metadata_=payload.get("metadata") or {},
        parent_asset_id=UUID(payload["parent_asset_id"]) if payload.get("parent_asset_id") else None,
    )
    session.add(asset)
    await session.flush()

    hs = payload.get("health_score", 85.0)
    session.add(
        HealthScore(
            asset_id=asset.asset_id,
            health_score=float(hs) if isinstance(hs, (int, float)) else 85.0,
            condition_score=2,
            risk_score=25.0,
            rul_months=60,
            model_version="manual-v1",
        )
    )
    await session.commit()
    await session.refresh(asset, ["asset_type", "substation"])
    _invalidate_corridor_cache()
    health = await _latest_health(session, asset.asset_id)
    return asset_to_dict(asset, health)


async def update_asset_record(
    session: AsyncSession | None, asset_id: str, payload: dict[str, Any]
) -> dict | None:
    if not is_db_ready() or session is None:
        asset = next((a for a in MOCK_ASSETS if a["id"] == asset_id), None)
        if asset:
            asset.update({k: v for k, v in payload.items() if v is not None})
        return asset

    try:
        uid = UUID(asset_id)
    except ValueError:
        return None

    asset = await session.scalar(
        select(Asset)
        .options(selectinload(Asset.asset_type), selectinload(Asset.substation))
        .where(Asset.asset_id == uid)
    )
    if not asset:
        return None

    for field in ("name", "status", "criticality", "manufacturer", "serial_number", "latitude", "longitude"):
        if field in payload and payload[field] is not None:
            setattr(asset, field, payload[field])
    if "metadata" in payload and payload["metadata"] is not None:
        asset.metadata_ = payload["metadata"]

    await session.commit()
    _invalidate_corridor_cache()
    health = await _latest_health(session, asset.asset_id)
    return asset_to_dict(asset, health)


async def deactivate_asset(session: AsyncSession | None, asset_id: str) -> bool:
    if not is_db_ready() or session is None:
        from app.services.mock_data import MOCK_ASSETS

        asset = next((a for a in MOCK_ASSETS if a["id"] == asset_id), None)
        if not asset:
            return False
        asset["status"] = "decommissioned"
        return True

    try:
        uid = UUID(asset_id)
    except ValueError:
        return False

    asset = await session.scalar(select(Asset).where(Asset.asset_id == uid))
    if not asset:
        return False
    asset.is_active = False
    asset.status = "Decommissioned"
    await session.commit()
    _invalidate_corridor_cache()
    return True


async def get_hierarchy(session: AsyncSession | None, asset_id: str) -> dict | None:
    asset_data = await get_asset(session, asset_id)
    if not asset_data:
        return None

    children: list[dict] = []
    if is_db_ready() and session is not None:
        try:
            uid = UUID(asset_id)
        except ValueError:
            return None
        rows = (
            await session.scalars(
                select(Asset)
                .options(selectinload(Asset.asset_type))
                .where(Asset.parent_asset_id == uid, Asset.is_active.is_(True))
            )
        ).all()
        for row in rows:
            health = await _latest_health(session, row.asset_id)
            children.append(asset_to_dict(row, health))

    return {"asset": asset_data, "children": children}


def _legacy_to_code(asset_type: str) -> str:
    return {"tower": "TOWER", "line": "LINE", "substation": "SUBSTATION"}.get(asset_type, "TOWER")


def generate_qr_url(asset_code: str) -> str:
    return f"/api/v1/assets/qr/{asset_code}.png"
