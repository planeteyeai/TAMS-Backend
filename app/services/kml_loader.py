"""
Load transmission assets from indian_KML/Towers_KML (OSM-derived Gujarat corridor data).

Integrated into:
  - mock_data.MOCK_ASSETS (lines + substations at startup)
  - asset_service.list_assets (state / bbox / include_towers filters)
  - gis_service.get_towers_in_bbox (viewport tower loading for the map)
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

KML_DIR = Path(__file__).resolve().parents[2] / "indian_KML" / "Towers_KML"

# (south, west, north, east)
INDIA_BOUNDS = (6.5, 68.0, 35.5, 97.5)

STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "Gujarat": (20.1, 68.1, 24.7, 74.5),
    "Maharashtra": (15.6, 72.6, 22.1, 80.9),
    "Rajasthan": (23.0, 69.3, 30.2, 78.2),
    "Karnataka": (11.5, 74.0, 18.5, 78.6),
    "Telangana": (15.8, 77.2, 19.9, 81.3),
    "Tamil Nadu": (8.0, 76.2, 13.6, 80.4),
    "Uttar Pradesh": (23.7, 77.0, 30.4, 84.6),
    "Delhi": (28.4, 76.8, 28.9, 77.4),
    "Madhya Pradesh": (21.0, 74.0, 26.9, 82.8),
    "West Bengal": (21.5, 85.8, 27.2, 89.9),
    "Andhra Pradesh": (12.6, 76.7, 19.9, 84.8),
    "Kerala": (8.0, 74.8, 12.8, 77.4),
    "Punjab": (29.5, 73.8, 32.5, 76.9),
    "Bihar": (24.3, 83.3, 27.5, 88.3),
    "Odisha": (17.8, 81.3, 22.6, 87.5),
    "Assam": (24.1, 89.7, 28.0, 96.0),
    "Jharkhand": (22.0, 83.3, 25.3, 87.9),
    "Chhattisgarh": (17.8, 80.2, 24.1, 84.4),
}

LINE_GLOBS = [
    "*_voltage_line.kml",
    "substation_Line.kml",
    "Portal_Line.kml",
    "Transformar_Line.kml",
    "Unidentified_voltage_line.kml",
]

TOWER_FILE = "Towers Locations.kml"
SUBSTATION_FILES = ["substation.kml", "Power_Plant.kml", "Portal.kml", "Transformar.kml"]

_NOW = datetime.now(timezone.utc)

_cache: dict[str, Any] = {
    "lines": None,
    "substations": None,
    "towers": None,
    "tower_counts": {},
}

PLACE_ID_TO_STATE: dict[str, str | None] = {
    "india": None,
    "gujarat": "Gujarat",
    "maharashtra": "Maharashtra",
    "rajasthan": "Rajasthan",
    "karnataka": "Karnataka",
    "telangana": "Telangana",
    "tamil-nadu": "Tamil Nadu",
    "uttar-pradesh": "Uttar Pradesh",
    "delhi": "Delhi",
    "madhya-pradesh": "Madhya Pradesh",
    "west-bengal": "West Bengal",
}

CITY_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "ahmedabad": (22.95, 72.5, 23.15, 72.65),
    "surat": (21.1, 72.7, 21.25, 73.0),
    "vadodara": (22.25, 73.1, 22.4, 73.25),
    "rajkot": (22.25, 70.7, 22.4, 70.85),
    "bhavnagar": (21.7, 72.1, 21.85, 72.2),
    "mumbai": (18.89, 72.75, 19.27, 73.05),
    "pune": (18.4, 73.7, 18.65, 74.0),
    "nagpur": (20.9, 78.9, 21.3, 79.2),
}


def _strip_ns(tag: str) -> str:
    return re.sub(r"\{[^}]+\}", "", tag)


def _in_box(lat: float, lon: float, box: tuple[float, float, float, float]) -> bool:
    south, west, north, east = box
    return south <= lat <= north and west <= lon <= east


def _detect_state_for_line(coords: list[tuple[float, float]]) -> str:
    for state, box in STATE_BOUNDS.items():
        if _line_intersects_box(coords, box):
            return state
    if any(_in_box(lat, lon, INDIA_BOUNDS) for lon, lat in coords):
        return "India"
    return "Unknown"


def _detect_state(lat: float, lon: float) -> str:
    for state, box in STATE_BOUNDS.items():
        if _in_box(lat, lon, box):
            return state
    if _in_box(lat, lon, INDIA_BOUNDS):
        return "India"
    return "Unknown"


def _parse_voltage_kv(props: dict[str, str], filename: str = "") -> int | None:
    raw = props.get("voltage") or props.get("voltage_kv") or ""
    if raw:
        try:
            v = int(float(raw))
            return v // 1000 if v > 1000 else v
        except ValueError:
            pass
    m = re.search(r"(\d+)_voltage_line", filename)
    if m:
        v = int(m.group(1))
        return v // 1000 if v > 1000 else v
    return None


# Realistic Indian grid substation voltage mix (more 132/220 than 765).
_SUBSTATION_CLASSES = [765, 400, 400, 220, 220, 220, 132, 132, 132, 66]


def _infer_substation_voltage(osm_id: str) -> int:
    """Deterministic voltage class for substations that lack a parsed voltage."""
    h = 0
    for ch in str(osm_id):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _SUBSTATION_CLASSES[h % len(_SUBSTATION_CLASSES)]


def _parse_simple_data(placemark: ET.Element) -> dict[str, str]:
    props: dict[str, str] = {}
    for child in placemark.iter():
        if _strip_ns(child.tag) == "SimpleData":
            name = child.attrib.get("name")
            if name:
                props[name] = (child.text or "").strip()
    return props


def _get_name(placemark: ET.Element, props: dict[str, str], fallback: str) -> str:
    for child in placemark:
        if _strip_ns(child.tag) == "name" and (child.text or "").strip():
            return child.text.strip()
    return props.get("ref") or props.get("name_en") or fallback


def _parse_coord_tokens(coord_str: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for token in coord_str.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                pairs.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return pairs


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _line_length_km(coords: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        total += _haversine_km(lat1, lon1, lat2, lon2)
    return round(total, 3)


def _line_intersects_box(coords: list[tuple[float, float]], box: tuple[float, float, float, float]) -> bool:
    return any(_in_box(lat, lon, box) for lon, lat in coords)


def _centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _asset_id(kind: str, osm_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", osm_id) or "unknown"
    return f"kml-{kind}-{safe}"


def _base_asset(
    *,
    asset_id: str,
    name: str,
    asset_type: str,
    lat: float,
    lon: float,
    state: str,
    props: dict[str, str],
    voltage_kv: int | None = None,
    geometry: dict | None = None,
    description: str = "",
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "region": "India",
        "country_or_state": state,
        "source": "indian_KML",
        "osm_id": props.get("osm_id"),
        "full_id": props.get("full_id"),
        "osm_type": props.get("osm_type"),
        "power": props.get("power"),
        "operator": props.get("operator") or props.get("operator_w") or props.get("operator_s"),
        "cables": props.get("cables"),
        "circuits": props.get("circuits"),
        "structure": props.get("structure"),
        "material": props.get("material"),
        "ref": props.get("ref"),
        "frequency": props.get("frequency"),
    }
    if voltage_kv:
        meta["voltage_kv"] = voltage_kv

    return {
        "id": asset_id,
        "name": name,
        "asset_type": asset_type,
        "latitude": lat,
        "longitude": lon,
        "status": "active",
        "health_score": "healthy",
        "description": description or f"OSM {props.get('power', asset_type)} — {state}",
        "metadata": {k: v for k, v in meta.items() if v is not None},
        "geometry": geometry,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _parse_placemark_lines(path: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    filename = path.name

    for event, elem in ET.iterparse(path, events=("end",)):
        if _strip_ns(elem.tag) != "Placemark":
            continue

        props = _parse_simple_data(elem)
        coords: list[tuple[float, float]] = []
        for child in elem.iter():
            tag = _strip_ns(child.tag)
            if tag == "coordinates" and child.text:
                parsed = _parse_coord_tokens(child.text)
                if len(parsed) >= 2:
                    coords = parsed
                    break

        if len(coords) < 2:
            elem.clear()
            continue

        if not _line_intersects_box(coords, INDIA_BOUNDS):
            elem.clear()
            continue

        lat, lon = _centroid(coords)
        state = _detect_state_for_line(coords)
        osm_id = props.get("osm_id") or props.get("full_id") or f"line-{len(assets)}"
        voltage_kv = _parse_voltage_kv(props, filename)
        name = _get_name(elem, props, f"LINE-{voltage_kv or '?'}kV-{osm_id}")
        length_km = _line_length_km(coords)

        assets.append(
            _base_asset(
                asset_id=_asset_id("line", osm_id),
                name=name,
                asset_type="line",
                lat=lat,
                lon=lon,
                state=state,
                props=props,
                voltage_kv=voltage_kv,
                geometry={"type": "LineString", "coordinates": [[lo, la] for lo, la in coords]},
                description=f"{voltage_kv or '?'} kV transmission corridor segment ({length_km} km)",
            )
        )
        assets[-1]["metadata"]["length_km"] = length_km
        elem.clear()

    return assets


def _parse_placemark_points(path: Path, asset_type: str) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []

    for event, elem in ET.iterparse(path, events=("end",)):
        if _strip_ns(elem.tag) != "Placemark":
            continue

        props = _parse_simple_data(elem)
        coords: list[tuple[float, float]] = []
        polygon_coords: list[list[tuple[float, float]]] = []

        for child in elem.iter():
            tag = _strip_ns(child.tag)
            if tag == "Point":
                for sub in child.iter():
                    if _strip_ns(sub.tag) == "coordinates" and sub.text:
                        coords = _parse_coord_tokens(sub.text)
            elif tag == "Polygon":
                for sub in child.iter():
                    if _strip_ns(sub.tag) == "coordinates" and sub.text:
                        ring = _parse_coord_tokens(sub.text)
                        if ring:
                            polygon_coords.append(ring)
            elif tag == "coordinates" and child.text:
                txt = child.text.strip()
                if " " not in txt and not polygon_coords:
                    coords = _parse_coord_tokens(txt)

        if polygon_coords:
            ring = polygon_coords[0]
            lat, lon = _centroid(ring)
            geometry = {"type": "Polygon", "coordinates": [[[lo, la] for lo, la in ring]]}
        elif coords:
            lon, lat = coords[0]
            geometry = None
        else:
            elem.clear()
            continue

        if not _in_box(lat, lon, INDIA_BOUNDS):
            elem.clear()
            continue

        state = _detect_state(lat, lon)
        osm_id = props.get("osm_id") or props.get("full_id") or f"{asset_type}-{len(assets)}"
        voltage_kv = _parse_voltage_kv(props, path.name)
        if asset_type == "substation" and not voltage_kv:
            voltage_kv = _infer_substation_voltage(osm_id)
        prefix = {"tower": "TWR", "substation": "SUB"}.get(asset_type, "AST")
        name = _get_name(elem, props, f"{prefix}-{osm_id}")

        asset = _base_asset(
            asset_id=_asset_id(asset_type, osm_id),
            name=name,
            asset_type=asset_type,
            lat=lat,
            lon=lon,
            state=state,
            props=props,
            voltage_kv=voltage_kv,
            geometry=geometry,
            description=f"{props.get('power', asset_type)} asset — {state}",
        )
        if asset_type == "substation":
            asset["metadata"]["substation_class"] = f"{voltage_kv} kV"
            if geometry:
                asset["metadata"]["transformer_count"] = 2 if (voltage_kv or 0) <= 220 else 4
        assets.append(asset)
        elem.clear()

    return assets


def _load_lines() -> list[dict[str, Any]]:
    if _cache["lines"] is not None:
        return _cache["lines"]

    lines: list[dict[str, Any]] = []
    if not KML_DIR.is_dir():
        logger.warning("KML directory not found: %s", KML_DIR)
        _cache["lines"] = []
        return []

    seen: set[str] = set()
    for pattern in LINE_GLOBS:
        for path in sorted(KML_DIR.glob(pattern)):
            logger.info("Parsing line KML: %s", path.name)
            for asset in _parse_placemark_lines(path):
                if asset["id"] not in seen:
                    seen.add(asset["id"])
                    lines.append(asset)

    logger.info("Loaded %d transmission line segments from KML", len(lines))
    _cache["lines"] = lines
    return lines


def _load_substations() -> list[dict[str, Any]]:
    if _cache["substations"] is not None:
        return _cache["substations"]

    subs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for filename in SUBSTATION_FILES:
        path = KML_DIR / filename
        if not path.is_file():
            continue
        logger.info("Parsing substation KML: %s", path.name)
        for asset in _parse_placemark_points(path, "substation"):
            if asset["id"] not in seen:
                seen.add(asset["id"])
                subs.append(asset)

    logger.info("Loaded %d substations from KML", len(subs))
    _cache["substations"] = subs
    return subs


def _load_towers() -> list[dict[str, Any]]:
    if _cache["towers"] is not None:
        return _cache["towers"]

    path = KML_DIR / TOWER_FILE
    if not path.is_file():
        logger.warning("Tower KML not found: %s", path)
        _cache["towers"] = []
        return []

    logger.info("Parsing tower KML (this may take a moment): %s", path.name)
    towers = _parse_placemark_points(path, "tower")
    logger.info("Loaded %d towers from KML", len(towers))
    _cache["towers"] = towers
    return towers


def preload_kml_assets() -> None:
    """Warm caches at application startup."""
    _load_lines()
    _load_substations()
    warmup_tower_counts()
    # Parse tower points in background so first Gujarat map request is fast.
    import threading

    def _warm_towers() -> None:
        try:
            _load_towers()
        except Exception:
            logger.exception("Background tower preload failed")

    threading.Thread(target=_warm_towers, name="kml-tower-preload", daemon=True).start()


def warmup_tower_counts() -> None:
    """Pre-compute India/Gujarat tower totals from KML (streaming)."""
    logger.info("Counting towers from KML…")
    count = _get_tower_count_for_box(INDIA_BOUNDS)
    _cache["tower_counts"]["Gujarat"] = count
    logger.info("India/Gujarat tower count: %d", count)


def _stream_count_towers(box: tuple[float, float, float, float] | None = None) -> int:
    path = KML_DIR / TOWER_FILE
    if not path.is_file():
        return 0
    count = 0
    for _event, elem in ET.iterparse(path, events=("end",)):
        if _strip_ns(elem.tag) != "coordinates":
            continue
        txt = (elem.text or "").strip()
        if not txt or " " in txt:
            elem.clear()
            continue
        parts = txt.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                if box is None or _in_box(lat, lon, box):
                    count += 1
            except ValueError:
                pass
        elem.clear()
    return count


def _box_cache_key(box: tuple[float, float, float, float]) -> str:
    return ",".join(f"{v:.4f}" for v in box)


def _get_tower_count_for_state(state: str | None) -> int:
    """Tower KML footprint is entirely within Gujarat."""
    if state is None:
        return _get_tower_count_for_box(INDIA_BOUNDS)
    if state == "Gujarat":
        return _get_tower_count_for_box(STATE_BOUNDS["Gujarat"])
    return 0


def _get_tower_count_for_box(box: tuple[float, float, float, float]) -> int:
    key = _box_cache_key(box)
    cached = _cache["tower_counts"].get(key)
    if cached is not None:
        return int(cached)

    if _cache["towers"] is not None:
        count = sum(
            1 for t in _cache["towers"] if _in_box(t["latitude"], t["longitude"], box)
        )
    else:
        count = _stream_count_towers(box)

    _cache["tower_counts"][key] = count
    return count


def get_region_stats(
    *,
    state: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """
    Actual asset totals from KML for a region.
    bbox format: (south, west, north, east)
    """
    corridor = get_corridor_assets()
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox[1], bbox[0], bbox[3], bbox[2]
        filtered = filter_assets(
            corridor,
            bbox=(min_lon, min_lat, max_lon, max_lat),
        )
        tower_count = _get_tower_count_for_box(bbox)
    elif state:
        filtered = filter_assets(corridor, state=state)
        tower_count = _get_tower_count_for_state(state)
    else:
        filtered = filter_assets(corridor)
        tower_count = _get_tower_count_for_box(INDIA_BOUNDS)

    lines = [a for a in filtered if a["asset_type"] == "line"]
    subs = [a for a in filtered if a["asset_type"] == "substation"]
    line_km = sum(float(a.get("metadata", {}).get("length_km") or 0) for a in lines)

    return {
        "towers": tower_count,
        "lines": len(lines),
        "substations": len(subs),
        "total": tower_count + len(lines) + len(subs),
        "line_km": round(line_km, 1),
        "source": "indian_KML",
    }


def get_stats_for_place(place_id: str) -> dict[str, Any]:
    if place_id in CITY_BOUNDS:
        return get_region_stats(bbox=CITY_BOUNDS[place_id])
    if place_id == "india":
        return get_region_stats()
    state = PLACE_ID_TO_STATE.get(place_id)
    if state:
        return get_region_stats(state=state)
    return get_region_stats()


def get_all_place_stats() -> dict[str, dict[str, Any]]:
    """Totals per place id for the Places menu (corridor counts + cached tower totals)."""
    place_ids = (
        ["india"]
        + [pid for pid in PLACE_ID_TO_STATE if pid != "india"]
        + list(CITY_BOUNDS.keys())
    )
    seen: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    for pid in place_ids:
        if pid in seen:
            continue
        seen.add(pid)
        if pid in CITY_BOUNDS:
            stats = get_region_stats(bbox=CITY_BOUNDS[pid])
        elif pid == "india":
            stats = get_region_stats()
        else:
            state = PLACE_ID_TO_STATE.get(pid)
            if not state:
                continue
            corridor = filter_assets(get_corridor_assets(), state=state)
            lines = [a for a in corridor if a["asset_type"] == "line"]
            subs = [a for a in corridor if a["asset_type"] == "substation"]
            tower_count = _get_tower_count_for_state(state)
            line_km = sum(float(a.get("metadata", {}).get("length_km") or 0) for a in lines)
            stats = {
                "towers": tower_count,
                "lines": len(lines),
                "substations": len(subs),
                "total": tower_count + len(lines) + len(subs),
                "line_km": round(line_km, 1),
                "source": "indian_KML",
            }
        out[pid] = {"total": stats["total"], **stats}
    return out


def get_corridor_assets() -> list[dict[str, Any]]:
    """Lines + substations for dashboard / asset list (no towers)."""
    return _load_lines() + _load_substations()


def get_towers_in_bbox(
    *,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    state: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """
    Return towers inside bbox. When more than `limit` match, return an
    evenly spaced spatial sample so Gujarat coverage is representative
    (not just the first N points in file order).
    """
    towers = _load_towers()
    box = (min_lat, min_lon, max_lat, max_lon)
    matched: list[dict[str, Any]] = []
    for t in towers:
        lat, lon = t["latitude"], t["longitude"]
        if not _in_box(lat, lon, box):
            continue
        if state and t.get("metadata", {}).get("country_or_state", "").lower() != state.lower():
            continue
        matched.append(t)

    if len(matched) <= limit:
        return matched

    # Even stride sample across the matched set (file order ≈ geographic for OSM dumps)
    step = len(matched) / float(limit)
    return [matched[int(i * step)] for i in range(limit)]


def _asset_intersects_state(asset: dict[str, Any], state: str) -> bool:
    box = STATE_BOUNDS.get(state)
    if not box:
        return str(asset.get("metadata", {}).get("country_or_state", "")).lower() == state.lower()

    meta_state = str(asset.get("metadata", {}).get("country_or_state", "")).lower()
    if meta_state == state.lower():
        return True

    geom = asset.get("geometry")
    if geom and geom.get("type") == "LineString":
        pairs = [(c[0], c[1]) for c in geom.get("coordinates", [])]
        return _line_intersects_box(pairs, box)

    lat, lon = asset.get("latitude"), asset.get("longitude")
    if lat is not None and lon is not None:
        return _in_box(lat, lon, box)
    return False


def filter_assets(
    assets: list[dict[str, Any]],
    *,
    asset_type: str | None = None,
    state: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """bbox: min_lon, min_lat, max_lon, max_lat"""
    items = assets
    if asset_type:
        items = [a for a in items if a["asset_type"] == asset_type]
    if state:
        st = state.lower()
        items = [
            a
            for a in items
            if _asset_intersects_state(a, state)
            or (st == "india" and _in_box(a["latitude"], a["longitude"], INDIA_BOUNDS))
        ]
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        box = (min_lat, min_lon, max_lat, max_lon)
        items = [a for a in items if _in_box(a["latitude"], a["longitude"], box)]
    if search:
        q = search.lower()
        items = [a for a in items if q in a["name"].lower()]
    return items


def list_kml_assets(
    *,
    asset_type: str | None = None,
    state: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    search: str | None = None,
    include_towers: bool = False,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[dict], int]:
    if include_towers:
        pool = get_corridor_assets() + _load_towers()
    else:
        pool = get_corridor_assets()

    filtered = filter_assets(pool, asset_type=asset_type, state=state, bbox=bbox, search=search)
    total = len(filtered)
    start = (page - 1) * page_size
    return filtered[start : start + page_size], total
