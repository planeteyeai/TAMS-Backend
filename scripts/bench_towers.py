"""Benchmark tower bbox query on configured DATABASE_URL."""
import asyncio
import time

from sqlalchemy import text

from app.db.database import engine


async def main() -> None:
    async with engine.connect() as conn:
        tid = await conn.scalar(
            text("SELECT asset_type_id FROM asset_types WHERE type_code = 'TOWER'")
        )
        print("tower_type_id", tid)

        explain = """
        EXPLAIN (ANALYZE, BUFFERS)
        SELECT a.asset_id, a.name, a.latitude, a.longitude,
               jsonb_build_object(
                 'country_or_state', a.metadata->'country_or_state',
                 'region', a.metadata->'region',
                 'voltage_kv', a.metadata->'voltage_kv'
               )
        FROM assets a
        JOIN asset_types t ON t.asset_type_id = a.asset_type_id
        WHERE t.type_code = 'TOWER' AND a.is_active
          AND a.latitude BETWEEN 22.9 AND 23.1
          AND a.longitude BETWEEN 72.5 AND 72.7
        LIMIT 600
        """
        for row in (await conn.execute(text(explain))).all():
            print(row[0])

        t0 = time.perf_counter()
        result = await conn.execute(
            text(
                """
                SELECT a.asset_id, a.name, a.latitude, a.longitude,
                       jsonb_build_object(
                         'country_or_state', a.metadata->'country_or_state',
                         'region', a.metadata->'region',
                         'voltage_kv', a.metadata->'voltage_kv'
                       )
                FROM assets a
                JOIN asset_types t ON t.asset_type_id = a.asset_type_id
                WHERE t.type_code = 'TOWER' AND a.is_active
                  AND a.latitude BETWEEN 22.9 AND 23.1
                  AND a.longitude BETWEEN 72.5 AND 72.7
                LIMIT 600
                """
            ),
        )
        rows = result.all()
        print("rows", len(rows), "sec", round(time.perf_counter() - t0, 3))

        from app.services.gis_service import get_viewport_towers

        t0 = time.perf_counter()
        data = await get_viewport_towers(
            bbox="72.5,22.9,72.7,23.1", state="Gujarat", limit=600
        )
        print(
            "service",
            data["total"],
            "sec",
            round(time.perf_counter() - t0, 3),
            "source",
            data.get("source"),
        )


if __name__ == "__main__":
    asyncio.run(main())
