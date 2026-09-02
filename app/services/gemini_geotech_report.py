"""Gemini-powered Transmission-line geotechnical report — cached by lat/lon."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = _BACKEND_DIR / "data" / "gemini_geotech_cache"

# Static system instruction — kept short to save tokens on every call.
_SYSTEM_PROMPT = """You are an Indian geotechnical engineer (IS 6403, IS 2911, IS 1498, IS 3043).
Write ONE complete HTML document (inline CSS, no markdown fences).
Use ONLY the JSON DATA provided — never invent field/lab measurements.
Tag modelled values (MOD), correlated (CORR), calculated (CALC), field-required (FTR).
Include ALL sections and ALL table columns:
1) Soil Test Summary (per BH, 0.5 m layers to 2.0 m: Gravel,Sand,Silt,Clay,LL,PL,PI,IS Class,MDD,OMC,Dry dens,Bulk dens,FSI,UCS,SG,SBC,CBR,Remarks,GWT)
2) SBC step calculations (design params, shear, settlement, depth & size correction)
3) Pile design 450 mm & 600 mm at 1.0/1.5/2.0 m (vertical, uplift, lateral + summary tables)
4) CBR depth-wise
5) Earth resistivity with formula and recommendation table
Show location name and coordinates prominently in scope."""

_USER_TEMPLATE = """Location: {place_label}
Coordinates: {lat:.6f}°N, {lon:.6f}°E
Region: {region}
Purpose: Transmission tower foundation investigation to 2.0 m depth.

DATA (use exactly):
{data_json}

Output professional HTML report for this site only."""


def _cache_key(lat: float, lon: float) -> str:
    return f"{round(lat, 5):.5f}_{round(lon, 5):.5f}"


def _cache_path(lat: float, lon: float) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_cache_key(lat, lon)}.json"


def get_cached_report(lat: float, lon: float) -> dict[str, Any] | None:
    path = _cache_path(lat, lon)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("html"):
            return payload
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Invalid geotech cache %s: %s", path, exc)
    return None


def save_cached_report(
    lat: float,
    lon: float,
    *,
    html: str,
    place_label: str,
    region: str | None,
    model: str,
) -> dict[str, Any]:
    payload = {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "cache_key": _cache_key(lat, lon),
        "place_label": place_label,
        "region": region,
        "html": html,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _cache_path(lat, lon).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _extract_html(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:html)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if "<html" not in text.lower():
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Geotech Report</title></head><body>{text}</body></html>"
    return text


async def generate_gemini_geotech_report(
    lat: float,
    lon: float,
    *,
    place_label: str,
    region: str | None,
    geo_summary: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    """Return cached HTML or call Gemini once, then cache."""
    if not force:
        cached = get_cached_report(lat, lon)
        if cached:
            return {
                "html": cached["html"],
                "cached": True,
                "cache_key": cached.get("cache_key") or _cache_key(lat, lon),
                "place_label": cached.get("place_label") or place_label,
                "generated_at": cached.get("generated_at"),
                "model": cached.get("model"),
                "source": "cache",
            }

    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in tams-backend/.env")

    # Compact JSON — no pretty print to save tokens.
    data_json = json.dumps(geo_summary, ensure_ascii=False, separators=(",", ":"))
    user_text = _USER_TEMPLATE.format(
        place_label=place_label or f"{lat:.6f}°N, {lon:.6f}°E",
        lat=lat,
        lon=lon,
        region=region or "Not specified",
        data_json=data_json,
    )

    model = settings.GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": settings.GEMINI_TEMPERATURE,
            "maxOutputTokens": settings.GEMINI_MAX_OUTPUT_TOKENS,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, params={"key": api_key}, json=body)
        if resp.status_code != 200:
            detail = resp.text[:500]
            logger.error("Gemini API error %s: %s", resp.status_code, detail)
            raise RuntimeError(f"Gemini API failed ({resp.status_code})")

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        raw = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if not raw.strip():
            raise RuntimeError("Gemini returned empty text")

    html = _extract_html(raw)
    saved = save_cached_report(
        lat,
        lon,
        html=html,
        place_label=place_label,
        region=region,
        model=model,
    )

    return {
        "html": html,
        "cached": False,
        "cache_key": saved["cache_key"],
        "place_label": place_label,
        "generated_at": saved["generated_at"],
        "model": model,
        "source": "gemini",
    }
