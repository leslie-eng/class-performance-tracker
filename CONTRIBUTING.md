# Contributing to ClassTrack

Thanks for helping. This is a two-app monorepo: a FastAPI backend in [`backend/`](backend/) and a React + Vite
frontend in [`frontend/`](frontend/). Neither uses Docker. See [README.md](README.md) for the full setup reference
and [DEPLOYMENT.md](DEPLOYMENT.md) for production.

This guide is the short path from a fresh clone to a merged pull request.

---

## 1. Getting it running

### Option A: SQLite (fastest, no Postgres)

The migrations are dialect-portable, so the whole app runs on SQLite. This is the quickest way to get a working app
with demo data.

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt

# Any SQLite file path works; it is created on first use.
# Windows cmd:
set DATABASE_URL=sqlite:///./dev.db
set JWT_SECRET=a-dev-secret-that-is-at-least-32-bytes
set ADMIN_EMAILS=demo@classtrack.dev
set SCHEDULER_ENABLED=false

alembic upgrade head
python -m scripts.seed_demo        # refuses to run unless the database is empty
uvicorn app.main:app --reload
```

Then, in a second terminal:

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

Sign in at http://localhost:5173 with **`demo@classtrack.dev` / `password123`** (an admin in a 9-person demo cohort).

> **Windows note:** `pip.exe` may be blocked by an Application Control policy. Use `python -m pip` instead of `pip`,
> and `python -m pytest` instead of `pytest`.

### Option B: Postgres

Copy [`backend/.env.example`](backend/.env.example) to `backend/.env` and set `DATABASE_URL` to a local Postgres or a
free [Neon](https://neon.tech) database. Everything else is the same as above.

### How the two apps connect

In development the frontend calls `/api/*`, and Vite proxies that to `http://localhost:8000`, stripping the `/api`
prefix (see [`frontend/vite.config.ts`](frontend/vite.config.ts)). So you do **not** need `VITE_API_URL` or any CORS
setup while developing locally.

---

## 2. Quality gates

Run these before you open a pull request. CI runs the same commands on every PR (see
[issue #5](https://github.com/leslie-eng/class-performance-tracker/issues/5)) and must be green.

| Command | Where | What it does |
|---|---|---|
| `python -m pytest` | `backend/` | Backend tests. SQLite by default; **drops and recreates every table**, so point `DATABASE_URL` at a throwaway database. |
| `npm run lint` | `frontend/` | oxlint. Must report 0 errors. Please keep it at 0 warnings too. |
| `npm run build` | `frontend/` | Runs `tsc -b` then the Vite build, so this type-checks the app as well. |

> **`npm ci` vs `npm install`:** `npm ci` deletes `node_modules` first. On Windows, if the Vite dev server is
> running it holds a `tailwindcss-oxide` binary open, the delete fails partway, and you are left with a broken
> `node_modules`. **Stop the dev server before `npm ci`**, or just use `npm install`.

---

## 3. Pull request workflow

`main` is the default branch and every change lands through a pull request. Keep each PR to **one concern**.

```bash
git checkout main && git pull
git checkout -b <type>/<short-name>
# ... make your change, run the quality gates ...
git add -A
git commit -m "feat(web): add X"
git push -u origin <type>/<short-name>
```

Branch name prefixes:

| Prefix | Use for |
|---|---|
| `feature/` | New user-facing behaviour |
| `fix/` | Bug fixes |
| `refactor/` | Internal changes with no behaviour change |
| `perf/` | Performance work |
| `chore/` | Tooling, CI, dependencies, housekeeping |
| `docs/` | Documentation only |

Commit messages use a `type(scope): summary` subject, for example `fix(web): keep the grading page from crashing`.

**Reference the issue your PR closes** in the PR body, on its own line:

```
Closes #12
```

### PR checklist

- [ ] `python -m pytest` passes (backend changes).
- [ ] `npm run lint` and `npm run build` pass (frontend changes).
- [ ] The change is tested, and the PR says *how* you verified it — not just that it compiles.
- [ ] No secrets, no `.env` values, no generated files committed.
- [ ] Relevant docs updated (below).

---

## 4. Conventions that matter here

### Database changes need a migration

Any change to [`backend/app/models.py`](backend/app/models.py) needs an Alembic migration in
[`backend/alembic/versions/`](backend/alembic/versions/). Deploys run `alembic upgrade head`, so a model change
without a migration will break production.

Generate one with:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
# read the generated file, then:
alembic upgrade head
```

Keep migrations **dialect-portable** — the test suite runs on SQLite while production runs on Postgres. The partial
unique index in [`c334b8ee73bd_initial_schema.py`](backend/alembic/versions/c334b8ee73bd_initial_schema.py) is the
pattern to copy: it carries both `postgresql_where` and `sqlite_where`.

### Never commit secrets

`.env` files are gitignored. Use [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example) as templates, and never put real values in them. On Render, set
variables in each service's **Environment** tab. Read `JWT_SECRET` as 48+ random characters from
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

When you add a setting, add it to the environment table in [README.md](README.md#3-environment-variables) too.

### Comment style

Explain **why**, not what. The codebase follows this closely — see the CORS trailing-slash note in
[`backend/app/main.py`](backend/app/main.py) or the JSON-cast note in [`backend/app/models.py`](backend/app/models.py).
A comment that restates the code adds nothing; one that records a constraint or a past bug is worth its weight.

### Frontend structure

- Design tokens live in [`frontend/src/index.css`](frontend/src/index.css) under Tailwind v4 `@theme`. Prefer the
  tokens over hard-coded hex values.
- Shared presentational pieces live in [`frontend/src/components/ui.tsx`](frontend/src/components/ui.tsx).
- Server state goes through TanStack Query hooks in [`frontend/src/lib/queries.ts`](frontend/src/lib/queries.ts);
  all requests go through the single client in [`frontend/src/lib/api.ts`](frontend/src/lib/api.ts).
- Keep component files to component-only exports so React Fast Refresh keeps working (this is enforced by oxlint).

### The mockups are a guide, not a contract

The UI was built from the Stitch screens in `stitch_classtrack_study_platform/`. Where the backend has no data for
something a mockup shows, the app shows real data or omits it — it does not invent numbers. Those deliberate
divergences are listed in [`frontend/README.md`](frontend/README.md). If your PR introduces another one, add it there.

---

## 5. Where to start

Issues labelled `good first issue` are scoped to be self-contained. If you are unsure where a change belongs, open
an issue or ask on the pull request before writing a lot of code.
