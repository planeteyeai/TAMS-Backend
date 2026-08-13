"""
Load transmission assets from indian_KML state packs (Gujarat + Rajasthan, …).

Integrated into:
  - mock_data.MOCK_ASSETS (lines + substations at startup)
  - asset_service.list_assets (state / bbox / include_towers filters)
  - gis_service.get_towers_in_bbox (viewport tower loading for the map)
"""

from __future__ import annotations

import logging
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

KML_ROOT = Path(__file__).resolve().parents[2] / "indian_KML"
# Legacy single-dir alias (Gujarat pack)
KML_DIR = KML_ROOT / "Towers_KML"

# (south, west, north, east)
INDIA_BOUNDS = (6.5, 68.0, 35.5, 97.5)

STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    # Delhi first so NCR points are not swallowed by surrounding Haryana bbox
    # Values: (south, west, north, east) — padded to full geographic state extents
    "Delhi": (28.40, 76.84, 28.88, 77.35),
    "Andhra Pradesh": (12.60, 76.75, 19.92, 84.75),
    "Arunachal Pradesh": (26.55, 91.55, 29.45, 97.42),
    "Assam": (24.10, 89.70, 27.98, 96.02),
    "Bihar": (24.20, 83.30, 27.55, 88.30),
    "Chhattisgarh": (17.78, 80.24, 24.12, 84.40),
    "Goa": (14.53, 73.68, 15.80, 74.35),
    "Gujarat": (20.10, 68.10, 24.70, 74.50),
    "Haryana": (27.65, 74.45, 30.95, 77.60),
    "Himachal Pradesh": (30.38, 75.55, 33.25, 79.07),
    "Jharkhand": (21.95, 83.28, 25.35, 87.98),
    "Karnataka": (11.50, 74.05, 18.47, 78.59),
    "Kerala": (8.17, 74.85, 12.80, 77.40),
    "Madhya Pradesh": (21.00, 74.00, 26.90, 82.80),
    "Maharashtra": (15.60, 72.60, 22.10, 80.90),
    "Manipur": (23.80, 93.00, 25.70, 94.80),
    "Meghalaya": (25.00, 89.80, 26.10, 92.80),
    "Mizoram": (21.90, 92.20, 24.50, 93.40),
    "Nagaland": (25.20, 93.30, 27.00, 95.30),
    "Odisha": (17.80, 81.30, 22.60, 87.50),
    "Punjab": (29.50, 73.80, 32.50, 76.90),
    "Rajasthan": (23.00, 69.30, 30.20, 78.20),
    "Sikkim": (27.00, 88.00, 28.20, 88.90),
    "Tamil Nadu": (8.00, 76.20, 13.60, 80.40),
    "Telangana": (15.80, 77.20, 19.90, 81.30),
    "Tripura": (22.90, 91.20, 24.50, 92.30),
    "Uttar Pradesh": (23.70, 77.00, 30.40, 84.60),
    "Uttarakhand": (28.70, 77.50, 31.50, 81.00),
    "West Bengal": (21.50, 85.80, 27.20, 89.90),
}

LINE_GLOBS = [
    "*_voltage_line.kml",
    "substation_Line.kml",
    "Portal_Line.kml",
    "Portal_L.kml",
    "Transformar_Line.kml",
    "Transformer_LIne.kml",
    "Transformer_L.kml",
    "Unidentified_voltage_line.kml",
    # Multi-state pack naming
    "*kv.kml",
    "*Kv.kml",
    "*KV.kml",
    "* kv.kml",
    "Minor_lines.kml",
    "Minor_Lines.kml",
    "Minor_Line.kml",
    "Minor_Liner.kml",
    "Substation_L.kml",
    "Cable.kml",
    "Power_Plant_lIne.kml",
    "Power_Plant_L.kml",
    "power_plant_L.kml",
    "power_Plant_Line.kml",
    "Generator_LINE.kml",
    "Generator_LIne.kml",
    "PGCIL_Line.kml",
    "Unindetifeid_Line.kml",
    "Unindentified_Line.kml",
    "Unindentified_Lines.kml",
    "Unidentified_Line.kml",
    "Unidentified_Lines.kml",
    "Unidentified_LINES.kml",
    "unidentified_lines.kml",
    "Unidentified Lines.kml",  # Sikkim
    "Unidentified_lines.kml",
    "Undentifeiad_Line.kml",  # Andhra typo
    "Undentified-Lines.kml",  # West Bengal typo
    "Onidentified_Line.kml",  # Jharkhand typo
    "Unidentifier=d_Lines.kml",  # Mizoram typo
    "minor_line.kml",
    "cable.kml",
    "cabler.kml",
    "*kvv.kml",
    "*klv.kml",
    # Dense state packs (Kerala etc.) — full corridor catch-all
    "line.kml",
    "Line.kml",
    "lines.kml",
    "Lines.kml",
]

