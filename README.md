# TAMS Backend

Backend API for **TAMS — Transmission Asset Intelligence & Monitoring Platform**, a satellite-based system for monitoring power transmission assets (towers, lines, substations).

Built with **FastAPI**.

## Features

- Satellite monitoring pipeline: Acquire → Detect → Compare → Alert → Complete
- STAC imagery catalog (Sentinel-1/2, Landsat 9, Sentinel-2 night)
- Rule-based change detection and alert engine
- Global substation catalog (India + world)
- REST API for assets, alerts, analytics, imagery, and monitoring workflows

## Project Structure

```
app/
├── main.py              # FastAPI entry point
├── api/v1/              # API routes (assets, alerts, analytics, imagery, monitoring)
├── core/                # config, logging
├── db/                  # database setup
├── models/              # ORM models
├── schemas/             # Pydantic schemas
└── services/            # monitoring workflow, change detection, alert engine, catalogs
```

## Getting Started

### 1. Prerequisites

- Python 3.11+ (tested on 3.12)

### 2. Setup

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# edit .env with your values
```

### 4. Run

```bash
python -m app.main
```

The API runs on `http://localhost:8000`.

- Swagger docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## API

All endpoints are served under `/api/v1`, e.g.:

- `GET /api/v1/assets`
- `GET /api/v1/alerts`
- `GET /api/v1/analytics/overview`
- `POST /api/v1/monitoring/run`
- `GET /api/v1/monitoring/workflow`
