# ClassTrack: Class Performance Tracker

ClassTrack keeps a study cohort accountable. Members join challenges and submit daily work: code, or a link to an
article they wrote. They earn points and streaks and appear on challenge and global leaderboards. Article
submissions are graded by Claude against a rubric. Members can also log job applications. A nightly job finds
members who are falling behind and can send them a WhatsApp nudge, and admins get a weekly digest.

| Part | Stack | Folder |
|---|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, APScheduler, uvicorn | [`backend/`](backend/) ([API docs](backend/README.md)) |
| Web app | React 19, TypeScript, Vite, Tailwind v4, TanStack Query | [`frontend/`](frontend/) ([UI notes](frontend/README.md)) |
| Database | PostgreSQL 16 (SQLite works only for tests) | external |

There is **no Dockerfile at the repo root**. Each app has its own, in `backend/Dockerfile` and
`frontend/Dockerfile`. `docker-compose.yml` runs all three parts locally. [`render.yaml`](render.yaml) deploys them
to Render.

---

## 1. Local setup

### Option A: Docker (everything in one command)

Prerequisites: Docker Desktop.

```bash
cp .env.example .env          # set JWT_SECRET at least
docker compose up --build
```

- App: http://localhost:8080
- API and Swagger UI: http://localhost:8000/docs

Compose starts Postgres, runs migrations and serves the frontend through nginx, which proxies `/api` to the backend.

### Option B: Run each part directly

Prerequisites: Python 3.13, Node 22, and a Postgres database (local or Neon).

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # edit DATABASE_URL, JWT_SECRET, ADMIN_EMAILS
alembic upgrade head                                 # create/upgrade tables
uvicorn app.main:app --reload                        # http://localhost:8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                                          # http://localhost:5173, proxies /api to :8000
```

Tests: `cd backend && pip install -r requirements-dev.txt && pytest`. By default the tests use SQLite.

---

## 2. Required components

| Component | Required? | Used for | Where to get it |
|---|---|---|---|
| PostgreSQL database | **Yes** | All app data: users, challenges, submissions, scores, job applications, notification log | [Neon](https://neon.tech) (free, does not expire), [Render Postgres](https://render.com/docs/postgresql) (free tier expires after 30 days), [Supabase](https://supabase.com) |
| Backend host | **Yes** | Runs the FastAPI API, migrations and the nightly scheduler | Render Web Service (Docker) |
| Frontend host | **Yes** | Serves the built React app | Render Static Site, or Vercel (`frontend/vercel.json` is already set up) |
| Anthropic API key | No | AI grading of article submissions. Without it, articles show "not configured" and admins grade them by hand | [console.anthropic.com](https://console.anthropic.com) > API Keys |
| Meta WhatsApp Cloud API | No | Sending lag nudges. The default provider is `console`, which only writes the messages to the logs | [developers.facebook.com](https://developers.facebook.com) > WhatsApp > API Setup |

The app has no third-party auth, email, SMS or file storage. Login is email and password, with JWTs signed by
`JWT_SECRET`.

---

## 3. Environment variables

Templates with placeholders:
- [`backend/.env.example`](backend/.env.example): the backend's variables, for local runs and as a reference for Render.
- [`.env.example`](.env.example): the variables `docker compose` reads.
- [`frontend/.env.example`](frontend/.env.example): the frontend's build-time variable.

Copy a template to `.env` and fill it in. `.env` files are gitignored. **Never commit real values.**

### Backend (`classtrack-api`)

| Variable | Required? | Purpose | Example format | Where to get it |
|---|---|---|---|---|
| `DATABASE_URL` | **Yes** | Postgres connection string. `postgres://` and `postgresql://` URLs are accepted as-is | `postgresql://USER:PASSWORD@HOST/DB?sslmode=require` | Neon: Dashboard > Connection Details. Render: database page > *Internal Database URL* |
| `JWT_SECRET` | **Yes** | Signs login tokens. Defaults to the insecure `change-me` if unset | 48+ random characters | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The Blueprint generates one |
| `ADMIN_EMAILS` | **Yes** (for an admin) | Accounts registered with these emails become admins | `you@example.com,ta@example.com` | You choose |
| `CORS_ORIGINS` | **Yes** (in production) | Browser origins allowed to call the API | `https://classtrack-web.onrender.com` | Your frontend's URL, without a trailing slash |
| `TIMEZONE` | No (default `UTC`) | Defines "today", day numbers and the nightly job time | `Africa/Lagos` | An [IANA tz name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) |
| `ANTHROPIC_API_KEY` | No | Turns on AI grading | `sk-ant-...` | console.anthropic.com |
| `GRADING_MODEL` | No (default `claude-opus-5`) | Claude model used for grading | `claude-opus-5` | Anthropic model list |
| `ADMIN_CAN_VIEW_JOB_APPLICATIONS` | No (default `false`) | Lets admins see members' job applications | `true` / `false` | You choose |
| `WHATSAPP_PROVIDER` | No (default `console`) | `console` writes messages to the logs. `meta` sends them for real | `console` | — |
| `WHATSAPP_TOKEN` | Only if `meta` | Meta Cloud API access token | `EAAG...` | Meta developer app > WhatsApp > API Setup |
| `WHATSAPP_PHONE_NUMBER_ID` | Only if `meta` | Sending number ID | `123456789012345` | Same page |
| `WHATSAPP_LAG_TEMPLATE` | No | Approved template for first contact, outside Meta's 24-hour messaging window | `lag_nudge` | Meta Business Manager > Message templates |
| `SCHEDULER_ENABLED` | No (default `true`) | Runs the nightly lag check and the weekly digest in-process. Enable it on exactly one instance | `true` | — |
| `LAG_CHECK_HOUR` | No (default `20`) | Hour, in `TIMEZONE`, of the lag check | `20` | — |
| `WEEKLY_DIGEST_DAY` | No (default `sun`) | Day of the admin digest | `sun` | — |
| `PORT` | Set by Render | Port the API listens on. Defaults to 8000 locally | `10000` | Render sets it automatically, so don't add it |

