"""
Import indian_KML corridor data into PostgreSQL.

Used by:
  - scripts/import_kml_to_db.py (manual / Railway one-off)
  - app startup when DATABASE is ready and assets table is empty
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker
from app.db.init_db import (
    ASSET_TYPES,
    ROLES,
    _health_from_enum,
    _map_legacy_status,
    _map_legacy_type,
)
from app.models import (
    Alarm,
    Asset,
    AssetType,
    HealthScore,
    Inspection,
    Role,
    Sensor,
    Substation,
    User,
    UserRole,
    WorkOrder,
)

logger = logging.getLogger(__name__)


def _safe_code(raw: str, fallback: str, max_len: int = 50) -> str:
    code = re.sub(r"[^A-Za-z0-9_-]", "-", (raw or fallback).upper()).strip("-")
    return (code or fallback)[:max_len]


async def ensure_reference_data(session: AsyncSession) -> dict[str, AssetType]:
    """Ensure asset types, roles, and admin user exist."""
    type_map: dict[str, AssetType] = {}
    for code, name, category in ASSET_TYPES:
        existing = await session.scalar(select(AssetType).where(AssetType.type_code == code))
        if existing:
            type_map[code] = existing
            continue
        at = AssetType(type_code=code, type_name=name, category=category)
        session.add(at)
        type_map[code] = at
    await session.flush()

    for code, name, desc in ROLES:
        exists = await session.scalar(select(Role).where(Role.role_code == code))
        if not exists:
            session.add(Role(role_code=code, role_name=name, description=desc))
    await session.flush()

    admin = await session.scalar(select(User).where(User.email == "admin@tams.local"))
    if not admin:
        admin = User(email="admin@tams.local", display_name="TAMS Administrator", department="IT")
        session.add(admin)
        await session.flush()
        admin_role = await session.scalar(select(Role).where(Role.role_code == "ADMIN"))
        if admin_role:
            session.add(UserRole(user_id=admin.user_id, role_id=admin_role.role_id))
    await session.flush()
    return type_map


async def _seed_ops_samples(
    session: AsyncSession,
    asset_uuid_map: dict[str, UUID],
    samples: list[dict[str, Any]],
) -> None:
    """Create a few alarms / work orders / inspections from imported assets."""
    from app.services.mock_data import MOCK_ALERTS

    severity_map = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
    for alert in MOCK_ALERTS[:20]:
        asset_id = asset_uuid_map.get(alert.get("asset_id", ""))
        if not asset_id:
            continue
        session.add(
            Alarm(
                asset_id=asset_id,
                alarm_code=str(alert.get("alert_type", "ALERT")).upper()[:50],
                title=alert.get("title", "Alert")[:200],
                description=alert.get("message"),
                severity=severity_map.get(alert.get("priority", "medium"), "Medium"),
                status="Active" if alert.get("status") == "open" else "Acknowledged",
                generated_at=alert.get("created_at") or datetime.now(timezone.utc),
            )
        )

    now = datetime.now(timezone.utc)
    for i, mock in enumerate(samples[:5]):
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
                description=f"Scheduled maintenance for {mock['name']}"[:500],
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
                summary=f"Inspection for {mock['name']}"[:500],
            )
        )


async def _flush_asset_batch(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    health_rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    await session.execute(insert(Asset.__table__), rows)
    if health_rows:
        await session.execute(insert(HealthScore.__table__), health_rows)
    await session.commit()
    return len(rows)


async def import_kml_to_database(
    *,
    include_towers: bool = True,
    force: bool = False,
    batch_size: int = 500,
    write_health_for_towers: bool = False,
) -> dict[str, Any]:
    """
    Load KML → assets (+ substations catalog, sample ops rows).

    Returns counts: {lines, substations, towers, inserted, skipped, cleared}.
    """
    from app.services.kml_loader import _load_towers, get_corridor_assets, preload_kml_assets
    from app.services import mock_data

    logger.info("KML→DB import starting (towers=%s force=%s)", include_towers, force)
    preload_kml_assets()
    # Wait briefly for background tower thread when towers requested
    if include_towers:
        towers = _load_towers()
    else:
        towers = []

    corridor = get_corridor_assets()
    mock_data.MOCK_ASSETS.clear()
    mock_data.MOCK_ASSETS.extend(corridor)
    mock_data.rebuild_derived_mock_data()

    all_items = list(corridor)
    if include_towers:
        all_items.extend(towers)

    stats = {
        "lines": sum(1 for a in corridor if a.get("asset_type") == "line"),
        "substations": sum(1 for a in corridor if a.get("asset_type") == "substation"),
        "towers": len(towers) if include_towers else 0,
        "inserted": 0,
        "skipped": 0,
        "cleared": 0,
        "source_total": len(all_items),
    }

    async with async_session_maker() as session:
        type_map = await ensure_reference_data(session)
        await session.commit()

        existing = await session.scalar(select(func.count()).select_from(Asset)) or 0
        if existing and not force:
            logger.info("Assets already present (%s) — skip import (use force=True to reimport)", existing)
            stats["skipped"] = int(existing)
            return stats

        if force and existing:
            logger.warning("Force import: clearing existing assets / ops rows")
            await session.execute(delete(Inspection))
            await session.execute(delete(WorkOrder))
            await session.execute(delete(Alarm))
            await session.execute(delete(HealthScore))
            await session.execute(delete(Sensor))
            await session.execute(delete(Asset))
            await session.execute(delete(Substation))
            await session.commit()
            stats["cleared"] = int(existing)
            type_map = await ensure_reference_data(session)
            await session.commit()

        # Re-resolve type ids after possible clear
        type_map = {}
        for code, _, _ in ASSET_TYPES:
            at = await session.scalar(select(AssetType).where(AssetType.type_code == code))
            if at:
                type_map[code] = at

        # Substations catalog first
        substation_ids: dict[str, int] = {}
        for mock in (a for a in corridor if a.get("asset_type") == "substation"):
            code = _safe_code(mock.get("id") or mock["name"], "SUB")
            existing_sub = await session.scalar(
                select(Substation).where(Substation.substation_code == code)
            )
            if existing_sub:
                substation_ids[mock["id"]] = existing_sub.substation_id
                continue
            sub = Substation(
                substation_code=code,
                substation_name=mock["name"][:200],
                latitude=mock.get("latitude"),
                longitude=mock.get("longitude"),
                voltage_level=str(mock.get("metadata", {}).get("voltage_kv", "") or "")[:20],
                region=str(mock.get("metadata", {}).get("region") or "India")[:100],
                status="InService",
            )
            session.add(sub)
            await session.flush()
            substation_ids[mock["id"]] = sub.substation_id
        await session.commit()

        asset_uuid_map: dict[str, UUID] = {}
        rows: list[dict[str, Any]] = []
        health_rows: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        for idx, mock in enumerate(all_items):
            type_code = _map_legacy_type(mock["asset_type"])
            at = type_map.get(type_code)
            if not at:
                stats["skipped"] += 1
                continue

            meta = dict(mock.get("metadata") or {})
            if mock.get("description"):
                meta["description"] = mock["description"]
            if mock.get("geometry"):
                meta["geometry"] = mock["geometry"]
            meta["legacy_id"] = mock.get("id")

            code = _safe_code(mock.get("id") or mock["name"], f"AST-{idx}")
            if code in seen_codes:
                code = _safe_code(f"{code}-{idx}", f"AST-{idx}")
            seen_codes.add(code)

            asset_id = uuid4()
            asset_uuid_map[mock["id"]] = asset_id
            geom = mock.get("geometry") if isinstance(mock.get("geometry"), dict) else None

            rows.append(
                {
                    "asset_id": asset_id,
                    "asset_code": code,
                    "name": (mock.get("name") or code)[:255],
                    "asset_type_id": at.asset_type_id,
                    "substation_id": substation_ids.get(mock["id"])
                    if mock.get("asset_type") == "substation"
                    else None,
                    "latitude": mock.get("latitude"),
                    "longitude": mock.get("longitude"),
                    "status": _map_legacy_status(mock.get("status", "active")),
                    "criticality": "Critical" if mock.get("health_score") == "critical" else "Medium",
                    "metadata": meta,
                    "voltage_level_kv": meta.get("voltage_kv"),
                    "geometry": geom,
                    "is_active": True,
                }
            )

            write_health = mock.get("asset_type") != "tower" or write_health_for_towers
            if write_health:
                hs, cs, rs = _health_from_enum(mock.get("health_score"))
                health_rows.append(
                    {
                        "health_score_id": uuid4(),
                        "asset_id": asset_id,
                        "health_score": hs,
                        "condition_score": cs,
                        "risk_score": rs,
                        "rul_months": 24 if cs >= 3 else 84,
                        "model_version": "kml-import-v1",
                    }
                )

            if len(rows) >= batch_size:
                stats["inserted"] += await _flush_asset_batch(session, rows, health_rows)
                rows.clear()
                health_rows.clear()
                if stats["inserted"] % 5000 == 0:
                    logger.info("Imported %s / %s assets…", stats["inserted"], len(all_items))

        stats["inserted"] += await _flush_asset_batch(session, rows, health_rows)

        sample_pool = [a for a in corridor if a.get("asset_type") == "line"][:5] or corridor[:5]
        await _seed_ops_samples(session, asset_uuid_map, sample_pool)
        await session.commit()

    logger.info(
        "KML→DB import complete: inserted=%s lines=%s substations=%s towers=%s",
        stats["inserted"],
        stats["lines"],
        stats["substations"],
        stats["towers"],
    )
    return stats
