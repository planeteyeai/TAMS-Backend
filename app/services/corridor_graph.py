"""
Spatial corridor walk: from a detected tower, follow connected lines until
substations / dead-end endpoints. Towers that carry multiple lines are treated
as junctions — adjacency is recorded per line to neighbouring towers.

OSM KML lacks way↔node topology, so connectivity is rebuilt from shared
line endpoints + spatial snap of towers/substations onto polylines.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from typing import Any

logger = logging.getLogger(__name__)

_COORD_DECIMALS = 5
_SNAP_TOWER_M = 90.0
_SNAP_SUBSTATION_M = 180.0
_MAX_LINE_HOPS = 60
_MAX_CORRIDOR_KM = 100.0
_LINE_CELL_DEG = 0.05  # ~5 km grid for candidate lines


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _ep_key(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, _COORD_DECIMALS), round(lat, _COORD_DECIMALS))


def _line_coords(line: dict[str, Any]) -> list[tuple[float, float]]:
    geom = line.get("geometry") or {}
    raw = geom.get("coordinates") or []
    out: list[tuple[float, float]] = []
    for c in raw:
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            out.append((float(c[0]), float(c[1])))
    return out


def _dist_point_to_segment_m(
    lon: float, lat: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    lat_r = math.radians(lat)
    m_lat = 111_320.0
    m_lon = max(111_320.0 * math.cos(lat_r), 1.0)
    ax = (a[0] - lon) * m_lon
    ay = (a[1] - lat) * m_lat
    bx = (b[0] - lon) * m_lon
    by = (b[1] - lat) * m_lat
    abx, aby = bx - ax, by - ay
    ab2 = abx * abx + aby * aby
    if ab2 < 1e-6:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, (-ax * abx - ay * aby) / ab2))
    return math.hypot(ax + t * abx, ay + t * aby)


def _along_line_m(lon: float, lat: float, coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Return (min_dist_m, distance_along_polyline_m)."""
    best_d = float("inf")
    along = 0.0
    cum = 0.0
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        d = _dist_point_to_segment_m(lon, lat, a, b)
        seg = _haversine_m(a[1], a[0], b[1], b[0])
        if d < best_d:
            best_d = d
            lat_r = math.radians(lat)
            m_lat = 111_320.0
            m_lon = max(111_320.0 * math.cos(lat_r), 1.0)
            ax = (a[0] - lon) * m_lon
            ay = (a[1] - lat) * m_lat
            bx = (b[0] - lon) * m_lon
            by = (b[1] - lat) * m_lat
            abx, aby = bx - ax, by - ay
            ab2 = abx * abx + aby * aby
            t = 0.0 if ab2 < 1e-6 else max(0.0, min(1.0, (-ax * abx - ay * aby) / ab2))
            along = cum + t * seg
        cum += seg
    return best_d, along


