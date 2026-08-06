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
    from app.services.kml_loader import _load_lines, _load_substations, _load_towers

    logger.info("KML→DB import starting (towers=%s force=%s)", include_towers, force)
    # Load directly (avoid preload background thread / double parse)
    logger.info("Parsing KML lines + substations…")
    corridor = _load_lines() + _load_substations()
    towers: list[dict[str, Any]] = []
    if include_towers:
        logger.info("Parsing KML towers (large file)…")
        towers = _load_towers()

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

        # Substations catalog — bulk insert (avoid per-row SELECT/flush over Railway)
        logger.info("Inserting substation catalog…")
        substation_ids: dict[str, int] = {}
        sub_rows: list[dict[str, Any]] = []
        seen_sub_codes: set[str] = set()
        legacy_to_code: dict[str, str] = {}
        for mock in (a for a in corridor if a.get("asset_type") == "substation"):
            code = _safe_code(mock.get("id") or mock["name"], "SUB")
            if code in seen_sub_codes:
                code = _safe_code(f"{code}-{len(seen_sub_codes)}", "SUB")
            seen_sub_codes.add(code)
            legacy_to_code[mock["id"]] = code
            sub_rows.append(
                {
                    "substation_code": code,
                    "substation_name": mock["name"][:200],
                    "latitude": mock.get("latitude"),
                    "longitude": mock.get("longitude"),
                    "voltage_level": str(mock.get("metadata", {}).get("voltage_kv", "") or "")[:20],
                    "region": str(mock.get("metadata", {}).get("region") or "India")[:100],
                    "status": "InService",
                }
            )
        if sub_rows:
            for i in range(0, len(sub_rows), batch_size):
                chunk = sub_rows[i : i + batch_size]
                await session.execute(insert(Substation.__table__), chunk)
                await session.commit()
            # Map legacy ids → DB ids
            result = await session.execute(select(Substation.substation_id, Substation.substation_code))
            code_to_id = {code: sid for sid, code in result.all()}
            for legacy_id, code in legacy_to_code.items():
                if code in code_to_id:
                    substation_ids[legacy_id] = code_to_id[code]
        logger.info("Substations in DB: %s", len(substation_ids))

        asset_uuid_map: dict[str, UUID] = {}
        rows: list[dict[str, Any]] = []
        health_rows: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        total = len(all_items)
        logger.info("Inserting %s assets in batches of %s…", total, batch_size)

        for idx, mock in enumerate(all_items):
            type_code = _map_legacy_type(mock["asset_type"])
            at = type_map.get(type_code)
            if not at:
                stats["skipped"] += 1
                continue

            meta = dict(mock.get("metadata") or {})
            if mock.get("description"):
                meta["description"] = mock["description"]
            # Keep geometry only on geometry column (avoid huge duplicate JSONB)
            meta["legacy_id"] = mock.get("id")

            code = _safe_code(mock.get("id") or mock["name"], f"AST-{idx}")
            if code in seen_codes:
                code = _safe_code(f"{code}-{idx}", f"AST-{idx}")
            seen_codes.add(code)

            asset_id = uuid4()
            # Only keep uuid map for a small sample (ops seed) — full map is huge
            if mock.get("asset_type") == "line" and len(asset_uuid_map) < 20:
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
                if stats["inserted"] % 2000 == 0 or stats["inserted"] <= batch_size:
                    logger.info("Imported %s / %s assets…", stats["inserted"], total)

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


