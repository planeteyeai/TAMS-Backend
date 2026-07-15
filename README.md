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

## Getting Started

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