class CorridorIndex:
    """Lightweight indexes — built once from KML caches (no full tower×line snap)."""

    def __init__(self) -> None:
        self.lines_by_id: dict[str, dict[str, Any]] = {}
        self.line_coords: dict[str, list[tuple[float, float]]] = {}
        self.line_ends: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
        self.endpoint_lines: dict[tuple[float, float], list[str]] = defaultdict(list)
        self.line_grid: dict[tuple[int, int], list[str]] = defaultdict(list)
        self.towers: list[dict[str, Any]] = []
        self.tower_grid: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        self.subs: list[dict[str, Any]] = []
        self.sub_grid: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        self._built = False

    def _cell(self, lon: float, lat: float) -> tuple[int, int]:
        return (int(math.floor(lon / _LINE_CELL_DEG)), int(math.floor(lat / _LINE_CELL_DEG)))

    def build(
        self,
        lines: list[dict[str, Any]],
        towers: list[dict[str, Any]],
        substations: list[dict[str, Any]],
    ) -> "CorridorIndex":
        self.__init__()
        for line in lines:
            lid = str(line.get("id") or "")
            coords = _line_coords(line)
            if not lid or len(coords) < 2:
                continue
            self.lines_by_id[lid] = line
            self.line_coords[lid] = coords
            start, end = _ep_key(*coords[0]), _ep_key(*coords[-1])
            self.line_ends[lid] = (start, end)
            self.endpoint_lines[start].append(lid)
            if end != start:
                self.endpoint_lines[end].append(lid)
            cells: set[tuple[int, int]] = set()
            for lon, lat in coords:
                cells.add(self._cell(lon, lat))
            for cell in cells:
                self.line_grid[cell].append(lid)

        for tw in towers:
            lat, lon = tw.get("latitude"), tw.get("longitude")
            if lat is None or lon is None:
                continue
            self.towers.append(tw)
            self.tower_grid[self._cell(float(lon), float(lat))].append(tw)

        for sub in substations:
            lat, lon = sub.get("latitude"), sub.get("longitude")
            if lat is None or lon is None:
                continue
            self.subs.append(sub)
            self.sub_grid[self._cell(float(lon), float(lat))].append(sub)

        self._built = True
        logger.info(
            "Corridor index: %s lines, %s towers, %s substations",
            len(self.lines_by_id),
            len(self.towers),
            len(self.subs),
        )
        return self

    def _nearby_cells(self, lon: float, lat: float, ring: int = 1) -> list[tuple[int, int]]:
        cx, cy = self._cell(lon, lat)
        return [(cx + dx, cy + dy) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)]

    def lines_near_point(self, lon: float, lat: float, max_m: float = 200.0) -> list[tuple[float, str, float]]:
        """Return [(dist_m, line_id, along_m), ...] for lines near the point."""
        hits: list[tuple[float, str, float]] = []
        seen: set[str] = set()
        for cell in self._nearby_cells(lon, lat, ring=1):
            for lid in self.line_grid.get(cell, []):
                if lid in seen:
                    continue
                seen.add(lid)
                coords = self.line_coords.get(lid) or []
                if len(coords) < 2:
                    continue
                d, along = _along_line_m(lon, lat, coords)
                if d <= max_m:
                    hits.append((d, lid, along))
        hits.sort(key=lambda x: x[0])
        return hits

    def towers_on_line(self, line_id: str) -> list[tuple[float, dict[str, Any]]]:
        """Towers snapped onto this line, ordered from start → end."""
        coords = self.line_coords.get(line_id) or []
        if len(coords) < 2:
            return []
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        min_lon, max_lon = min(lons) - 0.01, max(lons) + 0.01
        min_lat, max_lat = min(lats) - 0.01, max(lats) + 0.01
        # Collect towers from cells covering the line bbox
        cells: set[tuple[int, int]] = set()
        for lon, lat in coords:
            cells.update(self._nearby_cells(lon, lat, ring=1))
        found: list[tuple[float, dict[str, Any]]] = []
        seen_ids: set[str] = set()
        for cell in cells:
            for tw in self.tower_grid.get(cell, []):
                tid = str(tw.get("id") or "")
                if not tid or tid in seen_ids:
                    continue
                lat, lon = float(tw["latitude"]), float(tw["longitude"])
                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    continue
                d, along = _along_line_m(lon, lat, coords)
                if d <= _SNAP_TOWER_M:
                    seen_ids.add(tid)
                    found.append((along, tw))
        found.sort(key=lambda x: x[0])
        return found

    def substations_at_endpoint(self, ep: tuple[float, float]) -> list[dict[str, Any]]:
        lon, lat = ep
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for cell in self._nearby_cells(lon, lat, ring=1):
            for sub in self.sub_grid.get(cell, []):
                sid = str(sub.get("id") or "")
                if not sid or sid in seen:
                    continue
                d = _haversine_m(lat, lon, float(sub["latitude"]), float(sub["longitude"]))
                if d <= _SNAP_SUBSTATION_M:
                    seen.add(sid)
                    out.append(sub)
        return out

    def walk_from_tower_asset(
        self,
        tower: dict[str, Any],
        *,
        max_hops: int = _MAX_LINE_HOPS,
        max_km: float = _MAX_CORRIDOR_KM,
    ) -> dict[str, Any]:
        lat = float(tower["latitude"])
        lon = float(tower["longitude"])
        seed_id = str(tower.get("id") or "")
        seed_hits = self.lines_near_point(lon, lat, max_m=_SNAP_TOWER_M)
        if not seed_hits:
            # widen once
            seed_hits = self.lines_near_point(lon, lat, max_m=250.0)[:3]
        seed_lines = [lid for _, lid, _ in seed_hits[:4]]

        collected_lines: set[str] = set(seed_lines)
        collected_towers: dict[str, dict[str, Any]] = {seed_id: tower} if seed_id else {}
        collected_subs: dict[str, dict[str, Any]] = {}
        # tower_id → list of line ids (junctions have multiple)
        lines_at_tower: dict[str, set[str]] = defaultdict(set)
        towers_along: dict[str, list[dict[str, Any]]] = {}
        endpoints: list[dict[str, Any]] = []
        visited_eps: set[tuple[float, float]] = set()
        km_acc = 0.0

        q: deque[tuple[str, int]] = deque((lid, 0) for lid in seed_lines)

        while q:
            lid, hops = q.popleft()
            if hops > max_hops or km_acc > max_km:
                continue
            line = self.lines_by_id.get(lid)
            if not line:
                continue
            km_acc += float((line.get("metadata") or {}).get("length_km") or 0)

            along_towers = self.towers_on_line(lid)
            towers_along[lid] = [tw for _, tw in along_towers]
            for _, tw in along_towers:
                tid = str(tw.get("id") or "")
                if not tid:
                    continue
                collected_towers[tid] = tw
                lines_at_tower[tid].add(lid)
                # Junction expansion: other lines through this tower
                other_hits = self.lines_near_point(
                    float(tw["longitude"]), float(tw["latitude"]), max_m=_SNAP_TOWER_M
                )
                for _, other, _ in other_hits[:4]:
                    lines_at_tower[tid].add(other)
                    if other not in collected_lines:
                        collected_lines.add(other)
                        q.append((other, hops + 1))

            start, end = self.line_ends.get(lid, (None, None))
            for ep in (start, end):
                if ep is None or ep in visited_eps:
                    continue
                visited_eps.add(ep)
                subs = self.substations_at_endpoint(ep)
                if subs:
                    for sub in subs:
                        sid = str(sub.get("id") or "")
                        collected_subs[sid] = sub
                        endpoints.append(
                            {
                                "type": "substation",
                                "id": sid,
                                "name": sub.get("name"),
                                "latitude": sub.get("latitude"),
                                "longitude": sub.get("longitude"),
                                "line_id": lid,
                            }
                        )
                    continue

                nxt_lines = [x for x in self.endpoint_lines.get(ep, []) if x not in collected_lines]
                if not nxt_lines:
                    endpoints.append(
                        {
                            "type": "dead_end",
                            "id": f"ep-{ep[0]}-{ep[1]}",
                            "longitude": ep[0],
                            "latitude": ep[1],
                            "line_id": lid,
                        }
                    )
                    continue
                for nxt in nxt_lines:
                    collected_lines.add(nxt)
                    q.append((nxt, hops + 1))

        # Adjacency: previous/next tower on each shared line
        adjacencies: dict[str, list[dict[str, Any]]] = {}
        junction_ids: list[str] = []
        for tid, lids in lines_at_tower.items():
            if len(lids) > 1:
                junction_ids.append(tid)
            nbrs: list[dict[str, Any]] = []
            seen_nbr: set[str] = set()
            for lid in lids:
                seq = [str(t.get("id")) for t in towers_along.get(lid, []) if t.get("id")]
                if tid not in seq:
                    continue
                i = seq.index(tid)
                for j in (i - 1, i + 1):
                    if 0 <= j < len(seq) and seq[j] not in seen_nbr:
                        seen_nbr.add(seq[j])
                        nbr = collected_towers.get(seq[j]) or {}
                        nbrs.append(
                            {
                                "tower_id": seq[j],
                                "line_id": lid,
                                "name": nbr.get("name"),
                                "latitude": nbr.get("latitude"),
                                "longitude": nbr.get("longitude"),
                            }
                        )
            adjacencies[tid] = nbrs

        return {
            "seed_tower_id": seed_id,
            "towers": list(collected_towers.values()),
            "lines": [self.lines_by_id[l] for l in collected_lines if l in self.lines_by_id],
            "substations": list(collected_subs.values()),
            "adjacencies": adjacencies,
            "lines_at_tower": {k: sorted(v) for k, v in lines_at_tower.items()},
            "endpoints": endpoints,
            "junction_tower_ids": junction_ids,
            "stats": {
                "tower_count": len(collected_towers),
                "line_count": len(collected_lines),
                "substation_count": len(collected_subs),
                "junction_count": len(junction_ids),
                "endpoint_count": len(endpoints),
                "approx_km": round(km_acc, 1),
            },
        }