# Prefer named voltage files; skip mega "ALL Lines" when siblings exist (dedupe by osm_id anyway).
LINE_SKIP_NAMES = {
    "all lines.kml",
    "all polygon.kml",
    "all_line.kml",
    # Kerala line.kml is the dense corridor pack — do NOT skip (voltage files alone are incomplete)
    "mh.kml",
    "chhatisgadh.kml",  # tiny 1-placemark stub
    "telangana.kmz",
}

TOWER_FILES = [
    "Towers Locations.kml",
    "Tower_Locations.kml",
    "tower_Locations.kml",
    "Tower_locations.kml",
    "Tower_Location.kml",  # Sikkim
    "Tower_Locatins.kml",  # Assam typo
    "Tower_Locarions.kml",  # Telangana typo
    "Towers_locations.kml",  # Goa
    "points.kml",  # Kerala dense point pack (towers/poles)
    "Points.kml",
    "transsmition_Towers.kml",  # Rajasthan spelling
    "transmission_Towers.kml",
    "Transmitions_Towers.kml",  # Uttarakhand spelling
    "Transmition_tower_Locations.kml",  # Maharashtra spelling
    "Pole.kml",
    "pole.kml",
]
SUBSTATION_FILES = [
    "substation.kml",
    "Substation.kml",
    "SubStation.kml",
    "Substations.kml",
    "substations.kml",
    "substationss.kml",
    "Substationss.kml",
    "Sub_Stations.kml",
    "Substaions.kml",  # Tamil Nadu typo
    "substaions.kml",
    "Substaion.kml",  # Arunachal typo
    "Substaion_KML.kml",  # Uttarakhand typo
    "Subsations_Points.kml",  # Kerala typo
    "Subsation.kml",  # UP typo
    "Subsations.kml",
    "Power_Plant.kml",
    "Power_plant.kml",
    "power_plant.kml",
    "power_Plant.kml",
    "Power_Plants.kml",
    "Power_plants.kml",
    "power_plants.kml",
    "power_Plants.kml",
    "Power_Plantss.kml",
    "PowerPLants.kml",
    "Power-plant.kml",
    "Plant.kml",
    "Portal.kml",
    "portal.kml",
    "POrtal.kml",
    "Portals.kml",
    "portals.kml",
    "portalS.kml",
    "Portal_Point.kml",
    "Transformar.kml",
    "Transformer.kml",
    "transformer.kml",
    "tRANSFORMER.kml",
    "Transformers.kml",
    "transformers.kml",
    "transformer_Point.kml",
    "Transformer_points.kml",
    "Substation_Points.kml",
    "Substation_P.kml",
    "Substation_Polygon.kml",
    "Substation_POLYGON.kml",
    "Generator_PO.kml",
    "Generator_point.kml",
    "Generator.kml",
    "Generators.kml",
    "generators.kml",
    "Generatorr.kml",
    "generatorss.kml",
    "Generatorss.kml",
    "generator.kml",
    "Genenrator.kml",  # Sikkim typo
    "Power_Plant_Point.kml",
    "Terminal.kml",
    "terminal.kml",
    "switchgear.kml",
    "Switchgear.kml",
    "SwitchGear.kml",
    "Switch_Gear.kml",
    "Swichgear.kml",
    "switch.kml",
    "Switch.kml",
]

