"""Geotechnical investigation service (DB + in-memory mock fallback)."""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.init_db import is_db_ready
from app.models import GeotechInvestigation

# ---------------------------------------------------------------------------
# Seed: Location 1 — Nirona, Bhuj (from Transmission Line geotech report)
# ---------------------------------------------------------------------------

NIRONA_SEED: dict = {
    "site_code": "NIR-LOC-01",
    "site_name": "Nirona Location 1 — Transmission Tower",
    "project_name": "Transmission line",
    "client_name": "Planeteye Infra AI",
    "purpose": "Construction of Transmission Tower",
    "region": "Barren land, Nirona, Bhuj, Gujarat",
    "latitude": 23.446103,
    "longitude": 69.599508,
    "investigation_depth_m": 2.0,
    "groundwater_note": "Not encountered up to 2.0 m",
    "soil_layers": [
        {
            "depth_from_m": 0.0,
            "depth_to_m": 0.5,
            "gravel_pct": 4,
            "sand_pct": 30,
            "silt_pct": 38,
            "clay_pct": 28,
            "ll": 44,
            "pl": 23,
            "pi": 21,
            "soil_class": "CI",
            "mdd": 1.71,
            "omc": 18,
            "dry_density": 1.61,
            "fsi": 48,
            "bulk_density": 1.89,
            "ucs": 1.30,
            "sg": 2.70,
            "sbc": 10,
            "cbr": 4,
            "remarks": "Silty clay, medium stiff",
        },
        {
            "depth_from_m": 0.5,
            "depth_to_m": 1.0,
            "gravel_pct": 8,
            "sand_pct": 34,
            "silt_pct": 35,
            "clay_pct": 23,
            "ll": 41,
            "pl": 22,
            "pi": 19,
            "soil_class": "CL",
            "mdd": 1.74,
            "omc": 17,
            "dry_density": 1.65,
            "fsi": 42,
            "bulk_density": 1.91,
            "ucs": 1.45,
            "sg": 2.70,
            "sbc": 13,
            "cbr": 6,
            "remarks": "Clayey silt, stiff",
        },
        {
            "depth_from_m": 1.0,
            "depth_to_m": 1.5,
            "gravel_pct": 18,
            "sand_pct": 43,
            "silt_pct": 25,
            "clay_pct": 14,
            "ll": 34,
            "pl": 20,
            "pi": 14,
            "soil_class": "CL-ML",
            "mdd": 1.80,
            "omc": 15,
            "dry_density": 1.70,
            "fsi": 24,
            "bulk_density": 1.95,
            "ucs": 1.82,
            "sg": 2.70,
            "sbc": 16,
            "cbr": 10,
            "remarks": "Sandy clay with increasing density",
        },
        {
            "depth_from_m": 1.5,
            "depth_to_m": 2.0,
            "gravel_pct": 30,
            "sand_pct": 50,
            "silt_pct": 14,
            "clay_pct": 6,
            "ll": 28,
            "pl": 17,
            "pi": 11,
            "soil_class": "SM",
            "mdd": 1.88,
            "omc": 12,
            "dry_density": 1.78,
            "fsi": 10,
            "bulk_density": 2.00,
            "ucs": 2.30,
            "sg": 2.70,
            "sbc": 20,
            "cbr": 15,
            "remarks": "Dense sandy murum, suitable founding stratum",
        },
    ],
    "design_params": {
        "foundation_type": "1.0 m × 1.0 m Isolated Stub Foundation",
        "df_m": 1.5,
        "allowable_settlement_mm": 25,
        "fos_shear": 2.5,
        "fos_uplift": 3.0,
        "c_tm2": 1.5,
        "phi_deg": 20,
        "gamma_tm3": 1.90,
        "codes": ["IS 6403:1981", "IS 2911 (Part 1/Sec 2):2010", "IS 8009 (Part-1)", "IS 3043"],
    },
    "sbc_by_depth": [
        {"depth_m": 0.5, "sbc_tm2": 10},
        {"depth_m": 1.0, "sbc_tm2": 15},
        {"depth_m": 1.5, "sbc_tm2": 20, "design": True},
        {"depth_m": 2.0, "sbc_tm2": 24},
        {"depth_m": 2.5, "sbc_tm2": 26},
        {"depth_m": 3.0, "sbc_tm2": 28},
        {"depth_m": 3.5, "sbc_tm2": 30},
        {"depth_m": 4.0, "sbc_tm2": 32},
    ],
    "pile_capacities": [
        {"diameter_mm": 450, "depth_m": 1.0, "vertical_t": 3.0, "uplift_t": 0.47, "lateral_t": 5.6},
        {"diameter_mm": 450, "depth_m": 1.5, "vertical_t": 6.3, "uplift_t": 0.73, "lateral_t": 5.6},
        {"diameter_mm": 450, "depth_m": 2.0, "vertical_t": 8.3, "uplift_t": 1.08, "lateral_t": 5.6},
        {"diameter_mm": 600, "depth_m": 1.0, "vertical_t": 5.1, "uplift_t": 0.63, "lateral_t": 8.9},
        {"diameter_mm": 600, "depth_m": 1.5, "vertical_t": 11.4, "uplift_t": 0.97, "lateral_t": 8.9},
        {"diameter_mm": 600, "depth_m": 2.0, "vertical_t": 14.7, "uplift_t": 1.44, "lateral_t": 8.9},
    ],
    "cbr_by_depth": [
        {"depth_from_m": 0.0, "depth_to_m": 1.0, "soil_type": "CI — Medium stiff silty clay", "cbr_pct": 4},
        {"depth_from_m": 1.0, "depth_to_m": 2.0, "soil_type": "SM — Dense sandy murum", "cbr_pct": 12},
    ],
    "resistivity": {
        "method": "Wenner (IS 3043)",
        "formula": "ρ = 2π a R",
        "layers": [
            {"depth_from_m": 0.0, "depth_to_m": 1.0, "soil_type": "CI-CL", "resistivity_ohm_m": "50-60"},
            {"depth_from_m": 1.0, "depth_to_m": 2.0, "soil_type": "SM", "resistivity_ohm_m": "80-90"},
        ],
        "adopted_ohm_m": 85,
        "target_earth_resistance_ohm": 10,
        "earthing_type": "Copper-bonded GI Pipe Earthing",
        "pit_depth_m": 3.0,
    },
    "recommendations": {
        "adopted_sbc_tm2": 20,
        "design_depth_m": 1.5,
        "governing_cbr_pct": 4,
        "recommended_pile": "600 mm dia × 2.0 m for angle/tension towers; 450 mm × 2.0 m for suspension",
        "settlement_mm": 11.3,
        "settlement_status": "Safe",
    },
    "remarks": "Seeded from Transmission Line geotech investigation (Nirona, Bhuj).",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: GeotechInvestigation) -> dict:
    return {
        "id": str(row.geotech_id),
        "geotech_id": str(row.geotech_id),
        "site_code": row.site_code,
        "site_name": row.site_name,
        "project_name": row.project_name,
        "client_name": row.client_name,
        "purpose": row.purpose,
        "region": row.region,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "investigation_depth_m": row.investigation_depth_m,
        "groundwater_note": row.groundwater_note,
        "soil_layers": row.soil_layers or [],
        "design_params": row.design_params or {},
        "sbc_by_depth": row.sbc_by_depth or [],
        "pile_capacities": row.pile_capacities or [],
        "cbr_by_depth": row.cbr_by_depth or [],
        "resistivity": row.resistivity or {},
        "recommendations": row.recommendations or {},
        "remarks": row.remarks,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "source": "database",
    }