### Frontend (`classtrack-web`)

These are build-time variables. After changing one, you must **rebuild**; a restart is not enough.

| Variable | Required? | Purpose | Example format | Where to get it |
|---|---|---|---|---|
| `VITE_API_URL` | **Yes** (in production) | Base URL of the API. If unset, the app calls `/api`, which only works with the local proxies | `https://classtrack-api.onrender.com` | Your backend service's URL, without a trailing slash |
| `NODE_VERSION` | Render only | Node version used for the build | `22` | — |

---

## 4. Deploying on Render

The repo deploys as two services, plus an external database:

```
browser ──> classtrack-web (Static Site, frontend/dist)
   │
   └──fetch──> classtrack-api (Docker, backend/Dockerfile) ──> Postgres (Neon or Render)
```

### Option 1: Blueprint (recommended)

1. Push this repo to GitHub, including `render.yaml`.
2. Create a Postgres database, for example on Neon, and copy its connection string.
3. In Render, go to **New > Blueprint**, pick the repo and click **Apply**.
4. Render asks for each `sync: false` value:
   - `DATABASE_URL`: your Postgres connection string.
   - `ADMIN_EMAILS`: your email address.
   - `CORS_ORIGINS`: `https://classtrack-web.onrender.com`. Use the static site's real URL; if the name is taken, Render adds a suffix.
   - `VITE_API_URL`: `https://classtrack-api.onrender.com`. Again, use the API's real URL.
   - `ANTHROPIC_API_KEY` and the `WHATSAPP_*` values can be left blank.
5. Wait for both deploys to finish. If the real URLs differ from what you entered, fix `CORS_ORIGINS` (API) and
   `VITE_API_URL` (web) under each service's **Environment** tab. Then redeploy: the web service needs
   **Clear build cache & deploy**, because `VITE_API_URL` is read at build time.
6. Open the web URL and register with an `ADMIN_EMAILS` address (see section 6).

### Option 2: Fix an existing service by hand (the one that failed)

**Backend: Web Service, Runtime Docker.** Under **Settings > Build & Deploy**:

