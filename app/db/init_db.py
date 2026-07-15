"""Database initialization and seed data."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import Base, async_session_maker, engine
from app.models import (
    Alarm,
    Asset,
    AssetType,
    HealthScore,
    Inspection,
    Role,
    Substation,
    User,
    UserRole,
    WorkOrder,
)
from app.services.mock_data import MOCK_ALERTS, MOCK_ASSETS

logger = logging.getLogger(__name__)

_db_ready = False

ASSET_TYPES = [
    ("TOWER", "Transmission Tower", "Tower"),
    ("LINE", "Transmission Line", "Line"),
    ("SUBSTATION", "Substation", "Substation"),
    ("TRANSFORMER", "Power Transformer", "Transformer"),
    ("BREAKER", "Circuit Breaker", "Breaker"),
    ("RELAY", "Protection Relay", "Relay"),
]

ROLES = [
    ("ADMIN", "Administrator", "Full system access"),
    ("OPS_ENGINEER", "Operations Engineer", "Monitoring and alarms"),
    ("MAINT_ENGINEER", "Maintenance Engineer", "Work orders and maintenance"),
    ("ASSET_ENGINEER", "Asset Engineer", "Asset registry and health"),
    ("FIELD_TECH", "Field Technician", "Inspections and field work"),
    ("EXECUTIVE", "Executive Management", "Dashboards and reports"),
    ("AUDITOR", "Auditor", "Read-only audit access"),
]


def _map_legacy_type(asset_type: str) -> str:
    mapping = {"tower": "TOWER", "line": "LINE", "substation": "SUBSTATION"}
    return mapping.get(asset_type, "TOWER")


def _map_legacy_status(status: str) -> str:
    mapping = {
        "active": "InService",
        "inactive": "InService",
        "maintenance": "Maintenance",
        "decommissioned": "Decommissioned",
    }
    return mapping.get(status, "InService")


def _health_from_enum(score: str | None) -> tuple[float, int, float]:
    if score == "critical":
        return 35.0, 5, 85.0
    if score == "attention_required":
        return 62.0, 3, 55.0
    return 88.0, 1, 20.0


def asset_to_dict(asset: Asset, latest_health: HealthScore | None = None) -> dict:
    """Serialize asset for API (backward compatible with legacy frontend)."""
    type_code = asset.asset_type.type_code if asset.asset_type else "TOWER"
    legacy_type = type_code.lower() if type_code in ("TOWER", "LINE", "SUBSTATION") else "tower"
    if type_code == "LINE":
        legacy_type = "line"
    elif type_code == "SUBSTATION":
        legacy_type = "substation"

    health_enum = "healthy"
    if latest_health:
        if latest_health.health_score < 50:
            health_enum = "critical"
        elif latest_health.health_score < 75:
            health_enum = "attention_required"

    meta = dict(asset.metadata_ or {})
    if asset.voltage_level_kv:
        meta.setdefault("voltage_kv", asset.voltage_level_kv)

    result = {
        "id": str(asset.asset_id),
        "asset_id": str(asset.asset_id),
        "asset_code": asset.asset_code,
        "name": asset.name,
        "asset_type": legacy_type,
        "category": asset.asset_type.category if asset.asset_type else "Tower",
        "type_code": type_code,
        "latitude": asset.latitude,
        "longitude": asset.longitude,
        "status": asset.status,
        "criticality": asset.criticality,
        "health_score": health_enum,
        "description": meta.get("description") or asset.name,
        "metadata": meta,
        "manufacturer": asset.manufacturer,
        "serial_number": asset.serial_number,
        "voltage_level_kv": asset.voltage_level_kv,
        "capacity_rating": asset.capacity_rating,
        "capacity_unit": asset.capacity_unit,
        "installation_date": asset.installation_date.isoformat() if asset.installation_date else None,
        "warranty_expiry_date": asset.warranty_expiry_date.isoformat() if asset.warranty_expiry_date else None,
        "tags": asset.tags or [],
        "qr_code_url": asset.qr_code_url,
        "parent_asset_id": str(asset.parent_asset_id) if asset.parent_asset_id else None,
        "substation_id": asset.substation_id,
        "substation_name": asset.substation.substation_name if asset.substation else None,
        "is_active": asset.is_active,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }

    if latest_health:
        result["health"] = {
            "health_score": latest_health.health_score,
            "condition_score": latest_health.condition_score,
            "risk_score": latest_health.risk_score,
            "rul_months": latest_health.rul_months,
            "computed_at": latest_health.computed_at,
        }

    geom = meta.get("geometry")
    if geom:
        result["geometry"] = geom

    return result


async def check_db_connection() -> bool:
    global _db_ready
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _db_ready = True
        return True
    except Exception as exc:
        logger.warning("Database unavailable, using in-memory mock data: %s", exc)
        _db_ready = False
        return False


def is_db_ready() -> bool:
    return _db_ready


async def init_database() -> bool:
    """Create extensions, tables, and seed if empty."""
    if not await check_db_connection():
        return False

    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "postgis"'))
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        count = await session.scalar(select(func.count()).select_from(Asset))
        if count and count > 0:
            logger.info("Database already seeded (%s assets)", count)
            return True
        await _seed(session)
        await session.commit()
        logger.info("Database seeded successfully")
    return True


async def _seed(session: AsyncSession) -> None:
    type_map: dict[str, AssetType] = {}
    for code, name, category in ASSET_TYPES:
        at = AssetType(type_code=code, type_name=name, category=category)
        session.add(at)
        type_map[code] = at
    await session.flush()

    for code, name, desc in ROLES:
        session.add(Role(role_code=code, role_name=name, description=desc))
    await session.flush()

    admin = User(email="admin@tams.local", display_name="TAMS Administrator", department="IT")
    session.add(admin)
    await session.flush()

    admin_role = await session.scalar(select(Role).where(Role.role_code == "ADMIN"))
    if admin_role:
        session.add(UserRole(user_id=admin.user_id, role_id=admin_role.role_id))

    substation_ids: dict[str, int] = {}
    for mock in MOCK_ASSETS:
        if mock.get("asset_type") != "substation":
            continue
        code = mock["name"].replace(" ", "-").upper()[:50]
        sub = Substation(
            substation_code=code,
            substation_name=mock["name"],
            latitude=mock.get("latitude"),
            longitude=mock.get("longitude"),
            voltage_level=str(mock.get("metadata", {}).get("voltage_kv", "")),
            region=mock.get("metadata", {}).get("region"),
            status="InService",
        )
        session.add(sub)
        await session.flush()
        substation_ids[mock["id"]] = sub.substation_id

    asset_uuid_map: dict[str, UUID] = {}
    for mock in MOCK_ASSETS:
        type_code = _map_legacy_type(mock["asset_type"])
        meta = dict(mock.get("metadata") or {})
        if mock.get("description"):
            meta["description"] = mock["description"]
        if mock.get("geometry"):
            meta["geometry"] = mock["geometry"]

        substation_id = substation_ids.get(mock["id"]) if mock["asset_type"] == "substation" else None
        asset = Asset(
            asset_code=mock["name"].replace(" ", "-").upper()[:50],
            name=mock["name"],
            asset_type_id=type_map[type_code].asset_type_id,
            substation_id=substation_id,
            latitude=mock.get("latitude"),
            longitude=mock.get("longitude"),
            status=_map_legacy_status(mock.get("status", "active")),
            criticality="Critical" if mock.get("health_score") == "critical" else "Medium",
            metadata_=meta,
            voltage_level_kv=meta.get("voltage_kv"),
        )
        session.add(asset)
        await session.flush()
        asset_uuid_map[mock["id"]] = asset.asset_id

        hs, cs, rs = _health_from_enum(mock.get("health_score"))
        session.add(
            HealthScore(
                asset_id=asset.asset_id,
                health_score=hs,
                condition_score=cs,
                risk_score=rs,
                rul_months=24 if cs >= 3 else 84,
                model_version="seed-v1",
            )
        )

    severity_map = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
    for alert in MOCK_ALERTS:
        asset_id = asset_uuid_map.get(alert.get("asset_id"))
        if not asset_id:
            continue
        session.add(
            Alarm(
                asset_id=asset_id,
                alarm_code=alert.get("alert_type", "ALERT").upper(),
                title=alert.get("title", "Alert"),
                description=alert.get("message"),
                severity=severity_map.get(alert.get("priority", "medium"), "Medium"),
                status="Active" if alert.get("status") == "open" else "Acknowledged",
                generated_at=alert.get("created_at") or datetime.now(timezone.utc),
            )
        )

    now = datetime.now(timezone.utc)
    for i, mock in enumerate(MOCK_ASSETS[:3]):
        aid = asset_uuid_map.get(mock["id"])
        if not aid:
            continue
        session.add(
            WorkOrder(
                work_order_number=f"WO-2026-{1000 + i}",
                asset_id=aid,
                maintenance_type="PM" if i == 0 else "PdM",
                priority="High" if i == 1 else "Medium",
                status="Scheduled" if i < 2 else "InProgress",
                description=f"Scheduled maintenance for {mock['name']}",
                assigned_crew="Team Alpha",
                scheduled_start=now + timedelta(days=i + 1),
                scheduled_end=now + timedelta(days=i + 2),
            )
        )
        session.add(
            Inspection(
                asset_id=aid,
                inspection_type="Visual" if i % 2 == 0 else "Drone",
                status="Completed" if i == 0 else "Scheduled",
                inspector_name="Field Inspector",
                scheduled_date=now - timedelta(days=30 - i),
                completed_date=now - timedelta(days=25) if i == 0 else None,
                overall_score=85.0 - i * 10,
                summary=f"Inspection for {mock['name']}",
            )
        )