def _mock_seed() -> list[dict]:
    item = deepcopy(NIRONA_SEED)
    gid = str(uuid4())
    item.update(
        {
            "id": gid,
            "geotech_id": gid,
            "is_active": True,
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
            "source": "mock",
        }
    )
    return [item]


_MOCK_GEOTECH: list[dict] = _mock_seed()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _summary(item: dict) -> dict:
    rec = item.get("recommendations") or {}
    return {
        "id": item.get("id") or item.get("geotech_id"),
        "site_code": item.get("site_code"),
        "site_name": item.get("site_name"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "adopted_sbc_tm2": rec.get("adopted_sbc_tm2"),
        "design_depth_m": rec.get("design_depth_m"),
        "governing_cbr_pct": rec.get("governing_cbr_pct"),
        "adopted_resistivity_ohm_m": (item.get("resistivity") or {}).get("adopted_ohm_m"),
        "groundwater_note": item.get("groundwater_note"),
        "investigation_depth_m": item.get("investigation_depth_m"),
        "recommended_pile": rec.get("recommended_pile"),
        "layer_count": len(item.get("soil_layers") or []),
    }


async def list_investigations(
    session: AsyncSession | None,
    *,
    page: int = 1,
    page_size: int = 50,
    q: str | None = None,
) -> tuple[list[dict], int]:
    if not is_db_ready() or session is None:
        items = [i for i in _MOCK_GEOTECH if i.get("is_active", True)]
        if q:
            ql = q.lower()
            items = [
                i
                for i in items
                if ql in (i.get("site_code") or "").lower()
                or ql in (i.get("site_name") or "").lower()
                or ql in (i.get("region") or "").lower()
            ]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    stmt = select(GeotechInvestigation).where(GeotechInvestigation.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (GeotechInvestigation.site_code.ilike(like))
            | (GeotechInvestigation.site_name.ilike(like))
            | (GeotechInvestigation.region.ilike(like))
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = (
        stmt.order_by(GeotechInvestigation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.scalars(stmt)).all()
    return [_row_to_dict(r) for r in rows], int(total or 0)


async def get_investigation(session: AsyncSession | None, geotech_id: str) -> dict | None:
    if not is_db_ready() or session is None:
        for i in _MOCK_GEOTECH:
            if i.get("id") == geotech_id or i.get("geotech_id") == geotech_id:
                return i
        return None

    try:
        uid = UUID(geotech_id)
    except ValueError:
        return None
    row = await session.get(GeotechInvestigation, uid)
    if not row or not row.is_active:
        return None
    return _row_to_dict(row)


async def nearest_investigation(
    session: AsyncSession | None,
    *,
    lat: float,
    lon: float,
    max_km: float = 5.0,
) -> dict | None:
    items, _ = await list_investigations(session, page=1, page_size=200)
    best = None
    best_d = None
    for i in items:
        d = _haversine_km(lat, lon, float(i["latitude"]), float(i["longitude"]))
        if d <= max_km and (best_d is None or d < best_d):
            best, best_d = i, d
    if not best:
        return None
    out = _summary(best)
    out["distance_km"] = round(best_d or 0.0, 3)
    out["full"] = best
    return out


async def create_investigation(session: AsyncSession | None, payload: dict) -> dict:
    if not is_db_ready() or session is None:
        gid = str(uuid4())
        item = {
            **deepcopy(payload),
            "id": gid,
            "geotech_id": gid,
            "is_active": True,
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
            "source": "mock",
        }
        _MOCK_GEOTECH.append(item)
        return item

    row = GeotechInvestigation(
        site_code=payload["site_code"],
        site_name=payload["site_name"],
        project_name=payload.get("project_name"),
        client_name=payload.get("client_name"),
        purpose=payload.get("purpose"),
        region=payload.get("region"),
        latitude=payload["latitude"],
        longitude=payload["longitude"],
        investigation_depth_m=payload.get("investigation_depth_m", 2.0),
        groundwater_note=payload.get("groundwater_note"),
        soil_layers=payload.get("soil_layers") or [],
        design_params=payload.get("design_params") or {},
        sbc_by_depth=payload.get("sbc_by_depth") or [],
        pile_capacities=payload.get("pile_capacities") or [],
        cbr_by_depth=payload.get("cbr_by_depth") or [],
        resistivity=payload.get("resistivity") or {},
        recommendations=payload.get("recommendations") or {},
        remarks=payload.get("remarks"),
        is_active=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _row_to_dict(row)


async def update_investigation(session: AsyncSession | None, geotech_id: str, payload: dict) -> dict | None:
    if not is_db_ready() or session is None:
        for i, item in enumerate(_MOCK_GEOTECH):
            if item.get("id") == geotech_id or item.get("geotech_id") == geotech_id:
                updated = {**item, **deepcopy(payload), "updated_at": _now().isoformat()}
                _MOCK_GEOTECH[i] = updated
                return updated
        return None

    try:
        uid = UUID(geotech_id)
    except ValueError:
        return None
    row = await session.get(GeotechInvestigation, uid)
    if not row or not row.is_active:
        return None

    for key in (
        "site_code",
        "site_name",
        "project_name",
        "client_name",
        "purpose",
        "region",
        "latitude",
        "longitude",
        "investigation_depth_m",
        "groundwater_note",
        "soil_layers",
        "design_params",
        "sbc_by_depth",
        "pile_capacities",
        "cbr_by_depth",
        "resistivity",
        "recommendations",
        "remarks",
    ):
        if key in payload and payload[key] is not None:
            setattr(row, key, payload[key])

    await session.commit()
    await session.refresh(row)
    return _row_to_dict(row)


async def delete_investigation(session: AsyncSession | None, geotech_id: str) -> bool:
    if not is_db_ready() or session is None:
        for i, item in enumerate(_MOCK_GEOTECH):
            if item.get("id") == geotech_id or item.get("geotech_id") == geotech_id:
                _MOCK_GEOTECH[i]["is_active"] = False
                return True
        return False

    try:
        uid = UUID(geotech_id)
    except ValueError:
        return False
    row = await session.get(GeotechInvestigation, uid)
    if not row:
        return False
    row.is_active = False
    await session.commit()
    return True


def build_report_html(item: dict) -> str:
    """Generate a printable HTML geotech report from stored investigation data."""
    layers = item.get("soil_layers") or []
    sbc = item.get("sbc_by_depth") or []
    piles = item.get("pile_capacities") or []
    cbr = item.get("cbr_by_depth") or []
    res = item.get("resistivity") or {}
    rec = item.get("recommendations") or {}
    dp = item.get("design_params") or {}

    def esc(v) -> str:
        return str(v if v is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    layer_rows = "".join(
        f"<tr><td>{esc(L.get('depth_from_m'))}–{esc(L.get('depth_to_m'))}</td>"
        f"<td>{esc(L.get('gravel_pct'))}</td><td>{esc(L.get('sand_pct'))}</td>"
        f"<td>{esc(L.get('silt_pct'))}</td><td>{esc(L.get('clay_pct'))}</td>"
        f"<td>{esc(L.get('ll'))}</td><td>{esc(L.get('pl'))}</td><td>{esc(L.get('pi'))}</td>"
        f"<td>{esc(L.get('soil_class'))}</td><td>{esc(L.get('mdd'))}</td>"
        f"<td>{esc(L.get('omc'))}</td><td>{esc(L.get('dry_density'))}</td>"
        f"<td>{esc(L.get('fsi'))}</td><td>{esc(L.get('bulk_density'))}</td>"
        f"<td>{esc(L.get('ucs'))}</td><td>{esc(L.get('sg'))}</td>"
        f"<td>{esc(L.get('sbc'))}</td><td>{esc(L.get('cbr'))}</td>"
        f"<td>{esc(L.get('remarks'))}</td></tr>"
        for L in layers
    )
    sbc_rows = "".join(
        f"<tr><td>{esc(r.get('depth_m'))}{' (Design)' if r.get('design') else ''}</td>"
        f"<td>{esc(r.get('sbc_tm2'))}</td></tr>"
        for r in sbc
    )
    pile_rows = "".join(
        f"<tr><td>{esc(p.get('diameter_mm'))} mm</td><td>{esc(p.get('depth_m'))} m</td>"
        f"<td>{esc(p.get('vertical_t'))}</td><td>{esc(p.get('uplift_t'))}</td>"
        f"<td>{esc(p.get('lateral_t'))}</td></tr>"
        for p in piles
    )
    cbr_rows = "".join(
        f"<tr><td>{esc(c.get('depth_from_m'))}–{esc(c.get('depth_to_m'))}</td>"
        f"<td>{esc(c.get('soil_type'))}</td><td>{esc(c.get('cbr_pct'))}</td></tr>"
        for c in cbr
    )
    res_layers = res.get("layers") or []
    res_rows = "".join(
        f"<tr><td>{esc(r.get('depth_from_m'))}–{esc(r.get('depth_to_m'))}</td>"
        f"<td>{esc(r.get('soil_type'))}</td><td>{esc(r.get('resistivity_ohm_m'))}</td></tr>"
        for r in res_layers
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<title>Geotech Report — {esc(item.get('site_code'))}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1a1a1a}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:22px 0 8px;border-bottom:2px solid #0f766e;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;font-size:11px;margin:8px 0 16px}}
th,td{{border:1px solid #cbd5e1;padding:4px 6px;text-align:left}} th{{background:#ecfdf5}}
.meta{{font-size:13px;line-height:1.5}} .badge{{display:inline-block;background:#0f766e;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px}}
@media print{{body{{margin:12px}}}}
</style></head><body>
<h1>Geotechnical Investigation Report</h1>
<p class="meta"><span class="badge">{esc(item.get('site_code'))}</span>
<strong>{esc(item.get('site_name'))}</strong><br/>
Project: {esc(item.get('project_name'))} · Client: {esc(item.get('client_name'))}<br/>
Purpose: {esc(item.get('purpose'))}<br/>
Region: {esc(item.get('region'))}<br/>
Coordinates: {esc(item.get('latitude'))}°N, {esc(item.get('longitude'))}°E<br/>
Investigation depth: {esc(item.get('investigation_depth_m'))} m · GWT: {esc(item.get('groundwater_note'))}</p>

<h2>1. Soil Test Summary</h2>
<table><thead><tr>
<th>Depth (m)</th><th>Gravel%</th><th>Sand%</th><th>Silt%</th><th>Clay%</th>
<th>LL</th><th>PL</th><th>PI</th><th>Class</th><th>MDD</th><th>OMC</th>
<th>Dry dens.</th><th>FSI</th><th>Bulk dens.</th><th>UCS</th><th>SG</th><th>SBC</th><th>CBR</th><th>Remarks</th>
</tr></thead><tbody>{layer_rows or '<tr><td colspan="19">No layers</td></tr>'}</tbody></table>

<h2>2. Engineering Analysis — SBC (IS 6403)</h2>
<p class="meta">Foundation: {esc(dp.get('foundation_type'))} · Df = {esc(dp.get('df_m'))} m · FoS = {esc(dp.get('fos_shear'))}<br/>
Adopted c = {esc(dp.get('c_tm2'))} T/m² · φ = {esc(dp.get('phi_deg'))}° · γ = {esc(dp.get('gamma_tm3'))} T/m³<br/>
<strong>Adopted Net SBC = {esc(rec.get('adopted_sbc_tm2'))} T/m² at {esc(rec.get('design_depth_m'))} m</strong>
· Settlement = {esc(rec.get('settlement_mm'))} mm ({esc(rec.get('settlement_status'))})</p>
<table><thead><tr><th>Depth (m)</th><th>SBC (T/m²)</th></tr></thead><tbody>{sbc_rows}</tbody></table>

<h2>3. Pile Foundation Capacities (IS 2911)</h2>
<table><thead><tr><th>Diameter</th><th>Depth</th><th>Vertical (T)</th><th>Uplift (T)</th><th>Lateral (T)</th></tr></thead>
<tbody>{pile_rows}</tbody></table>
<p class="meta">{esc(rec.get('recommended_pile'))}</p>

<h2>4. California Bearing Ratio (CBR)</h2>
<table><thead><tr><th>Depth (m)</th><th>Soil Type</th><th>CBR (%)</th></tr></thead><tbody>{cbr_rows}</tbody></table>
<p class="meta">Governing design CBR = <strong>{esc(rec.get('governing_cbr_pct'))}%</strong></p>

<h2>5. Earth Resistivity (IS 3043)</h2>
<p class="meta">Method: {esc(res.get('method'))} · Formula: {esc(res.get('formula'))}<br/>
Adopted design resistivity = <strong>{esc(res.get('adopted_ohm_m'))} Ω·m</strong>
· Target earth resistance ≤ {esc(res.get('target_earth_resistance_ohm'))} Ω
· Earthing: {esc(res.get('earthing_type'))} · Pit depth {esc(res.get('pit_depth_m'))} m</p>
<table><thead><tr><th>Depth (m)</th><th>Soil</th><th>Resistivity (Ω·m)</th></tr></thead><tbody>{res_rows}</tbody></table>

<p class="meta" style="margin-top:28px;color:#64748b">Generated by TAMS Geotech Module · {esc(_now().isoformat())}<br/>
{esc(item.get('remarks'))}</p>
</body></html>"""


async def ensure_nirona_seed(session: AsyncSession | None) -> None:
    """Ensure Nirona seed exists in DB when empty (called optionally on first list)."""
    if not is_db_ready() or session is None:
        return
    count = await session.scalar(select(func.count()).select_from(GeotechInvestigation))
    if count and count > 0:
        return
    await create_investigation(session, deepcopy(NIRONA_SEED))