# Folder name → forced state label (more reliable than bbox for NCR overlaps)
DIR_STATE_HINTS: dict[str, str] = {
    # Legacy Gujarat pack (folder is not named Gujarat_KML)
    "Towers_KML": "Gujarat",
    "Delhi_KML": "Delhi",
    "Haryana_KML": "Haryana",
    "Punjab_KML": "Punjab",
    "Rajasthan_KML": "Rajasthan",
    "Himachal_Pradesh_KML": "Himachal Pradesh",
    "Uttarakhand_KML": "Uttarakhand",
    "Karnataka_KML": "Karnataka",
    "Kerala_KML": "Kerala",
    "Madhya_Pradesh_KML": "Madhya Pradesh",
    "Maharashtra_KML": "Maharashtra",
    "Tamil_Nadu_KML": "Tamil Nadu",
    "Assam_KML": "Assam",
    "Andhra_Pradesh_KML": "Andhra Pradesh",
    "Bihar_KML": "Bihar",
    "Goa_KML": "Goa",
    "Jharkhand_KML": "Jharkhand",
    "Odisha_KML": "Odisha",
    "Sikkim_KML": "Sikkim",
    "Arunachal_Pradesh_KML": "Arunachal Pradesh",
    "Chhattisgarh_KML": "Chhattisgarh",
    "Manipur_KML": "Manipur",
    "Meghalaya_KML": "Meghalaya",
    "Mizoram_KML": "Mizoram",
    "Nagaland_KML": "Nagaland",
    "Telangana_KML": "Telangana",
    "Tripura_KML": "Tripura",
    "Uttar_Pradesh_KML": "Uttar Pradesh",
    "West_Bengal_KML": "West Bengal",
}

# States whose corridor packs have been merged into MOCK_ASSETS / caches
_loaded_corridor_states: set[str] = set()
_state_merge_lock = threading.Lock()
# When set, only parse KML dirs mapped to this state (speeds up per-state upsert).
_STATE_DIR_FILTER: str | None = None


def ensure_state_corridor_loaded(state: str | None) -> None:
    """Lazy-load one state pack into MOCK_ASSETS when Places selects it."""
    if not state or state.lower() in ("india", "all"):
        return
    label = state.strip()
    # Normalize to canonical STATE_BOUNDS key
    canonical = None
    for name in STATE_BOUNDS:
        if name.lower() == label.lower():
            canonical = name
            break
    if not canonical:
        return
    if canonical in _loaded_corridor_states:
        return

    with _state_merge_lock:
        if canonical in _loaded_corridor_states:
            return
        prev_filter = _STATE_DIR_FILTER
        try:
            from app.services import mock_data

            set_state_dir_filter(canonical)
            # Force parse this pack (ignore mock fallback)
            global _cache
            saved_lines, saved_subs = _cache["lines"], _cache["substations"]
            _cache["lines"] = None
            _cache["substations"] = None
            chunk = _load_lines() + _load_substations()
            seen = {a["id"] for a in mock_data.MOCK_ASSETS}
            added = 0
            for asset in chunk:
                if asset["id"] in seen:
                    continue
                seen.add(asset["id"])
                mock_data.MOCK_ASSETS.append(asset)
                added += 1
            # Restore combined corridor caches from MOCK_ASSETS
            _cache["lines"] = [
                a for a in mock_data.MOCK_ASSETS if a.get("asset_type") == "line"
            ]
            _cache["substations"] = [
                a for a in mock_data.MOCK_ASSETS if a.get("asset_type") == "substation"
            ]
            _loaded_corridor_states.add(canonical)
            logger.info(
                "On-demand loaded %s corridor (+%d, mock total %d)",
                canonical,
                added,
                len(mock_data.MOCK_ASSETS),
            )
        except Exception:
            logger.exception("On-demand load failed for %s", canonical)
            _cache["lines"] = saved_lines
            _cache["substations"] = saved_subs
        finally:
            set_state_dir_filter(prev_filter)


def mark_corridor_state_loaded(state: str) -> None:
    _loaded_corridor_states.add(state)


def set_state_dir_filter(state: str | None) -> None:
    """Restrict KML directory iteration to one state pack (or clear with None)."""
    global _STATE_DIR_FILTER
    _STATE_DIR_FILTER = state


def _iter_kml_dirs() -> list[Path]:
    dirs: list[Path] = []
    if KML_DIR.is_dir():
        dirs.append(KML_DIR)
    if KML_ROOT.is_dir():
        for child in sorted(KML_ROOT.iterdir()):
            if child.is_dir() and child.name != "Towers_KML" and child not in dirs:
                dirs.append(child)
    if not _STATE_DIR_FILTER:
        return dirs
    needle = _STATE_DIR_FILTER.lower()
    filtered: list[Path] = []
    for d in dirs:
        hinted = DIR_STATE_HINTS.get(d.name)
        if hinted and hinted.lower() == needle:
            filtered.append(d)
        elif d.name == "Towers_KML" and needle == "gujarat":
            filtered.append(d)
    return filtered

