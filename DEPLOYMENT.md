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
  - `OPENROUTER_API_KEY` — Optional, turns on all AI features (see [AI models](#ai-models-openrouter) below)
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

## Friday Drop, quizzes and coding exercises

Operational extras on top of the setup above and in [README.md](README.md#4-deploying-on-render).
Every variable named here is described in the README's
[environment table](README.md#backend-classtrack-api).

### What happens on deploy

The API's start command runs `alembic upgrade head`, so the new tables are created on the first deploy. There are
three migrations: the weekly drop and quizzes, the learning materials, and the coding exercises. Nothing else needs
running by hand.

If you deploy with the Blueprint, the new variables are created with it, including a generated `JOB_TOKEN`.
`TIMEZONE` now defaults to `Africa/Nairobi`. That also moves "today" for streaks and the 20:00 lag check.

### Waking the API for the Friday Drop

The drop is scheduled for Friday 08:00 in `TIMEZONE`. On Render's free plan the API sleeps after 15 idle minutes,
and a sleeping process can't fire its own scheduler. Three things make sure the drop still goes out:

1. **The in-process scheduler** fires at 08:00 if the API happens to be awake.
2. **A startup catch-up**: whenever the API starts on a Friday after 08:00, it sends that day's drop if it hasn't
   gone out yet.
3. **An external cron** calls `POST /internal/jobs/weekly-drop` with the `X-Job-Token` header. The call wakes the
   API, which then runs the catch-up. The endpoint answers `202` at once and does the work in the background.

All three paths claim the same `job_runs` row before running, and each member's message is recorded with the drop
date. Running the job twice, or all three at once, never sends anyone the drop twice. A member whose send failed is
retried on the next run.

#### Option A: cron-job.org (free, no code)

1. Copy `JOB_TOKEN` from the API service's **Environment** tab in Render.
2. On [cron-job.org](https://cron-job.org), create a cron job:
   - **URL**: `https://<your-api>.onrender.com/internal/jobs/weekly-drop`
   - **Request method**: POST (under Advanced)
   - **Headers**: `X-Job-Token: <JOB_TOKEN>`
   - **Schedule**: custom, *every 5 minutes, Fridays, 07:55–08:59*, time zone `Africa/Nairobi`
   - **Timeout**: the default 30 s is fine. The first call while the API is waking may time out; the next one
     succeeds, and the wake-up itself triggers the catch-up.
3. Use **Test run** and check for `202 {"due": false}`, which is the expected answer outside the drop time.

Pinging only in the Friday window, rather than all week, keeps the free instance asleep the rest of the time.

#### Option B: GitHub Actions

Add `JOB_TOKEN` and `API_URL` as repository secrets, then commit `.github/workflows/weekly-drop.yml`:

```yaml
name: Wake API for the Friday Drop
on:
  schedule:
    - cron: "*/10 5 * * 5"  # Fridays 05:00-05:50 UTC = 08:00-08:50 Nairobi
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: |
          for i in 1 2 3; do
            curl -fsS -X POST -H "X-Job-Token: ${{ secrets.JOB_TOKEN }}" \
              "${{ secrets.API_URL }}/internal/jobs/weekly-drop" && break
            sleep 60
          done
```

GitHub may start scheduled workflows a few minutes late; that's harmless here.

#### Checking it worked

- **Admin > Friday Drop > Preview next drop** shows the exact one-line WhatsApp text and who would get it.
- After 08:00 on a Friday, **Admin > WhatsApp nudges > Recent notifications** lists one `weekly_drop` row per
  opted-in member.
- With `WHATSAPP_PROVIDER=console`, which is the default, messages only go to the API logs as `[whatsapp -> …]`.

### WhatsApp templates

Messages a business starts need an approved Meta template. Template parameters can't contain newlines, tabs or more
than four spaces in a row, so the drop is sent as a single line: a two-sentence summary, the project titles, and a
link to `FRONTEND_URL/weekly`. The full summary and the quizzes stay in the web app.

1. In Meta Business Manager, create a template (category *Utility*, language *English*) whose body is a single
   variable, for example `{{1}}`.
2. Once it's approved, set these on the API:
   - `WHATSAPP_PROVIDER=meta`
   - `WHATSAPP_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_WEEKLY_TEMPLATE=<template name>`
3. Set `FRONTEND_URL` to the static site URL so the link works.

Admin alerts use the same template. These go to admins with a phone number when no class notes were added by Friday,
or when a quiz couldn't be generated. Only members with a phone number and WhatsApp opt-in get the drop; everyone
else sees it on `/weekly`.

### Quizzes and learning materials

- **Without notes there is nothing to send.** If nobody pastes class notes (`/weekly` or Admin > Friday Drop) for the
  coming Friday, the drop goes out without a summary or weekly quiz, and admins get a reminder. Nothing is
  generated from nothing.
- Admins add materials (pasted text, a URL, or `.md`/`.txt`/`.pdf` up to 5 MB) at **/admin/materials**. Only the
  extracted text is stored, in Postgres; Render's disk isn't used. Scanned PDFs with no text layer are refused.
- **Turning on review:** set `REQUIRE_QUIZ_REVIEW=true` and generated quizzes wait in **Admin > Learning
  materials > Quizzes** until published. With it off (the default), they go live straight away, and you can still
  edit or unpublish them.
- **Cost:** a weekly drop generates three quizzes (10, 20 and 30 minutes). A monthly drop adds three course
  quizzes and three interview quizzes per specialization in use. Generation uses the `generation` task's model
  (Admin > AI models, or `LLM_TASK_MODELS`); pick a cheaper one there to cut cost.

### Coding exercises: where code runs

Member code never runs on the API host. The default `CODE_RUNNER=none` runs it in the member's browser: Python
through [Pyodide](https://pyodide.org) (loaded from jsDelivr, pinned in `frontend/src/lib/runner/pyodide.worker.ts`)
and JavaScript in a sandboxed Web Worker. Browser runs can only use the visible tests, so they count as practice: a
full pass earns half the exercise's points.

For verified runs, which include hidden tests and earn full points, host a **Judge0-compatible sandbox on its own
isolated server**, separate from Render and from anything holding your data. Then set these on the API:

```
CODE_RUNNER=remote
CODE_RUNNER_URL=https://judge0.your-domain.example
CODE_RUNNER_KEY=<Judge0 AUTHN token>
```

Judge0 language ids are set in `backend/app/services/code_runner.py` (`python: 71`, `javascript: 63`, the Judge0 CE
defaults); change them if your instance numbers languages differently. If the sandbox is unreachable, submissions
fall back to the browser result and are marked unverified.

New exercises drafted from materials always need an admin to check them. **Admin > Learning materials > Coding
exercises > Verify in browser** runs the reference solution against every test, including hidden ones, before you
publish.

## AI models (OpenRouter)

All AI features (article grading, code feedback, weekly summaries, material digests, quiz and exercise generation)
go through [OpenRouter](https://openrouter.ai), via `backend/app/llm/`. The Anthropic SDK is no longer used.

### Render environment checklist (`classtrack-api` > Environment)

| Variable | Set it to | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | your key, `sk-or-v1-...` | Required for AI. Unset = AI features show "not configured" |
| `LLM_DEFAULT_MODEL` | `luna` | Blueprint default |
| `LLM_TASK_MODELS` | `generation=gemini-flash` | Blueprint default |
| `LLM_FALLBACK_MODELS` | `mistral-small,gemini-flash` | Blueprint default |
| `LLM_REQUIRE_ZDR` | leave unset (`true`) | Never `false` in production: it would let member data reach providers that may log it |
| `LLM_ANONYMIZE` | leave unset (`true`) | |
| `AI_RATE_LIMIT_PER_HOUR` | leave unset (`30`) | Raise only if members hit it in normal use |
| `LLM_STARTUP_CHECK` | leave unset (`true`) | |

Remove the old `ANTHROPIC_API_KEY`, `GRADING_MODEL` and `QUIZ_MODEL` if they're still set; they're ignored.

### One-time OpenRouter account setup

1. **Credits:** buy at least $10 once. Paid models fail with 402 without credit, and the free-model limit rises
   from 50 to 1,000 requests a day.
2. **Privacy** (Settings > Privacy): turn off training for paid and free models, and turn on Zero Data Retention
   for the account. The app already asks for this on every request; the account setting is the backstop.
3. **Key:** create a key for this app only, with a monthly credit limit (for example $5). That caps the worst case
   if something loops.
4. Leave prompt logging off.

### What happens at startup

The API checks its configuration before serving requests and **refuses to start** (the deploy fails, with the
reason in the logs) when:
- `OPENROUTER_API_KEY` is set but OpenRouter rejects it;
- a model setting names an unknown model or task, or a model without zero data retention while that's required;
- `JWT_SECRET` is still `change-me`, or `WHATSAPP_PROVIDER=meta` is missing its token or number id.

These only log a warning: no key at all (AI off), OpenRouter unreachable (so an OpenRouter outage can't block a
deploy), a key with no credit left, or a configured model OpenRouter no longer lists. The key check calls
OpenRouter's `/key` and `/models` endpoints, which don't run a model and cost nothing.

### Switching models and rolling back

- **Live:** Admin > AI models. Pick a model per task; it applies within about 30 seconds, no redeploy. "Reset" goes
  back to the env setting. Use **Test a model** to try one first (reply, latency, tokens, cost).
- **Rollback:** press Reset, or change `LLM_TASK_MODELS` / `LLM_DEFAULT_MODEL` in Render (redeploys in about a minute).
- **Adding a model:** add it to `backend/app/llm/registry.py` with its prices and whether it has a zero-retention
  provider (check https://openrouter.ai/api/v1/endpoints/zdr), then deploy.
- **Comparing models before switching:** from `backend/`, `python -m scripts.compare_models` runs one sample prompt on
  every registry model and prints reply, latency, tokens and cost; `--structured` grades a sample article with the
  real rubric to check each model returns valid JSON. A few cents per run; nothing is written to the database.
- **Comparing models in use:** Admin > AI models > Usage, `GET /admin/llm/usage?days=30`, or
  `python -m scripts.llm_usage --days 30` with `DATABASE_URL` set (read-only).

### Free-tier cold starts

A free Render web service sleeps after about 15 minutes without traffic, and the first request after that waits
for it to boot (often close to a minute). With AI:
- Grading, feedback, summaries and digests run in the background after the request returns, so members only wait
  for the boot; the page polls until the AI result is in.
- The test button, Generate quizzes, Generate exercises and Regenerate summary wait for the model. Generation can take
  a minute on its own, so after a cold start the browser may wait two. If it times out, try again: the server is
  awake by then.
- The startup key check adds at most a few seconds to a boot (8-second timeout per request; it never blocks).
- The AI rate-limit counters and the model-choice cache are in memory and reset on each boot. That's harmless:
  choices are re-read from the database.
- The external cron that wakes the API for the Friday Drop ([above](#waking-the-api-for-the-friday-drop)) also
  gives quiz generation a warm server.

## Challenge approvals

Members propose challenges (`/challenges/proposals`); they stay `pending`, unlisted and not joinable, until an admin
approves them at **/admin/challenges**. Status rules live in `backend/app/services/challenge_review.py`; admins and
members are notified in the app (the bell), through `backend/app/services/inbox.py`.

### Deploying it

- **No new environment variables.**
- **Migration `c8166f6654fb`** runs automatically: the API's start command is `alembic upgrade head && uvicorn …`,
  so it runs once when the new API instance starts, before it serves traffic. There's nothing to run by hand (and the
  free plan has no shell).
  - It adds `status`, `created_by`, `updated_at`, `reviewed_by`, `reviewed_at`, `review_note` to `challenges` and
    creates `inbox_messages`. Every existing challenge becomes `approved`, so nothing that's live disappears.
  - It's safe while the old API is still serving during the switch-over: old code never reads the new columns, and a
    challenge it creates gets the database default `approved` (only admins could create challenges before).
- **Order:** merge and deploy after the OpenRouter work (pull request #4); this branch's migration follows its two.
  Render deploys the API and the static site from the same commit; the site is usually live a few minutes before the
  API. In that window the new pages get 404s from the old API (the bell's badge stays quiet; the proposal pages show an
  error until the API is up). Deploying in a quiet hour is enough.
- **Before the first deploy, take a Neon backup branch** (Neon console > Branches > Create branch from `main`). It's
  instant and free, and makes rollback a restore rather than a migration.

### Rolling back

- **Code only (redeploy the previous commit):** the old code ignores the new columns, *but it lists every challenge*,
  so pending, rejected and cancelled proposals would show up as normal challenges members can join. Avoid this unless
  there are no proposals yet.
- **Code and schema:** `alembic downgrade f233d4c326a4` deletes every non-approved proposal (so they can't go live),
  then drops the new columns and the inbox. Approved challenges and their data are kept. Or restore the Neon backup
  branch.

### After deploying: smoke test

Sign in as a member and as an admin (an `ADMIN_EMAILS` address) and run the end-to-end checklist in the pull request:
propose → admin sees it in the bell and the queue → reject with a reason → member sees the reason → propose, edit,
approve with a note → member joins from /join → the detail page shows who approved it, when and why.