| Setting | Value |
|---|---|
| Root Directory | *(leave empty)* |
| Dockerfile Path | `./backend/Dockerfile` |
| Docker Build Context Directory | `./backend` |
| Docker Command | *(leave empty: the image migrates, then starts uvicorn on `$PORT`)* |
| Health Check Path | `/health` |

Alternatively, set **Root Directory** to `backend` and keep Dockerfile Path `./Dockerfile` and Context `.`.
Then add the backend variables from section 3 under **Environment**, and use **Manual Deploy > Deploy latest commit**.

There's no separate build or start command to set: the Dockerfile installs the requirements, and the
container's entrypoint runs `alembic upgrade head` and then
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

**Frontend: New > Static Site.**

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |
| Environment | `VITE_API_URL=https://<your-api>.onrender.com`, `NODE_VERSION=22` |
| Redirects/Rewrites | Source `/*`, Destination `/index.html`, Action **Rewrite** |

Don't deploy `frontend/Dockerfile` on Render. Its nginx config proxies to `backend:8000`, a hostname that only
exists inside docker-compose.

### Free-plan caveats

- Free web services sleep after 15 minutes without traffic. The first request after that takes about 30–60
  seconds, and **the in-process scheduler doesn't run while the service is asleep**, so the 8pm lag check and the
  weekly digest can be missed. Use a paid instance for reliable nudges, or trigger the checks yourself from the
  admin page (`POST /admin/notify/run`).
- Free Render Postgres databases expire after 30 days. Neon's free tier doesn't.

---

## 5. Common deploy errors

| Error | Cause | Fix |
|---|---|---|
| `failed to read dockerfile: open Dockerfile: no such file or directory` | Render looks for `./Dockerfile` at the repo root, but the backend's is at `backend/Dockerfile` | Set Dockerfile Path `./backend/Dockerfile` and Build Context `./backend`, or set Root Directory to `backend`. Or use the Blueprint |
| `No open ports detected` / `Port scan timeout` | The app isn't listening on `$PORT`, or the container crashed before it started | The image binds to `0.0.0.0:$PORT`. Check the logs above this line: it's usually a migration or database error |
| `connection refused` / `could not translate host name` at startup | `DATABASE_URL` is missing or wrong. `localhost` doesn't work on Render | Paste the provider's full connection string. For Render Postgres in the same region, use the **Internal** URL |
| `SSL connection is required` / `sslmode` errors | The host requires TLS | Append `?sslmode=require` (Neon's URLs already include it) |
| `prepared statement "_pg3_x" does not exist` | A transaction-mode connection pooler (PgBouncer) | Use the database's direct, non-pooler host, for example the Neon host without `-pooler` |
| `alembic ... Can't locate revision` | The database was migrated by a different branch of the code | Point the API at a fresh database, or fix the `alembic_version` table |
| Blocked by CORS policy (browser console) | `CORS_ORIGINS` doesn't include the frontend URL exactly | Set it to `https://<web>.onrender.com`: scheme included, no trailing slash. Then redeploy the API |
| Frontend calls `/api/...` and gets 404 | `VITE_API_URL` wasn't set when the site was built | Set it, then **Clear build cache & deploy** the static site |
| Refreshing `/leaderboard` gives 404 | The SPA rewrite is missing | Add the rewrite rule `/*` → `/index.html` |
| Static build fails with a Vite/Node version error | Render's default Node version is too old for Vite 8 | Set `NODE_VERSION=22` |

---

## 6. First admin account

There's no default admin. A user becomes an admin **when they register** with an email listed in
`ADMIN_EMAILS`:

1. Set `ADMIN_EMAILS=you@example.com` on the API service and deploy.
2. Open the web app and register with that email, using a password of at least 8 characters.
3. That account can now open `/admin`, create challenges and promote others through
   `PATCH /admin/members/{id}/role?is_admin=true`.

If you registered **before** setting `ADMIN_EMAILS`, the flag isn't applied after the fact. Either register
another account, or promote yourself in SQL (Neon SQL editor or `psql`):

```sql
UPDATE users SET is_admin = true WHERE email = 'you@example.com';
```

`python -m scripts.seed_demo` (run from `backend/`) creates a demo cohort with the admin login
`demo@classtrack.dev` / `password123`. It only runs on an empty database and is for demos, not production.