_NOW = datetime.now(timezone.utc)

_cache: dict[str, Any] = {
    "lines": None,
    "substations": None,
    "towers": None,
    "tower_counts": {},
    "tower_grid": None,  # coarse spatial index: (ilat, ilon) -> list[tower]
    "tower_states_loaded": set(),  # avoid re-parsing the same state KML pack
}

_tower_load_lock = threading.Lock()
_lines_load_lock = threading.Lock()
_subs_load_lock = threading.Lock()
_TOWER_GRID_DEG = 0.25  # ~28 km cells


def _grid_key(lat: float, lon: float) -> tuple[int, int]:
    return (int(math.floor(lat / _TOWER_GRID_DEG)), int(math.floor(lon / _TOWER_GRID_DEG)))


def _boxes_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Boxes as (min_lat, min_lon, max_lat, max_lon)."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _states_intersecting_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> set[str]:
    """Prefer states that contain the viewport centre (avoids mega-bboxes like AP)."""
    mid_lat = (min_lat + max_lat) / 2.0
    mid_lon = (min_lon + max_lon) / 2.0
    containing = {
        name
        for name, box in STATE_BOUNDS.items()
        if _in_box(mid_lat, mid_lon, box)
    }
    if containing:
        # If multiple (NCR / border overlaps), keep the 2 smallest by area
        ranked = sorted(
            containing,
            key=lambda n: (
                (STATE_BOUNDS[n][2] - STATE_BOUNDS[n][0])
                * (STATE_BOUNDS[n][3] - STATE_BOUNDS[n][1])
            ),
        )
        return set(ranked[:2])
    q = (min_lat, min_lon, max_lat, max_lon)
    return {name for name, box in STATE_BOUNDS.items() if _boxes_intersect(q, box)}


