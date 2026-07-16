"""Quick DB check then full KML import (skips broken PostGIS path)."""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> int:
    from sqlalchemy import text

    from app.db.database import async_session_maker, engine
    from app.db.init_db import check_db_connection, init_database, is_db_ready
    from app.services.kml_db_import import import_kml_to_database

    ok = await init_database()
    if not ok:
        # Tables may already exist; mark ready if SELECT works
        if await check_db_connection():
            print("init_database soft-failed but connection OK — continuing import")
        else:
            raise SystemExit("Database not ready")

    async with engine.connect() as c:
        n = (await c.execute(text("select count(*) from assets"))).scalar()
        print("assets_before", n)

    print("Starting full KML import (force=True, towers=True)...")
    stats = await import_kml_to_database(
        include_towers=True,
        force=True,
        batch_size=500,
        write_health_for_towers=False,
    )
    print("Import finished:", stats)

    async with engine.connect() as c:
        n = (await c.execute(text("select count(*) from assets"))).scalar()
        print("assets_after", n)
        by_type = await c.execute(
            text(
                "SELECT at.type_code, count(*) FROM assets a "
                "JOIN asset_types at ON at.asset_type_id = a.asset_type_id "
                "GROUP BY at.type_code ORDER BY at.type_code"
            )
        )
        for row in by_type:
            print("type", row[0], row[1])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