_INDEX: CorridorIndex | None = None


def get_corridor_index(*, force_rebuild: bool = False) -> CorridorIndex:
    global _INDEX
    if _INDEX is not None and _INDEX._built and not force_rebuild:
        return _INDEX
    from app.services.kml_loader import _load_lines, _load_substations, _load_towers

    _INDEX = CorridorIndex().build(_load_lines(), _load_towers(), _load_substations())
    return _INDEX


def walk_corridor_from_tower(
    tower: dict[str, Any],
    *,
    max_hops: int = _MAX_LINE_HOPS,
    max_km: float = _MAX_CORRIDOR_KM,
) -> dict[str, Any]:
    return get_corridor_index().walk_from_tower_asset(tower, max_hops=max_hops, max_km=max_km)


def _point_along_polyline(
    coords: list[tuple[float, float]], target_m: float
) -> tuple[float, float] | None:
    """Return lon/lat at `target_m` metres along the polyline from the start."""
    if len(coords) < 2 or target_m < 0:
        return None
    remaining = target_m
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        seg = _haversine_m(a[1], a[0], b[1], b[0])
        if seg <= 1e-3:
            continue
        if remaining <= seg:
            t = remaining / seg
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        remaining -= seg
    return coords[-1]


def detect_missing_towers_along_lines(
    *,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    known_towers: list[dict[str, Any]] | None = None,
    max_gap_m: float = 240.0,
    fill_step_m: float = 210.0,
    max_new: int = 140,
) -> list[dict[str, Any]]:
    """
    Find large gaps between towers on lines inside the viewport.

    1) Prefer real KML towers that sit on the gap but were missed by the bbox sample.
    2) Otherwise place provisional detected towers along the corridor (imagery-visible
       pylons often sit in these gaps when OSM is incomplete).

    Tuned aggressively so big lattice spans visible in imagery are less likely to be missed.
    """
    idx = get_corridor_index()
    known = list(known_towers or [])
    known_ids = {str(t.get("id")) for t in known if t.get("id")}

    # Lines that intersect the viewport bbox (via any vertex)
    line_ids: set[str] = set()
    for cell_lon in range(
        int(math.floor(min_lon / _LINE_CELL_DEG)),
        int(math.floor(max_lon / _LINE_CELL_DEG)) + 1,
    ):
        for cell_lat in range(
            int(math.floor(min_lat / _LINE_CELL_DEG)),
            int(math.floor(max_lat / _LINE_CELL_DEG)) + 1,
        ):
            for lid in idx.line_grid.get((cell_lon, cell_lat), []):
                line_ids.add(lid)

    found: list[dict[str, Any]] = []
    for lid in line_ids:
        if len(found) >= max_new:
            break
        line = idx.lines_by_id.get(lid)
        coords = idx.line_coords.get(lid) or []
        if not line or len(coords) < 2:
            continue

        along = idx.towers_on_line(lid)
        # Also include known towers snapped onto this line
        for tw in known:
            lat, lon = tw.get("latitude"), tw.get("longitude")
            if lat is None or lon is None:
                continue
            d, a = _along_line_m(float(lon), float(lat), coords)
            if d <= _SNAP_TOWER_M:
                tid = str(tw.get("id") or "")
                if tid and tid not in {str(t.get("id")) for _, t in along}:
                    along.append((a, tw))
        along.sort(key=lambda x: x[0])

        # Total line length
        total = 0.0
        for i in range(len(coords) - 1):
            total += _haversine_m(coords[i][1], coords[i][0], coords[i + 1][1], coords[i + 1][0])

        checkpoints: list[float] = [0.0] + [a for a, _ in along] + [total]
        for i in range(len(checkpoints) - 1):
            if len(found) >= max_new:
                break
            gap = checkpoints[i + 1] - checkpoints[i]
            if gap < max_gap_m:
                continue
            # Place fill points every fill_step_m inside the gap
            pos = checkpoints[i] + fill_step_m
            while pos < checkpoints[i + 1] - fill_step_m * 0.4 and len(found) < max_new:
                pt = _point_along_polyline(coords, pos)
                if not pt:
                    break
                lon, lat = pt
                # Keep fills inside viewport
                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    pos += fill_step_m
                    continue

                # Prefer a real nearby KML tower first
                real: dict[str, Any] | None = None
                best_d = _SNAP_TOWER_M
                for cell in idx._nearby_cells(lon, lat, ring=1):
                    for tw in idx.tower_grid.get(cell, []):
                        tid = str(tw.get("id") or "")
                        if not tid or tid in known_ids:
                            continue
                        d = _haversine_m(lat, lon, float(tw["latitude"]), float(tw["longitude"]))
                        if d < best_d:
                            best_d = d
                            real = tw

                if real:
                    tid = str(real["id"])
                    if tid not in known_ids:
                        known_ids.add(tid)
                        found.append(real)
                else:
                    # Provisional tower detected from corridor gap (imagery pylon site)
                    syn_id = f"kml-tower-gap-{lid[-8:]}-{int(lat * 1e5)}-{int(lon * 1e5)}"
                    if syn_id in known_ids:
                        pos += fill_step_m
                        continue
                    known_ids.add(syn_id)
                    meta = dict(line.get("metadata") or {})
                    meta.update(
                        {
                            "detected_source": "corridor_gap_fill",
                            "power": "tower",
                            "structure": "lattice",
                            "parent_line_id": lid,
                            "gap_fill": True,
                        }
                    )
                    volt = meta.get("voltage_kv")
                    found.append(
                        {
                            "id": syn_id,
                            "name": f"TWR-GAP-{int(lat * 1e4)}-{int(lon * 1e4)}",
                            "asset_type": "tower",
                            "latitude": lat,
                            "longitude": lon,
                            "status": "active",
                            "health_score": "healthy",
                            "metadata": meta,
                            "voltage_level_kv": volt,
                        }
                    )
                pos += fill_step_m

    logger.info(
        "Gap-fill viewport (%.4f,%.4f)–(%.4f,%.4f): %s new towers from %s lines",
        min_lon,
        min_lat,
        max_lon,
        max_lat,
        len(found),
        len(line_ids),
    )
    return found
