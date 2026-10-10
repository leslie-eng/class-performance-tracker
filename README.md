# ClassTrack: Class Performance Tracker

ClassTrack keeps a study cohort accountable. Members join challenges and submit daily work: code, or a link to an
article they wrote. They earn points and streaks and appear on challenge and global leaderboards. Article
submissions are graded by Claude against a rubric. Members can also log job applications. A nightly job finds
members who are falling behind and can send them a WhatsApp nudge, and admins get a weekly digest.

| Part | Stack | Folder |
|---|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, APScheduler, uvicorn | [`backend/`](backend/) ([API docs](backend/README.md)) |
| Web app | React 19, TypeScript, Vite (builds to `dist/`), Tailwind v4, React Router, TanStack Query | [`frontend/`](frontend/) ([UI notes](frontend/README.md)) |
| Database | PostgreSQL (SQLite works only for tests) | external |

Besides daily tasks, members get:
- **The Friday Drop** (`/weekly`): every Friday at 08:00 (`TIMEZONE`), a summary of the week's class notes, a pick
  between the two projects members proposed, and a timed quiz (10, 20 or 30 minutes, easy to hard). On the first
  Friday of the month, an interview-prep quiz for the member's specialization and a whole-course quiz come out too.
  Opted-in members also get a one-line WhatsApp message.
- **Coding exercises** (`/code`): coursework in an in-browser editor. Python runs with Pyodide and JavaScript in a
  sandboxed worker, in the member's own browser, never on the server. AI feedback follows every submission.
- **Learning materials** (admins, `/admin/materials`): notes, links and `.md`/`.txt`/`.pdf` files that quizzes and
  draft exercises are generated from, with a review screen for both.

Quiz and coding points are kept separate from the challenge leaderboard and streaks.

The repo is a monorepo with two apps. Neither uses Docker. On Render they run as a **Python web service** and a
**Static Site**, both defined in [`render.yaml`](render.yaml).

---

## 1. Local setup