async def upsert_missing_kml_assets(
    *,
    include_towers: bool = True,
    state: str | None = None,
    batch_size: int = 1000,
) -> dict[str, Any]:
    """
    Parse current indian_KML packs (Gujarat + Rajasthan, …) and insert only missing assets.

    Does NOT wipe existing rows — safe to run after adding a new state pack.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.services.kml_loader import (
        _load_lines,
        _load_substations,
        _load_towers,
        clear_kml_cache,
        set_state_dir_filter,
    )

    clear_kml_cache()
    set_state_dir_filter(state)
    logger.info("Upsert missing KML assets (state=%s towers=%s)", state, include_towers)
    try:
        corridor = _load_lines() + _load_substations()
        towers = _load_towers() if include_towers else []
        all_items = list(corridor) + list(towers)
        if state:
            needle = state.lower()
            all_items = [
                a
                for a in all_items
                if str((a.get("metadata") or {}).get("country_or_state") or "").lower() == needle
            ]
    finally:
        set_state_dir_filter(None)
        clear_kml_cache()

    stats: dict[str, Any] = {
        "state": state or "all",
        "source_total": len(all_items),
        "lines": sum(1 for a in all_items if a.get("asset_type") == "line"),
        "substations": sum(1 for a in all_items if a.get("asset_type") == "substation"),
        "towers": sum(1 for a in all_items if a.get("asset_type") == "tower"),
        "inserted": 0,
        "skipped": 0,
    }

    async with async_session_maker() as session:
        type_map = await ensure_reference_data(session)
        await session.commit()

        # Refresh type map after commit
        type_map = {}
        for code, _, _ in ASSET_TYPES:
            at = await session.scalar(select(AssetType).where(AssetType.type_code == code))
            if at:
                type_map[code] = at

        rows: list[dict[str, Any]] = []
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
            meta["legacy_id"] = mock.get("id")

            code = _safe_code(mock.get("id") or mock["name"], f"AST-{idx}")
            if code in seen_codes:
                code = _safe_code(f"{code}-{idx}", f"AST-{idx}")
            seen_codes.add(code)

            geom = mock.get("geometry") if isinstance(mock.get("geometry"), dict) else None
            rows.append(
                {
                    "asset_id": uuid4(),
                    "asset_code": code,
                    "name": (mock.get("name") or code)[:255],
                    "asset_type_id": at.asset_type_id,
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

            if len(rows) >= batch_size:
                stmt = pg_insert(Asset.__table__).values(rows)
                stmt = stmt.on_conflict_do_nothing(index_elements=["asset_code"])
                result = await session.execute(stmt)
                stats["inserted"] += int(result.rowcount or 0)
                await session.commit()
                rows.clear()
                if stats["inserted"] and stats["inserted"] % 2000 == 0:
                    logger.info("Upserted %s assets…", stats["inserted"])

        if rows:
            stmt = pg_insert(Asset.__table__).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["asset_code"])
            result = await session.execute(stmt)
            stats["inserted"] += int(result.rowcount or 0)
            await session.commit()

    stats["skipped"] = max(stats["source_total"] - stats["inserted"], 0)
    logger.info(
        "Upsert KML complete: inserted=%s skipped=%s state=%s",
        stats["inserted"],
        stats["skipped"],
        stats["state"],
    )
    return stats


def _approx_near(lat1: float, lon1: float, lat2: float, lon2: float, meters: float = 25.0) -> bool:
    import math

    dlat = (lat1 - lat2) * 111_320.0
    dlon = (lon1 - lon2) * 111_320.0 * math.cos(math.radians(lat1))
    return (dlat * dlat + dlon * dlon) <= meters * meters


# Avoid re-syncing the same viewport on every camera pan (seconds).
_SYNC_CACHE: dict[str, float] = {}
_SYNC_TTL_S = 120.0


async def upsert_detected_towers_in_bbox(
    *,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    state: str | None = None,
    limit: int = 5000,
    near_meters: float = 25.0,
    force: bool = False,
) -> dict[str, int]:
    """
    Detect KML/OSM towers in the viewport that are missing from Postgres and insert them.

    Matching skips insert when asset_code / legacy_id already exists, or another tower
    is already within `near_meters` (avoids duplicates from slight coordinate drift).
    """
    import time

    from app.services.kml_loader import get_towers_in_bbox

    cache_key = f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}|{state}|{limit}"
    now = time.monotonic()

    candidates = get_towers_in_bbox(
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        state=state,
        limit=limit,
    )
    gap_count = 0
    # Fill corridor gaps (missed OSM towers + provisional pylons visible in imagery)
    try:
        from app.services.corridor_graph import detect_missing_towers_along_lines

        gap_towers = detect_missing_towers_along_lines(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            known_towers=candidates,
            max_new=min(80, max(20, limit // 10)),
        )
        if gap_towers:
            seen = {str(t.get("id")) for t in candidates}
            for g in gap_towers:
                gid = str(g.get("id") or "")
                if gid and gid not in seen:
                    candidates.append(g)
                    seen.add(gid)
                    gap_count += 1
    except Exception:
        logger.exception("Corridor gap-fill failed")

    if not candidates:
        _SYNC_CACHE[cache_key] = now
        return {"detected": 0, "inserted": 0, "skipped": 0}

    if (
        not force
        and gap_count == 0
        and cache_key in _SYNC_CACHE
        and now - _SYNC_CACHE[cache_key] < _SYNC_TTL_S
    ):
        try:
            corridor = await upsert_corridors_from_seed_towers(candidates[:3], max_seeds=2)
            return {
                "detected": len(candidates),
                "inserted": 0,
                "skipped": 0,
                "cached": 1,
                "corridor": corridor,
            }
        except Exception:
            return {"detected": len(candidates), "inserted": 0, "skipped": 0, "cached": 1}

    async with async_session_maker() as session:
        # Lightweight — do not call ensure_reference_data on the map hot path.
        tower_type = await session.scalar(select(AssetType).where(AssetType.type_code == "TOWER"))
        if not tower_type:
            logger.warning("TOWER asset type missing — cannot upsert detected towers")
            return {"detected": len(candidates), "inserted": 0, "skipped": len(candidates)}

        pad = 0.0003  # ~30 m
        existing_rows = (
            await session.execute(
                select(Asset.asset_code, Asset.latitude, Asset.longitude, Asset.metadata_)
                .join(AssetType, Asset.asset_type_id == AssetType.asset_type_id)
                .where(
                    AssetType.type_code == "TOWER",
                    Asset.is_active.is_(True),
                    Asset.latitude.is_not(None),
                    Asset.longitude.is_not(None),
                    Asset.latitude >= min_lat - pad,
                    Asset.latitude <= max_lat + pad,
                    Asset.longitude >= min_lon - pad,
                    Asset.longitude <= max_lon + pad,
                )
            )
        ).all()

        # Fast path: DB already has at least as many towers as KML for this viewport.
        if len(existing_rows) >= len(candidates):
            _SYNC_CACHE[cache_key] = now
            result = {
                "detected": len(candidates),
                "inserted": 0,
                "skipped": len(candidates),
                "db_covered": 1,
            }
            try:
                result["corridor"] = await upsert_corridors_from_seed_towers(
                    candidates[:3], max_seeds=2
                )
            except Exception:
                logger.exception("Corridor walk failed on covered viewport")
            return result

        existing_codes: set[str] = set()
        existing_legacy: set[str] = set()
        existing_pts: list[tuple[float, float]] = []
        for code, lat, lon, meta in existing_rows:
            if code:
                existing_codes.add(str(code).upper())
            if isinstance(meta, dict):
                lid = meta.get("legacy_id") or meta.get("full_id") or meta.get("osm_id")
                if lid:
                    existing_legacy.add(str(lid))
            if lat is not None and lon is not None:
                existing_pts.append((float(lat), float(lon)))

        rows: list[dict[str, Any]] = []
        skipped = 0
        for idx, mock in enumerate(candidates):
            lat = mock.get("latitude")
            lon = mock.get("longitude")
            if lat is None or lon is None:
                skipped += 1
                continue

            legacy_id = str(mock.get("id") or "")
            code = _safe_code(legacy_id or mock.get("name") or f"TWR-{idx}", f"TWR-{idx}")
            osm_id = str((mock.get("metadata") or {}).get("osm_id") or "")
            full_id = str((mock.get("metadata") or {}).get("full_id") or "")

            if (
                code in existing_codes
                or legacy_id in existing_legacy
                or (osm_id and osm_id in existing_legacy)
                or (full_id and full_id in existing_legacy)
            ):
                skipped += 1
                continue

            if any(_approx_near(float(lat), float(lon), elat, elon, near_meters) for elat, elon in existing_pts):
                skipped += 1
                continue

            meta = dict(mock.get("metadata") or {})
            if mock.get("description"):
                meta["description"] = mock["description"]
            meta["legacy_id"] = legacy_id
            meta["detected_source"] = "viewport_kml_sync"

            rows.append(
                {
                    "asset_id": uuid4(),
                    "asset_code": code,
                    "name": (mock.get("name") or code)[:255],
                    "asset_type_id": tower_type.asset_type_id,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "status": _map_legacy_status(mock.get("status", "active")),
                    "criticality": "Medium",
                    "metadata": meta,
                    "voltage_level_kv": meta.get("voltage_kv"),
                    "geometry": None,
                    "is_active": True,
                }
            )
            existing_codes.add(code)
            if legacy_id:
                existing_legacy.add(legacy_id)
            existing_pts.append((float(lat), float(lon)))

        inserted = 0
        if rows:
            for i in range(0, len(rows), 200):
                chunk = rows[i : i + 200]
                try:
                    inserted += await _flush_asset_batch(session, chunk, [])
                except Exception:
                    logger.exception("Failed inserting detected tower batch; trying one-by-one")
                    await session.rollback()
                    for row in chunk:
                        try:
                            await session.execute(insert(Asset.__table__), [row])
                            await session.commit()
                            inserted += 1
                        except Exception:
                            await session.rollback()
                            skipped += 1

        _SYNC_CACHE[cache_key] = now
        logger.info(
            "Viewport tower sync bbox=(%.4f,%.4f)–(%.4f,%.4f): detected=%s inserted=%s skipped=%s",
            min_lon,
            min_lat,
            max_lon,
            max_lat,
            len(candidates),
            inserted,
            skipped,
        )
        result = {"detected": len(candidates), "inserted": inserted, "skipped": skipped}

        # When new towers appear (or viewport is incomplete), walk each seed's
        # connected lines out to substations / dead-ends and persist the corridor.
        seeds = candidates[:8]
        if seeds:
            try:
                corridor = await upsert_corridors_from_seed_towers(seeds, max_seeds=5)
                result["corridor"] = corridor
            except Exception:
                logger.exception("Corridor walk/upsert failed after tower detect")
        return result


async def _existing_for_candidates(
    session: AsyncSession, legacy_ids: list[str], codes: list[str]
) -> tuple[set[str], set[str]]:
    """Load only the codes/legacy ids we might collide with (not the whole table)."""
    existing_codes: set[str] = set()
    existing_legacy: set[str] = set()
    code_list = [c.upper() for c in codes if c][:500]
    leg_list = [x for x in legacy_ids if x][:500]
    if code_list:
        rows = (
            await session.execute(select(Asset.asset_code).where(Asset.asset_code.in_(code_list)))
        ).all()
        for (code,) in rows:
            if code:
                existing_codes.add(str(code).upper())
    if leg_list:
        rows = (
            await session.execute(
                select(Asset.metadata_).where(Asset.metadata_["legacy_id"].astext.in_(leg_list))
            )
        ).all()
        for (meta,) in rows:
            if isinstance(meta, dict) and meta.get("legacy_id"):
                existing_legacy.add(str(meta["legacy_id"]))
    return existing_codes, existing_legacy


async def upsert_corridors_from_seed_towers(
    seed_towers: list[dict[str, Any]],
    *,
    max_seeds: int = 5,
) -> dict[str, Any]:
    """
    For each detected seed tower: walk connected lines until substations / endpoints,
    then upsert towers + lines + substations with adjacency / multi-line junction metadata.
    """
    from app.services.corridor_graph import walk_corridor_from_tower

    stats = {
        "seeds": 0,
        "walks": 0,
        "towers_inserted": 0,
        "lines_inserted": 0,
        "substations_inserted": 0,
        "junctions": 0,
        "endpoints": 0,
        "skipped": 0,
    }
    if not seed_towers:
        return stats

    all_towers: dict[str, dict[str, Any]] = {}
    all_lines: dict[str, dict[str, Any]] = {}
    all_subs: dict[str, dict[str, Any]] = {}
    all_adj: dict[str, list[dict[str, Any]]] = {}
    all_lines_at: dict[str, list[str]] = {}
    endpoint_count = 0

    for seed in seed_towers[:max_seeds]:
        stats["seeds"] += 1
        try:
            walk = walk_corridor_from_tower(seed, max_km=45.0, max_hops=40)
        except Exception:
            logger.exception("Corridor walk failed for seed %s", seed.get("id"))
            continue
        stats["walks"] += 1
        endpoint_count += len(walk.get("endpoints") or [])
        stats["junctions"] += len(walk.get("junction_tower_ids") or [])
        for tw in walk.get("towers") or []:
            tid = str(tw.get("id") or "")
            if tid:
                all_towers[tid] = tw
        for ln in walk.get("lines") or []:
            lid = str(ln.get("id") or "")
            if lid:
                all_lines[lid] = ln
        for sub in walk.get("substations") or []:
            sid = str(sub.get("id") or "")
            if sid:
                all_subs[sid] = sub
        for tid, nbrs in (walk.get("adjacencies") or {}).items():
            all_adj[tid] = nbrs
        for tid, lids in (walk.get("lines_at_tower") or {}).items():
            prev = set(all_lines_at.get(tid, []))
            prev.update(lids)
            all_lines_at[tid] = sorted(prev)

    stats["endpoints"] = endpoint_count
    if not (all_towers or all_lines or all_subs):
        return stats

    # Cap persist size so one dense corridor cannot stall the map API.
    tower_items = list(all_towers.items())[:120]
    line_items = list(all_lines.items())[:50]
    sub_items = list(all_subs.items())[:20]
    all_towers = dict(tower_items)
    all_lines = dict(line_items)
    all_subs = dict(sub_items)

    async with async_session_maker() as session:
        type_map: dict[str, AssetType] = {}
        for code in ("TOWER", "LINE", "SUBSTATION"):
            at = await session.scalar(select(AssetType).where(AssetType.type_code == code))
            if at:
                type_map[code] = at
        if "TOWER" not in type_map:
            return stats

        candidate_legacy = list(all_towers.keys()) + list(all_lines.keys()) + list(all_subs.keys())
        candidate_codes = [_safe_code(x, "AST") for x in candidate_legacy]
        existing_codes, existing_legacy = await _existing_for_candidates(
            session, candidate_legacy, candidate_codes
        )

        def _prepare(
            mock: dict[str, Any],
            type_code: str,
            *,
            extra_meta: dict[str, Any] | None = None,
        ) -> dict[str, Any] | None:
            at = type_map.get(type_code)
            if not at:
                return None
            legacy_id = str(mock.get("id") or "")
            code = _safe_code(legacy_id or mock.get("name") or type_code, type_code)
            if code in existing_codes or legacy_id in existing_legacy:
                return None
            osm_id = str((mock.get("metadata") or {}).get("osm_id") or "")
            if osm_id and osm_id in existing_legacy:
                return None

            meta = dict(mock.get("metadata") or {})
            if mock.get("description"):
                meta["description"] = mock["description"]
            meta["legacy_id"] = legacy_id
            meta["detected_source"] = "corridor_walk_sync"
            if extra_meta:
                meta.update(extra_meta)

            geom = mock.get("geometry") if isinstance(mock.get("geometry"), dict) else None
            row = {
                "asset_id": uuid4(),
                "asset_code": code,
                "name": (mock.get("name") or code)[:255],
                "asset_type_id": at.asset_type_id,
                "latitude": mock.get("latitude"),
                "longitude": mock.get("longitude"),
                "status": _map_legacy_status(mock.get("status", "active")),
                "criticality": "Medium",
                "metadata": meta,
                "voltage_level_kv": meta.get("voltage_kv"),
                "geometry": geom,
                "is_active": True,
            }
            existing_codes.add(code)
            if legacy_id:
                existing_legacy.add(legacy_id)
            return row

        tower_rows: list[dict[str, Any]] = []
        for tid, tw in all_towers.items():
            extra = {
                "adjacent_towers": all_adj.get(tid, [])[:12],
                "line_legacy_ids": all_lines_at.get(tid, []),
                "is_junction": len(all_lines_at.get(tid, [])) > 1,
            }
            row = _prepare(tw, "TOWER", extra_meta=extra)
            if row:
                tower_rows.append(row)
            else:
                stats["skipped"] += 1

        line_rows: list[dict[str, Any]] = []
        for lid, ln in all_lines.items():
            tower_ids = [
                str(t.get("id"))
                for t in all_towers.values()
                if lid in set(all_lines_at.get(str(t.get("id") or ""), []))
            ]
            extra = {
                "corridor_tower_ids": tower_ids[:200],
                "tower_count_on_line": len(tower_ids),
            }
            row = _prepare(ln, "LINE", extra_meta=extra)
            if row:
                line_rows.append(row)
            else:
                stats["skipped"] += 1

        sub_rows: list[dict[str, Any]] = []
        for sid, sub in all_subs.items():
            row = _prepare(sub, "SUBSTATION", extra_meta={"endpoint_role": "terminus"})
            if row:
                sub_rows.append(row)
            else:
                stats["skipped"] += 1

        async def _insert_rows(rows: list[dict[str, Any]], counter_key: str) -> None:
            if not rows:
                return
            for i in range(0, len(rows), 100):
                chunk = rows[i : i + 100]
                try:
                    n = await _flush_asset_batch(session, chunk, [])
                    stats[counter_key] += n
                except Exception:
                    logger.exception("Corridor batch insert failed (%s)", counter_key)
                    await session.rollback()
                    for row in chunk:
                        try:
                            await session.execute(insert(Asset.__table__), [row])
                            await session.commit()
                            stats[counter_key] += 1
                        except Exception:
                            await session.rollback()
                            stats["skipped"] += 1

        await _insert_rows(line_rows, "lines_inserted")
        await _insert_rows(sub_rows, "substations_inserted")
        await _insert_rows(tower_rows, "towers_inserted")

    logger.info(
        "Corridor upsert: seeds=%s walks=%s towers+%s lines+%s subs+%s junctions=%s endpoints=%s",
        stats["seeds"],
        stats["walks"],
        stats["towers_inserted"],
        stats["lines_inserted"],
        stats["substations_inserted"],
        stats["junctions"],
        stats["endpoints"],
    )
    return stats
