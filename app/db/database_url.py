"""Normalize DATABASE_URL for SQLAlchemy + asyncpg (Railway / Render / local)."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def normalize_database_url(url: str) -> str:
    """
    Railway injects postgres:// or postgresql:// — async SQLAlchemy needs
    postgresql+asyncpg://. Strip libpq SSL query knobs that break asyncpg.
    """
    if not url or not url.strip():
        return url

    normalized = url.strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://") :]
    if normalized.startswith("postgresql://"):
        normalized = "postgresql+asyncpg://" + normalized[len("postgresql://") :]
    elif normalized.startswith("postgresql+psycopg2://"):
        normalized = "postgresql+asyncpg://" + normalized[len("postgresql+psycopg2://") :]

    parsed = urlparse(normalized)
    if not parsed.query:
        return normalized

    drop = {"sslmode", "ssl", "channel_binding"}
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in drop]
    return urlunparse(parsed._replace(query=urlencode(kept)))


def database_requires_ssl(url: str) -> bool:
    """SSL for public hosts; skip local and Railway private network DNS."""
    host = (urlparse(url).hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "postgres", "db"}:
        return False
    if host.endswith(".railway.internal"):
        return False
    return True
