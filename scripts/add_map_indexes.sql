-- Run once on Railway / local Postgres after import for fast map tower queries.
CREATE INDEX IF NOT EXISTS ix_assets_type_lat_lon_active
    ON assets (asset_type_id, latitude, longitude)
    WHERE is_active = true AND latitude IS NOT NULL AND longitude IS NOT NULL;
