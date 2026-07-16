# Connect Railway Postgres → Backend → Render Frontend

Do **not** paste passwords into git. Use Railway **Variable References**.

## 1) Postgres → Backend (same Railway project)

You already have a Postgres service with `DATABASE_URL` (internal) and `DATABASE_PUBLIC_URL` (proxy).

1. Open your **backend API service** (the one deployed from `TAMS-Backend`), **not** the Postgres service.
2. Go to **Variables** → **Add Variable** / **Add Reference**.
3. Set:

| Variable | Value |
|----------|--------|
| `DATABASE_URL` | **Reference** → Postgres service → `DATABASE_URL` (internal). Equivalent: `${{Postgres.DATABASE_URL}}` |
| `CORS_ORIGINS` | `https://tams-txmr.onrender.com,https://tams-28nc.onrender.com,http://localhost:3000` |
| `ALLOWED_HOSTS` | `*,.up.railway.app` |
| `DEBUG` | `false` |
| `IMPORT_KML_ON_STARTUP` | `true` |
| `IMPORT_INCLUDE_TOWERS` | `true` |
| `JWT_SECRET_KEY` | any long random string |

4. Redeploy the backend.
5. Open `https://YOUR-BACKEND.up.railway.app/health` — expect `"database": true`.

> Use the **internal** `DATABASE_URL` (`postgres.railway.internal`) for the backend on Railway.  
> Use `DATABASE_PUBLIC_URL` only for tools on your laptop / outside Railway.

## 2) Backend → Frontend (Render)

1. Copy the backend **public** domain: `https://….up.railway.app` (Settings → Networking / Domains).
2. On Render → **tams-txmr** (or your frontend service) → **Environment**:

| Variable | Value |
|----------|--------|
| `BACKEND_URL` | `https://YOUR-BACKEND.up.railway.app` |
| `NEXT_PUBLIC_HOSTED_API_BASE_URL` | `https://YOUR-BACKEND.up.railway.app/api/v1` |
| `NEXT_PUBLIC_API_BASE_URL` | `/api/v1` |

3. Redeploy the frontend.

Flow:

```text
Browser → https://tams-28nc.onrender.com
       → /api/* (Next rewrite) → Railway Backend
       → Railway Postgres
```

## 3) Optional: fill DB from KML

After backend is healthy with `"database": true`:

```bash
railway run python -m scripts.import_kml_to_db --force
```

Or wait for the startup auto-import (`IMPORT_KML_ON_STARTUP=true`).
