"""
Import all indian_KML assets into PostgreSQL.

Usage (local):
  set DATABASE_URL=postgresql+asyncpg://...
  python -m scripts.import_kml_to_db
  python -m scripts.import_kml_to_db --force
  python -m scripts.import_kml_to_db --skip-towers

Usage (Railway one-off):
  railway run python -m scripts.import_kml_to_db --force
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Import KML corridor data into Postgres")
    parser.add_argument("--force", action="store_true", help="Clear existing assets and reimport")
    parser.add_argument("--skip-towers", action="store_true", help="Import lines + substations only")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--health-towers", action="store_true", help="Also write health rows for towers")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async def _run() -> dict:
        from app.db.init_db import init_database
        from app.services.kml_db_import import import_kml_to_database

        ok = await init_database()
        if not ok:
            raise SystemExit(
                "Database not ready. Set DATABASE_URL to your Railway/local Postgres "
                "(e.g. DATABASE_URL=${{Postgres.DATABASE_URL}})."
            )
        return await import_kml_to_database(
            include_towers=not args.skip_towers,
            force=args.force,
            batch_size=args.batch_size,
            write_health_for_towers=args.health_towers,
        )

    stats = asyncio.run(_run())
    print("Import finished:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
