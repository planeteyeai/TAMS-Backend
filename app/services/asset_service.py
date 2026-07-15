"""Asset business logic with DB + mock fallback."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import asset_to_dict, is_db_ready
from app.models import Asset, AssetType, HealthScore
from app.services.mock_data import MOCK_ASSETS, create_asset as mock_create_asset


async def _latest_health(session: AsyncSession, asset_id: UUID) -> HealthScore | None:
    stmt = (
        select(HealthScore)
        .where(HealthScore.asset_id == asset_id)
        .order_by(HealthScore.computed_at.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


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

    total = await session.scalar(count_stmt) or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.scalars(stmt)).all()

    result = []
    for row in rows:
        health = await _latest_health(session, row.asset_id)
        result.append(asset_to_dict(row, health))
    return result, int(total or 0)


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
