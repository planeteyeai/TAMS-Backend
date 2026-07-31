"""Bulk import transmission tower ground-level KML files into assets."""

from __future__ import annotations

from typing import Any
from uuid import uuid4
import xml.etree.ElementTree as ET

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, AssetType


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean_code_part(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}f}".replace("-", "m").replace(".", "_")


def _tower_asset_code(lat: float, lon: float, elevation_m: float | None) -> str:
    elev_part = "na" if elevation_m is None else _clean_code_part(elevation_m, 1)
    return f"GJ-GLE-{_clean_code_part(lat)}-{_clean_code_part(lon)}-{elev_part}"[:50]


def _parse_ground_tower_placemark(
    elem: ET.Element,
    *,
    source_name: str,
    import_batch_id: str,
) -> dict[str, Any] | None:
    lat = lon = elevation_m = None
    placemark_name = None

    for child in elem.iter():
        name = _tag_name(child.tag)
        if name == "name" and child.text and not placemark_name:
            placemark_name = child.text.strip()
        elif name == "SimpleData":
            field = child.attrib.get("name", "").strip().lower()
            text = (child.text or "").strip()
            if not text:
                continue
            if field == "latitude":
                lat = float(text)
            elif field == "longitude":
                lon = float(text)
            elif field in {"altitude (m)", "altitude", "elevation", "ground elevation"}:
                elevation_m = float(text)
        elif name == "coordinates" and child.text and (lat is None or lon is None):
            coord_text = child.text.strip().split()[0]
            parts = coord_text.split(",")
            if len(parts) >= 2:
                lon = float(parts[0])
                lat = float(parts[1])
            if len(parts) >= 3 and elevation_m is None and parts[2]:
                elevation_m = float(parts[2])

    if lat is None or lon is None:
        return None

    asset_code = _tower_asset_code(lat, lon, elevation_m)
    return {
        "asset_id": uuid4(),
        "asset_code": asset_code,
        "name": (placemark_name or asset_code)[:255],
        "latitude": lat,
        "longitude": lon,
        "elevation_m": elevation_m,
        "status": "InService",
        "criticality": "Medium",
        "metadata": {
            "country_or_state": "Gujarat",
            "region": "India",
            "asset_source": "tower-ground-kml",
            "source_file": source_name,
            "import_batch_id": import_batch_id,
            "ground_elevation_m": elevation_m,
            "tower_class": "transmission",
        },
        "is_active": True,
    }


async def import_ground_tower_kml(
    session: AsyncSession,
    *,
    source,
    source_name: str,
    import_batch_id: str,
    batch_size: int = 2000,
) -> dict[str, int | str]:
    tower_type = await session.scalar(
        select(AssetType).where(AssetType.type_code == "TOWER", AssetType.is_active.is_(True))
    )
    if not tower_type:
        raise ValueError("Tower asset type is not configured in the database")

    inserted = 0
    parsed = 0
    skipped = 0
    batch: list[dict[str, Any]] = []

    for _event, elem in ET.iterparse(source, events=("end",)):
        if _tag_name(elem.tag) != "Placemark":
            continue

        try:
            row = _parse_ground_tower_placemark(
                elem,
                source_name=source_name,
                import_batch_id=import_batch_id,
            )
            if row is None:
                skipped += 1
            else:
                parsed += 1
                batch.append({**row, "asset_type_id": tower_type.asset_type_id})

            if len(batch) >= batch_size:
                stmt = insert(Asset.__table__).values(batch)
                stmt = stmt.on_conflict_do_nothing(index_elements=["asset_code"])
                result = await session.execute(stmt)
                inserted += int(result.rowcount or 0)
                await session.commit()
                batch.clear()
        except Exception:
            skipped += 1
        finally:
            elem.clear()

    if batch:
        stmt = insert(Asset.__table__).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["asset_code"])
        result = await session.execute(stmt)
        inserted += int(result.rowcount or 0)
        await session.commit()

    return {
        "source_name": source_name,
        "import_batch_id": import_batch_id,
        "parsed": parsed,
        "inserted": inserted,
        "skipped": skipped + max(parsed - inserted, 0),
    }