def _build_tower_grid(towers: list[dict[str, Any]]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    grid: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for t in towers:
        key = _grid_key(float(t["latitude"]), float(t["longitude"]))
        grid.setdefault(key, []).append(t)
    return grid


def clear_kml_cache() -> None:
    """Drop in-memory KML caches so new state packs are re-parsed."""
    _cache["lines"] = None
    _cache["substations"] = None
    _cache["towers"] = None
    _cache["tower_grid"] = None
    _cache["tower_counts"] = {}
    _cache["tower_states_loaded"] = set()
    logger.info("Cleared indian_KML in-memory caches")

PLACE_ID_TO_STATE: dict[str, str | None] = {
    "india": None,
    "andhra-pradesh": "Andhra Pradesh",
    "arunachal-pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal-pradesh": "Himachal Pradesh",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "madhya-pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil-nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar-pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "west-bengal": "West Bengal",
    "delhi": "Delhi",
}

CITY_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    # (south, west, north, east) — keep in sync with frontend places.ts city children
    "ahmedabad": (22.95, 72.5, 23.15, 72.65),
    "surat": (21.1, 72.7, 21.25, 73.0),
    "vadodara": (22.25, 73.1, 22.4, 73.25),
    "rajkot": (22.25, 70.7, 22.4, 70.85),
    "bhavnagar": (21.7, 72.1, 21.85, 72.2),
    "gandhinagar": (23.15, 72.60, 23.28, 72.72),
    "jamnagar": (22.42, 69.98, 22.55, 70.15),
    "mumbai": (18.89, 72.75, 19.27, 73.05),
    "pune": (18.4, 73.7, 18.65, 74.0),
    "nagpur": (20.9, 78.9, 21.3, 79.2),
    "nashik": (19.95, 73.70, 20.10, 73.90),
    "aurangabad": (19.80, 75.25, 19.95, 75.45),
    "thane": (19.15, 72.90, 19.30, 73.10),
    "visakhapatnam": (17.65, 83.15, 17.85, 83.45),
    "vijayawada": (16.45, 80.55, 16.60, 80.75),
    "itanagar": (27.05, 93.55, 27.15, 93.70),
    "guwahati": (26.05, 91.55, 26.25, 91.90),
    "patna": (25.55, 85.00, 25.70, 85.25),
    "raipur": (21.15, 81.55, 21.35, 81.75),
    "panaji": (15.45, 73.78, 15.55, 73.90),
    "gurugram": (28.35, 76.90, 28.55, 77.15),
    "faridabad": (28.35, 77.25, 28.50, 77.40),
    "shimla": (31.05, 77.10, 31.15, 77.25),
    "ranchi": (23.28, 85.25, 23.42, 85.42),
    "jamshedpur": (22.75, 86.10, 22.90, 86.30),
    "bengaluru": (12.85, 77.45, 13.15, 77.75),
    "mysuru": (12.25, 76.55, 12.40, 76.75),
    "mangaluru": (12.85, 74.78, 13.00, 74.95),
    "thiruvananthapuram": (8.45, 76.85, 8.60, 77.05),
    "kochi": (9.90, 76.20, 10.10, 76.40),
    "kozhikode": (11.20, 75.70, 11.35, 75.90),
    "bhopal": (23.15, 77.30, 23.35, 77.55),
    "indore": (22.65, 75.75, 22.85, 76.00),
    "jabalpur": (23.10, 79.85, 23.25, 80.05),
    "imphal": (24.75, 93.88, 24.85, 93.98),
    "shillong": (25.55, 91.85, 25.62, 91.95),
    "aizawl": (23.70, 92.68, 23.78, 92.78),
    "kohima": (25.64, 94.08, 25.70, 94.15),
    "bhubaneswar": (20.22, 85.75, 20.40, 85.95),
    "cuttack": (20.40, 85.80, 20.55, 85.95),
    "ludhiana": (30.85, 75.75, 31.00, 75.95),
    "amritsar": (31.58, 74.80, 31.70, 74.95),
    "jaipur": (26.80, 75.70, 27.00, 75.90),
    "jodhpur": (26.20, 72.95, 26.35, 73.10),
    "udaipur": (24.52, 73.65, 24.65, 73.80),
    "gangtok": (27.30, 88.58, 27.38, 88.65),
    "chennai": (12.90, 80.10, 13.20, 80.35),
    "coimbatore": (10.95, 76.85, 11.10, 77.05),
    "madurai": (9.85, 78.05, 10.00, 78.20),
    "hyderabad": (17.25, 78.25, 17.55, 78.60),
    "warangal": (17.90, 79.50, 18.05, 79.65),
    "agartala": (23.80, 91.25, 23.90, 91.35),
    "lucknow": (26.75, 80.85, 26.95, 81.05),
    "kanpur": (26.40, 80.25, 26.55, 80.45),
    "agra": (27.15, 77.95, 27.25, 78.10),
    "varanasi": (25.25, 82.90, 25.40, 83.05),
    "noida": (28.50, 77.30, 28.65, 77.45),
    "dehradun": (30.25, 77.95, 30.40, 78.15),
    "haridwar": (29.90, 78.10, 30.00, 78.20),
    "kolkata": (22.45, 88.20, 22.70, 88.50),
    "siliguri": (26.65, 88.35, 26.80, 88.50),
    "new-delhi": (28.55, 77.15, 28.68, 77.30),
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
    m = re.search(r"(\d+)_voltage_line", filename, flags=re.IGNORECASE)
    if m:
        v = int(m.group(1))
        return v // 1000 if v > 1000 else v
    # Rajasthan pack: 132kv.kml / 66 kv.kml / 500000Kv.kml
    m = re.search(r"(\d+)\s*kv", filename, flags=re.IGNORECASE)
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


def _parse_placemark_lines(path: Path, forced_state: str | None = None) -> list[dict[str, Any]]:
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
        state = forced_state or _detect_state_for_line(coords)
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


def _parse_placemark_points(
    path: Path, asset_type: str, forced_state: str | None = None
) -> list[dict[str, Any]]:
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

        state = forced_state or _detect_state(lat, lon)
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

    with _lines_load_lock:
        if _cache["lines"] is not None:
            return _cache["lines"]

        lines: list[dict[str, Any]] = []
        dirs = _iter_kml_dirs()
        if not dirs:
            logger.warning("KML directories not found under: %s", KML_ROOT)
            _cache["lines"] = []
            return []

        seen: set[str] = set()
        for kml_dir in dirs:
            forced = DIR_STATE_HINTS.get(kml_dir.name)
            for pattern in LINE_GLOBS:
                for path in sorted(kml_dir.glob(pattern)):
                    if path.name.lower() in LINE_SKIP_NAMES:
                        continue
                    logger.info("Parsing line KML: %s/%s", kml_dir.name, path.name)
                    for asset in _parse_placemark_lines(path, forced_state=forced):
                        if asset["id"] not in seen:
                            seen.add(asset["id"])
                            lines.append(asset)

        logger.info("Loaded %d transmission line segments from KML", len(lines))
        _cache["lines"] = lines
        return lines


def _load_substations() -> list[dict[str, Any]]:
    if _cache["substations"] is not None:
        return _cache["substations"]

    with _subs_load_lock:
        if _cache["substations"] is not None:
            return _cache["substations"]

        subs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for kml_dir in _iter_kml_dirs():
            forced = DIR_STATE_HINTS.get(kml_dir.name)
            for filename in SUBSTATION_FILES:
                path = kml_dir / filename
                if not path.is_file():
                    continue
                logger.info("Parsing substation KML: %s/%s", kml_dir.name, path.name)
                for asset in _parse_placemark_points(path, "substation", forced_state=forced):
                    if asset["id"] not in seen:
                        seen.add(asset["id"])
                        subs.append(asset)

        logger.info("Loaded %d substations from KML", len(subs))
        _cache["substations"] = subs
        return subs


def _load_towers() -> list[dict[str, Any]]:
    if _cache["towers"] is not None:
        return _cache["towers"]

    with _tower_load_lock:
        if _cache["towers"] is not None:
            return _cache["towers"]

        towers: list[dict[str, Any]] = []
        seen: set[str] = set()
        seen_paths: set[str] = set()
        found_any = False
        for kml_dir in _iter_kml_dirs():
            forced = DIR_STATE_HINTS.get(kml_dir.name)
            for filename in TOWER_FILES:
                path = kml_dir / filename
                if not path.is_file():
                    continue
                resolved = str(path.resolve()).lower()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                found_any = True
                logger.info("Parsing tower KML (this may take a moment): %s/%s", kml_dir.name, path.name)
                for asset in _parse_placemark_points(path, "tower", forced_state=forced):
                    if asset["id"] not in seen:
                        seen.add(asset["id"])
                        towers.append(asset)

        if not found_any:
            logger.warning("No tower KML files found under: %s", KML_ROOT)

        logger.info("Loaded %d towers from KML", len(towers))
        _cache["towers"] = towers
        _cache["tower_grid"] = _build_tower_grid(towers)
        return towers


def _load_towers_for_states(states: set[str]) -> list[dict[str, Any]]:
    """Parse only the KML packs for the given states — used for fast cold bbox queries."""
    if not states:
        return []
    towers: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_paths: set[str] = set()
    wanted = {s.lower() for s in states}
    for kml_dir in _iter_kml_dirs():
        forced = DIR_STATE_HINTS.get(kml_dir.name)
        if forced and forced.lower() not in wanted:
            continue
        if not forced:
            continue
        for filename in TOWER_FILES:
            path = kml_dir / filename
            if not path.is_file():
                continue
            # Windows is case-insensitive — avoid parsing the same file 3×
            resolved = str(path.resolve()).lower()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            logger.info("Fast-path tower KML: %s/%s", kml_dir.name, path.name)
            for asset in _parse_placemark_points(path, "tower", forced_state=forced):
                if asset["id"] not in seen:
                    seen.add(asset["id"])
                    towers.append(asset)
    logger.info("Fast-path loaded %d towers for states %s", len(towers), sorted(states))
    return towers


def _ensure_tower_states_loaded(states: set[str]) -> None:
    """Parse missing state packs once, then reuse the in-memory grid."""
    if not states:
        return
    with _tower_load_lock:
        loaded_states: set[str] = _cache.setdefault("tower_states_loaded", set())
        missing = {s for s in states if s not in loaded_states}
        if not missing:
            return
        loaded = _load_towers_for_states(missing)
        existing = _cache["towers"]
        if existing is None:
            _cache["towers"] = loaded
        else:
            seen = {t["id"] for t in existing}
            merged = list(existing)
            for t in loaded:
                if t["id"] not in seen:
                    seen.add(t["id"])
                    merged.append(t)
            _cache["towers"] = merged
        _cache["tower_grid"] = _build_tower_grid(_cache["towers"] or [])
        for s in missing:
            loaded_states.add(s)
            st = s.lower()
            _cache["tower_counts"][s] = sum(
                1
                for t in loaded
                if str((t.get("metadata") or {}).get("country_or_state", "")).lower() == st
            )
        logger.info(
            "Tower cache now has %d towers (states loaded: %s)",
            len(_cache["towers"] or []),
            sorted(loaded_states),
        )


def preload_kml_assets(*, warm_towers: bool = True) -> None:
    """Warm corridor caches at application startup.

    Tower warm is Gujarat-scoped only — national parse is on-demand via /gis/towers
    fast-path so the API event loop stays responsive.
    """
    _load_lines()
    _load_substations()
    if not warm_towers:
        return

    def _warm_priority() -> None:
        try:
            _ensure_tower_states_loaded({"Gujarat"})
            with _tower_load_lock:
                n = len(_cache["towers"] or [])
            if n:
                logger.info("Priority-warmed %d Gujarat towers", n)
        except Exception:
            logger.exception("Background Gujarat tower warm failed")

    threading.Thread(target=_warm_priority, name="kml-tower-warm", daemon=True).start()


def warmup_tower_counts() -> None:
    """Pre-compute India / known state tower totals from KML (streaming)."""
    logger.info("Counting towers from KML…")
    india = _get_tower_count_for_box(INDIA_BOUNDS)
    _cache["tower_counts"]["India"] = india
    for state in (
        "Gujarat",
        "Rajasthan",
        "Delhi",
        "Haryana",
        "Punjab",
        "Himachal Pradesh",
        "Uttarakhand",
        "Karnataka",
        "Kerala",
        "Madhya Pradesh",
        "Maharashtra",
        "Tamil Nadu",
        "Assam",
        "Andhra Pradesh",
        "Bihar",
        "Goa",
        "Jharkhand",
        "Odisha",
        "Sikkim",
        "Arunachal Pradesh",
        "Chhattisgarh",
        "Manipur",
        "Meghalaya",
        "Mizoram",
        "Nagaland",
        "Telangana",
        "Tripura",
        "Uttar Pradesh",
        "West Bengal",
    ):
        box = STATE_BOUNDS.get(state)
        if not box:
            continue
        _cache["tower_counts"][state] = _get_tower_count_for_box(box)
        logger.info("%s tower count: %d", state, _cache["tower_counts"][state])
    logger.info("India tower count: %d", india)


def _iter_tower_kml_paths() -> list[Path]:
    paths: list[Path] = []
    for kml_dir in _iter_kml_dirs():
        for filename in TOWER_FILES:
            path = kml_dir / filename
            if path.is_file():
                paths.append(path)
    return paths


def _stream_count_towers(box: tuple[float, float, float, float] | None = None) -> int:
    count = 0
    for path in _iter_tower_kml_paths():
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
    if state is None:
        return _get_tower_count_for_box(INDIA_BOUNDS)
    cached = _cache["tower_counts"].get(state)
    if cached is not None:
        return int(cached)

    # Prefer metadata count from loaded packs (bbox counts leak neighbors)
    towers = _cache.get("towers")
    if towers is not None:
        want = state.lower()
        count = sum(
            1
            for t in towers
            if str((t.get("metadata") or {}).get("country_or_state", "")).lower() == want
        )
        if count:
            _cache["tower_counts"][state] = count
            return count

    box = STATE_BOUNDS.get(state)
    if not box:
        return 0
    return _get_tower_count_for_box(box)


def _get_tower_count_for_box(box: tuple[float, float, float, float]) -> int:
    key = _box_cache_key(box)
    cached = _cache["tower_counts"].get(key)
    if cached is not None:
        return int(cached)

    # Named-state shortcut (warmup fills these)
    for state, sbox in STATE_BOUNDS.items():
        if sbox == box and state in _cache["tower_counts"]:
            return int(_cache["tower_counts"][state])

    if _cache["towers"] is not None:
        count = sum(
            1 for t in _cache["towers"] if _in_box(t["latitude"], t["longitude"], box)
        )
        _cache["tower_counts"][key] = count
        return count

    # Cold start: never stream every tower KML for stats — that blocks /assets
    # for minutes. Background warmup fills real counts later.
    return 0


def get_region_stats(
    *,
    state: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """
    Actual asset totals from KML for a region.
    bbox format: (south, west, north, east)
    """
    if state:
        ensure_state_corridor_loaded(state)
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
    # Prefer published mock pool while a background full reload is in progress —
    # otherwise callers block for minutes on a second full India parse.
    # When a state dir filter is active we must parse that pack (progressive merge).
    try:
        from app.services.mock_data import MOCK_ASSETS

        if (
            not _STATE_DIR_FILTER
            and MOCK_ASSETS
            and (_cache["lines"] is None or _cache["substations"] is None)
        ):
            return [a for a in MOCK_ASSETS if a.get("asset_type") in ("line", "substation")]
    except Exception:
        pass
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
    evenly spaced spatial sample so coverage is representative
    (not just the first N points in file order).
    """
    box = (min_lat, min_lon, max_lat, max_lon)

    if state:
        _ensure_tower_states_loaded({state})
    elif _cache["towers"] is None:
        states = _states_intersecting_bbox(min_lat, min_lon, max_lat, max_lon)
        _ensure_tower_states_loaded(states)

    with _tower_load_lock:
        grid = _cache.get("tower_grid")
        if grid is None and _cache["towers"]:
            grid = _build_tower_grid(_cache["towers"])
            _cache["tower_grid"] = grid
        grid = grid or {}

    i0, j0 = _grid_key(min_lat, min_lon)
    i1, j1 = _grid_key(max_lat, max_lon)
    if i0 > i1:
        i0, i1 = i1, i0
    if j0 > j1:
        j0, j1 = j1, j0

    state_l = state.lower() if state else None
    matched: list[dict[str, Any]] = []
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            for t in grid.get((i, j), []):
                lat, lon = t["latitude"], t["longitude"]
                if not _in_box(lat, lon, box):
                    continue
                if state_l:
                    meta = str((t.get("metadata") or {}).get("country_or_state", "")).lower()
                    if meta and meta != state_l:
                        continue
                matched.append(t)

    if len(matched) <= limit:
        return matched

    step = len(matched) / float(limit)
    return [matched[int(i * step)] for i in range(limit)]


def _asset_intersects_state(asset: dict[str, Any], state: str) -> bool:
    """Match assets to a state by pack metadata — never by overlapping rectangles.

    Bounding boxes for Indian states overlap heavily (MP/CG, RJ/GJ, etc.). Using
    geometry∩bbox as an OR rule leaks neighbor corridors into the wrong Places view.
    """
    want = state.strip().lower()
    if want in ("india", "all"):
        return True

    meta_state = str((asset.get("metadata") or {}).get("country_or_state", "")).strip().lower()
    if meta_state and meta_state not in ("unknown",):
        return meta_state == want

    # Untagged legacy rows only — prefer bbox, but never override a real state label
    box = STATE_BOUNDS.get(state)
    if not box:
        return False
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
        st = state.lower().strip()
        if st in ("india", "all"):
            items = [
                a
                for a in items
                if _in_box(a["latitude"], a["longitude"], INDIA_BOUNDS)
            ]
        else:
            items = [a for a in items if _asset_intersects_state(a, state)]
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
    if state:
        ensure_state_corridor_loaded(state)

    # Prefer already-published mock corridor so /assets does not re-parse KML.
    try:
        from app.services.mock_data import MOCK_ASSETS

        if MOCK_ASSETS and not include_towers:
            pool = list(MOCK_ASSETS)
        elif include_towers:
            pool = get_corridor_assets() + (
                _cache["towers"] if _cache["towers"] is not None else []
            )
        else:
            pool = get_corridor_assets()
    except Exception:
        pool = get_corridor_assets()
        if include_towers and _cache["towers"] is not None:
            pool = pool + _cache["towers"]

    filtered = filter_assets(pool, asset_type=asset_type, state=state, bbox=bbox, search=search)
    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]
    # Map catalog pulls large pages — thin dense LineStrings for faster JSON
    if page_size >= 400 and not include_towers:
        page_items = [_slim_asset_geometry(a) for a in page_items]
    return page_items, total


def _slim_asset_geometry(asset: dict[str, Any], *, max_pts: int = 40) -> dict[str, Any]:
    geom = asset.get("geometry")
    if not geom or geom.get("type") != "LineString":
        return asset
    coords = geom.get("coordinates") or []
    if len(coords) <= max_pts:
        return asset
    step = (len(coords) - 1) / float(max_pts - 1)
    slim = [coords[int(round(i * step))] for i in range(max_pts)]
    out = dict(asset)
    out["geometry"] = {"type": "LineString", "coordinates": slim}
    return out