Prerequisites:
- Python 3.13. The version is pinned in `backend/.python-version`; 3.14 also works locally.
- Node 22 and npm.
- A Postgres database: a local install, or a free [Neon](https://neon.tech) database.

### Backend (http://localhost:8000, Swagger UI at `/docs`)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # set DATABASE_URL, JWT_SECRET, ADMIN_EMAILS
alembic upgrade head               # create/upgrade tables
uvicorn app.main:app --reload
```

### Frontend (http://localhost:5173)

```bash
cd frontend
npm install
npm run dev
```

In development, leave `VITE_API_URL` unset. Vite forwards `/api/*` to `http://localhost:8000`, so you don't need
any CORS setup.

Tests: `cd backend && pip install -r requirements-dev.txt && pytest`. By default the tests use SQLite.

---

## 2. Required components

| Component | Required? | Used for | Where to get it |
|---|---|---|---|
| PostgreSQL database | **Yes** | All app data: users, challenges, submissions, scores, job applications, notification log | [Render Postgres](https://render.com/docs/postgresql) (created by the Blueprint; the free tier expires after 30 days), [Neon](https://neon.tech) (free, does not expire), [Supabase](https://supabase.com) |
| API host | **Yes** | Runs FastAPI, migrations and the nightly scheduler | Render Web Service, Python runtime |
| Frontend host | **Yes** | Serves the built React app | Render Static Site, or Vercel (`frontend/vercel.json` is already set up) |
| Anthropic API key | No | AI grading of article submissions. Without it, articles show "not configured" and admins grade them by hand | [console.anthropic.com](https://console.anthropic.com) > API Keys |
| Meta WhatsApp Cloud API | No | Sending lag nudges and the Friday Drop. The default provider is `console`, which only writes the messages to the logs | [developers.facebook.com](https://developers.facebook.com) > WhatsApp > API Setup |
| External cron | Recommended on free Render | Wakes the sleeping API on Friday morning so the drop goes out on time | [cron-job.org](https://cron-job.org) (free) or a GitHub Actions schedule; see [DEPLOYMENT.md](DEPLOYMENT.md) |
| Code sandbox | No | Verified runs of coding exercises, including hidden tests | Self-hosted [Judge0](https://github.com/judge0/judge0) on its own server. Not part of the free setup |

Login is email and password, with JWTs signed by `JWT_SECRET`. The app has no OAuth, email, SMS or file storage: uploaded learning materials keep only their extracted text, in Postgres.

---

## 3. Environment variables

Templates with placeholders:
- [`backend/.env.example`](backend/.env.example): copy it to `backend/.env`.
- [`frontend/.env.example`](frontend/.env.example): copy it to `frontend/.env`. You only need it to point a local
  build at a remote API.

`.env` files are gitignored. **Never commit real values.** On Render, set the variables in each service's
**Environment** tab instead.

### Backend (`classtrack-api`)

| Variable | Required? | Purpose | Example format | Where to get it |
|---|---|---|---|---|
| `DATABASE_URL` | **Yes** | Postgres connection string. `postgres://` and `postgresql://` are converted to SQLAlchemy's psycopg 3 driver automatically | `postgresql://USER:PASSWORD@HOST:5432/DB` | Render Postgres: the Blueprint wires it in (or use the database page > **Internal Database URL**). Neon: Dashboard > Connection Details |
| `JWT_SECRET` | **Yes** | Signs login tokens. Defaults to the insecure `change-me` if unset | 48+ random characters | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The Blueprint generates one |
| `ADMIN_EMAILS` | **Yes** (for an admin) | Accounts registered with these emails become admins | `you@example.com,ta@example.com` | You choose |
| `CORS_ORIGINS` | **Yes** (in production) | Comma-separated browser origins allowed to call the API. Defaults to `http://localhost:3000,http://localhost:5173`. Read at startup, so the API must redeploy after a change. The API logs the list it's using as `CORS allowed origins: [...]` | `https://classtrack-web.onrender.com,http://localhost:5173` | Your static site's URL, scheme included. Keep the localhost entries if you also run the frontend locally against this API |
| `PYTHON_VERSION` | Render only | Python version Render installs | `3.13` | — |
| `FORWARDED_ALLOW_IPS` | Render only | Makes uvicorn trust Render's proxy headers, so the app sees the real client IP and `https` | `*` | — |
| `TIMEZONE` | No (default `UTC`; the Blueprint sets `Africa/Nairobi`) | Defines "today" for streaks and day numbers, the time of the nightly lag check, and the Friday Drop time. Changing it moves all three | `Africa/Nairobi` | An [IANA tz name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) |
| `ANTHROPIC_API_KEY` | No | Turns on AI grading, weekly summaries, quiz and exercise generation, and code feedback. Without it these show "not configured" | `sk-ant-...` | console.anthropic.com |
| `GRADING_MODEL` | No (default `claude-opus-5`) | Claude model used for grading | `claude-opus-5` | Anthropic model list |
| `ADMIN_CAN_VIEW_JOB_APPLICATIONS` | No (default `false`) | Lets admins see members' job applications | `true` / `false` | You choose |
| `WHATSAPP_PROVIDER` | No (default `console`) | `console` writes messages to the logs. `meta` sends them for real | `console` | — |
| `WHATSAPP_TOKEN` | Only if `meta` | Meta Cloud API access token | `EAAG...` | Meta developer app > WhatsApp > API Setup |
| `WHATSAPP_PHONE_NUMBER_ID` | Only if `meta` | Sending number ID | `123456789012345` | Same page |
| `WHATSAPP_LAG_TEMPLATE` | No | Approved template for first contact, outside Meta's 24-hour messaging window | `lag_nudge` | Meta Business Manager > Message templates |
| `SCHEDULER_ENABLED` | No (default `true`) | Runs the nightly lag check and the weekly digest in-process. Enable it on exactly one instance | `true` | — |
| `LAG_CHECK_HOUR` | No (default `20`) | Hour, in `TIMEZONE`, of the lag check | `20` | — |
| `WEEKLY_DIGEST_DAY` | No (default `sun`) | Day of the admin digest | `sun` | — |
| `WEEKLY_DROP_DAY` / `WEEKLY_DROP_HOUR` | No (default `fri` / `8`) | When the Friday Drop goes out, in `TIMEZONE` | `fri` / `8` | — |
| `MONTHLY_QUIZ_WEEK` | No (default `first`) | Which Friday of the month also releases the interview-prep and course quizzes | `first` or `last` | — |
| `SPECIALIZATIONS` | No | Choices members can pick in Settings; the interview-prep quiz follows it (no choice = `general`) | `data_engineering,data_science,…,general` | You choose |
| `QUIZ_MODEL` | No (default: `GRADING_MODEL`) | Claude model for summaries, digests, quiz and exercise generation | a cheaper Claude model | Anthropic model list |
| `REQUIRE_QUIZ_REVIEW` | No (default `false`) | `true` keeps generated quizzes as drafts until an admin publishes them | `false` | — |
| `FRONTEND_URL` | **Yes** for WhatsApp links | Link at the end of drop messages (`…/weekly`) | `https://classtrack-web.onrender.com` | Your static site's URL |
| `WHATSAPP_WEEKLY_TEMPLATE` | Only if `meta` | Approved template with **one** body parameter, used for the drop and admin alerts. The message is sent as a single line | `weekly_drop` | Meta Business Manager > Message templates |
| `JOB_TOKEN` | Recommended on free Render | Secret the external cron sends as `X-Job-Token` to `POST /internal/jobs/weekly-drop`. Unset turns the endpoint off | 32+ random characters | The Blueprint generates one; see [DEPLOYMENT.md](DEPLOYMENT.md) |
| `CODE_RUNNER` | No (default `none`) | `none`: members run exercises in their browser (practice runs, reduced points). `remote`: an external sandbox runs every test, hidden ones included | `none` | — |
| `CODE_RUNNER_URL` / `CODE_RUNNER_KEY` | Only if `remote` | Your Judge0-compatible sandbox and its auth token. It needs its own isolated host | `https://judge0.example.com` | Self-hosted Judge0; see [DEPLOYMENT.md](DEPLOYMENT.md) |
| `PORT` | Set by Render | Port the API listens on | `10000` | Render sets it automatically, so don't add it |

### Frontend (`classtrack-web`)

Vite copies `VITE_*` values into the JavaScript bundle at **build time**. Changing one in Render's
**Environment** tab does nothing until the static site is **rebuilt**: use **Manual Deploy > Clear build cache &
deploy**. Until then, the live site keeps the old value, or no value at all.

| Variable | Required? | Purpose | Example format | Where to get it |
|---|---|---|---|---|
| `VITE_API_URL` | **Yes** (in production) | Base URL of the API. If unset, the app calls `/api`, which only works with the Vite dev proxy | `https://classtrack-api.onrender.com` | The API service's URL in Render, without a trailing slash |
| `NODE_VERSION` | Render only | Node version used for the build. Vite 8 needs Node 20.19 or later | `22` | — |

---

## 4. Deploying on Render

```
browser ──> classtrack-web (Static Site: frontend/dist)
   │
   └──fetch──> classtrack-api (Python web service) ──> classtrack-db (Render Postgres)
```

Create things in this order: **database → API → frontend → update `CORS_ORIGINS`**. The Blueprint does the
first three in one step.

### Option 1: Blueprint (recommended)

1. Push the repo, including `render.yaml`, to GitHub.
2. In Render, go to **New > Blueprint**, pick the repo and click **Apply**. Render asks for each `sync: false`
   value:
   - `ADMIN_EMAILS`: your email address.
   - `CORS_ORIGINS`: `https://classtrack-web.onrender.com`. This is a guess at the URL; you'll fix it in step 4.
   - `VITE_API_URL`: `https://classtrack-api.onrender.com`. Also a guess; fixed in step 4.
   - `ANTHROPIC_API_KEY` and the `WHATSAPP_*` values can be left blank.
3. Render creates `classtrack-db`, then `classtrack-api`, with `DATABASE_URL` wired from the database and
   `JWT_SECRET` generated. Then it creates `classtrack-web`.
4. Check the real URLs at the top of each service page. If Render added a suffix, for example
   `classtrack-api-x1y2.onrender.com`:
   - **API > Environment**: set `CORS_ORIGINS` to the web URL. Saving redeploys the API.
   - **Web > Environment**: set `VITE_API_URL` to the API URL, then **Manual Deploy > Clear build cache & deploy**.
5. Open the web URL and create the admin account (section 6).

**Using Neon instead of Render Postgres:** before you apply, delete the `databases:` block in `render.yaml` and
replace the `DATABASE_URL` entry with `- key: DATABASE_URL` / `sync: false`. Then paste the Neon connection string
when Render asks.

### Option 2: Create or fix the services by hand

**1. Database:** **New > Postgres**. Name it `classtrack-db`, choose the same region you'll use for the API, and
pick a plan. When it's ready, copy the **Internal Database URL**. (Or use a Neon connection string.)

**2. API:** **New > Web Service**, then pick the repo.

If you're fixing the existing service that fails with the Dockerfile error: you can't change a service's runtime
from Docker to Python. Delete that service and create a new one, or ignore it.

| Setting | Value |
|---|---|
| Runtime / Language | **Python 3** |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` (under **Advanced**) |

Environment:
- `DATABASE_URL`: the URL from step 1.
- `JWT_SECRET`: a long random string.
- `ADMIN_EMAILS`: your email address.
- `CORS_ORIGINS`: leave it for now; you'll set it in step 4.
- `PYTHON_VERSION=3.13` and `FORWARDED_ALLOW_IPS=*`.
- Optionally `ANTHROPIC_API_KEY`.

The start command runs migrations on every deploy, so you don't need a separate migration step.

**3. Frontend:** **New > Static Site**, then pick the repo.

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |
| Environment | `VITE_API_URL=https://<your-api>.onrender.com`, `NODE_VERSION=22` |
| Redirects/Rewrites | Source `/*`, Destination `/index.html`, Action **Rewrite** |

**4. Close the loop:** set the API's `CORS_ORIGINS` to the static site's URL, for example
`https://classtrack-web.onrender.com`, and save. The API redeploys.

### After the first deploy: Friday Drop setup

The free instance sleeps, so the 08:00 scheduler can miss the drop. Set up the free external cron in
[DEPLOYMENT.md](DEPLOYMENT.md#waking-the-api-for-the-friday-drop) (5 minutes), and set `FRONTEND_URL` on the API.

### Free-plan caveats

- Free web services sleep after 15 minutes without traffic, and the first request after that takes about 30–60
  seconds. **The scheduler doesn't run while the service is asleep**, so the 8pm lag check and the weekly digest
  can be missed. Use a paid instance for reliable nudges, or run the checks yourself from the admin page.
- Free Render Postgres databases expire after 30 days. Back up your data or move to a paid plan or Neon before
  then.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `failed to read dockerfile: open Dockerfile: no such file or directory` | The service was created with the **Docker** runtime, and this repo has no Dockerfile | A service's runtime can't be changed after creation. Create a new **Python** web service (section 4, Option 2), or use the Blueprint, then delete the Docker service |
| `No open ports detected` / `Port scan timeout` / "Application failed to respond" | The app isn't listening on `0.0.0.0:$PORT`, or it crashed before starting | Use the exact start command above. Check the earlier log lines: a crash in `alembic upgrade head` usually means a database problem |
| `ModuleNotFoundError: No module named 'app'` | Root Directory isn't `backend` | Set Root Directory to `backend` |
| Build fails while installing packages, or the wrong Python is used | The Python version isn't pinned | Set `PYTHON_VERSION=3.13` (`backend/.python-version` sets it too) |
| `connection refused` / `could not translate host name` / `localhost` in the logs | `DATABASE_URL` is missing or wrong. `localhost` doesn't exist on Render | Paste the full connection string. For Render Postgres in the same region, use the **Internal** URL. Other providers usually need `?sslmode=require` |
| `prepared statement "_pg3_x" does not exist` | A transaction-mode pooler (PgBouncer) | Use the direct, non-pooler host, for example the Neon host without `-pooler` |
| Browser console: blocked by CORS policy | `CORS_ORIGINS` doesn't exactly match the site's origin | Set it to `https://<web>.onrender.com`: scheme included, no trailing slash. Separate several origins with commas, then let the API redeploy |
| Forms "submit" but nothing reaches the API. The error says *"returned a web page instead of JSON"*, or the requests go to `/api/...` and return 404/405 | `VITE_API_URL` wasn't set when the site was built. The requests hit the static site, whose `/* → /index.html` rewrite answers them | Set `VITE_API_URL` to the API URL, then **Clear build cache & deploy** the static site |
| *"Could not reach the API at …"* | CORS blocked the request, the URL is wrong, or the API crashed. An unhandled 500 also has no CORS headers, so the browser reports it as a CORS error | Check the API logs first. Then make sure `CORS_ORIGINS` contains the site's exact origin, and that opening `<VITE_API_URL>/health` in a browser returns `{"status":"ok"}` |
| Refreshing `/leaderboard` or `/grading/12` gives 404 | The SPA rewrite is missing | Add a rewrite rule: source `/*`, destination `/index.html` |
| The first request takes about a minute; nightly nudges don't arrive | Free-tier spin-down | Expected on the free plan. Upgrade the API instance to keep it awake |

---

### Debugging API requests

All requests go through one client, [`frontend/src/lib/api.ts`](frontend/src/lib/api.ts), which uses
`VITE_API_URL` as the base URL.

- **On screen:** a failed form shows `Error <status>: <message>` next to the form. A failed page load shows the
  same message in a toast with a **Retry** button.
- **In the console:** every failed request is logged as `[api] METHOD URL -> status`, with the response body.
  If the production build has no `VITE_API_URL`, the console also shows a warning at load.
- **In DevTools > Network:** check that requests go to `https://<api>.onrender.com/...`, not to the site's own
  domain.

## 6. First admin account

There's no default admin. A user becomes an admin **when they register** with an email listed in
`ADMIN_EMAILS`:

1. Set `ADMIN_EMAILS=you@example.com` on the API service, and let it deploy.
2. Open the web app and register with that email, using a password of at least 8 characters.
3. That account can now open `/admin`, create challenges and promote others through
   `PATCH /admin/members/{id}/role?is_admin=true`.

If you registered **before** setting `ADMIN_EMAILS`, the flag isn't applied after the fact. Promote yourself in
SQL, either from the database's **Shell / psql** command on Render or from Neon's SQL editor:

```sql
UPDATE users SET is_admin = true WHERE email = 'you@example.com';
```

`python -m scripts.seed_demo` (run from `backend/`) creates a demo cohort with the admin login
`demo@classtrack.dev` / `password123`. It only runs on an empty database and is for demos, not production.
