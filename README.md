# TAMS Backend

Backend API for **TAMS — Transmission Asset Monitoring System**, covering satellite monitoring and enterprise asset modules (registry, alarms, health, maintenance, inspections, GIS, dashboards).

Built with **FastAPI** + **PostgreSQL/PostGIS** (with in-memory mock fallback when DB is unavailable).

## Features

- **Satellite monitoring pipeline:** Acquire → Detect → Compare → Alert → Complete
- **STAC imagery catalog:** Sentinel-1/2, Landsat 9, Sentinel-2 night
- **Enterprise modules:** Assets, alarms, health scores, work orders, inspections, GIS GeoJSON, role dashboards
- **Rule-based change detection** and alert engine
- **Global substation catalog** (India + world)
- **REST API** under `/api/v1`

## Project Structure

```
app/
├── main.py              # FastAPI entry point, lifespan DB init
├── api/v1/              # assets, alarms, alerts, health, workorders, inspections,
│                        # gis, dashboard, analytics, imagery, monitoring, predictive, risk
├── core/                # config, logging
├── db/                  # database setup, init_db seed
├── models/              # entities.py (SQLAlchemy ORM)
├── schemas/             # Pydantic request/response schemas
└── services/            # asset, alarm, health, maintenance, inspection, gis, dashboard,
                           # monitoring workflow, change detection, mock_data, catalogs
```

## Deploy (Railway)

1. Create a Railway project from [planeteyeai/TAMS-Backend](https://github.com/planeteyeai/TAMS-Backend).
2. **Add Postgres:** project → **+ New** → **Database** → **PostgreSQL**.
3. On the **backend service → Variables**, link the DB:

| Variable | Value |
|----------|--------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `CORS_ORIGINS` | `https://tams-txmr.onrender.com,http://localhost:3000` |
| `ALLOWED_HOSTS` | `*,.up.railway.app` |
| `DEBUG` | `false` |
| `JWT_SECRET_KEY` | strong random secret |

The app rewrites Railway’s `postgres://…` URL to `postgresql+asyncpg://…` automatically, creates tables on boot, and **imports all indian_KML assets into Postgres** when the table is empty (`IMPORT_KML_ON_STARTUP=true`).

### Load / reload KML into the database (script)

```bash
# Local
set DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:PORT/DB
python -m scripts.import_kml_to_db

# Wipe and reimport everything (lines + substations + towers)
python -m scripts.import_kml_to_db --force

# Railway shell / one-off
railway run python -m scripts.import_kml_to_db --force
```

After import, GIS / assets / stats are served from the database (`"source": "database"`).

4. Railway builds with the repo `Dockerfile` (`railway.json`).
5. Copy the public URL (`https://….up.railway.app`) into the Render frontend env:
   - `BACKEND_URL`
   - `NEXT_PUBLIC_HOSTED_API_BASE_URL` (= `…/api/v1`)

Health: `GET /health` (includes `"database": true` when Postgres is connected) · Docs: `GET /docs`

## Getting Started (local)

### 1. Prerequisites

- Python 3.11+ (tested on 3.12)
- PostgreSQL 15+ with PostGIS (optional — mock mode works without DB)

### 2. Setup

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 3. Run

```bash
python -m uvicorn app.main:app --reload --port 8000
```

- Swagger docs: `http://localhost:8000/docs`
- API status: `GET http://localhost:8000/api/v1/status` (shows `"database": true/false`)

## Key API Routes

| Module | Examples |
|--------|----------|
| Assets | `GET/POST/PUT/DELETE /api/v1/assets` |
| Alarms | `GET/POST /api/v1/alarms`, acknowledge, close |
| Health | `GET /api/v1/health` |
| Maintenance | `GET/POST /api/v1/workorders` |
| Inspections | `GET/POST /api/v1/inspections` |
| GIS | `GET /api/v1/gis/features` |
| Dashboards | `GET /api/v1/dashboard/operations` |
| Satellite | `POST /api/v1/monitoring/run` |

See [docs/enterprise/IMPLEMENTATION.md](../docs/enterprise/IMPLEMENTATION.md) for the full matrix.
