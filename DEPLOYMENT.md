# ClassTrack Deployment Guide

## Backend-Frontend Connection

### Development Setup

**Backend runs on port 8000, frontend on port 5173.**

1. Backend:
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env and set at minimum: DATABASE_URL, JWT_SECRET
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

2. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. The Vite dev server proxies `/api/*` requests to `http://localhost:8000/*` (stripping the `/api` prefix).

### Production Deployment (Render)

The `render.yaml` blueprint deploys both services:

#### Backend (`classtrack-api`)
- Set these environment variables in Render dashboard:
  - `CORS_ORIGINS` — **CRITICAL**: Must include your frontend URL, e.g. `https://classtrack-web.onrender.com`
  - `ADMIN_EMAILS` — Comma-separated emails that become admins on registration
  - `ANTHROPIC_API_KEY` — Optional, for AI article grading
  - `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_LAG_TEMPLATE` — Optional, for WhatsApp notifications

#### Frontend (`classtrack-web`)
- Set this environment variable:
  - `VITE_API_URL` — **CRITICAL**: The backend's full URL, e.g. `https://classtrack-api.onrender.com` (no trailing slash)
- **Important**: This is a build-time variable. After changing it, you must trigger a redeploy so Vite rebuilds with the new value.

### CORS Troubleshooting

If frontend requests fail with network errors:
1. Check browser console for CORS errors
2. Verify `CORS_ORIGINS` on backend includes the frontend origin (scheme + domain, no trailing slash)
3. Verify frontend was built with correct `VITE_API_URL`
4. Check backend logs for the "CORS allowed origins" line on startup

### API URL Validation

The frontend includes runtime checks:
- If `VITE_API_URL` was unset during build, it defaults to `/api` and logs a warning in production
- If the API returns HTML instead of JSON, it detects the frontend's `index.html` was served (wrong URL)

### Database

Render provisions a free PostgreSQL database. Migrations run automatically on every backend deploy via the `startCommand`.

For other providers (Neon, Supabase), delete the `databases` section in `render.yaml` and set `DATABASE_URL` manually (the backend accepts `postgres://` and `postgresql://` URLs and converts them to `postgresql+psycopg://`).
