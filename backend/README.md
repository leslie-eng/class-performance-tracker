# ClassTrack API

FastAPI backend for ClassTrack, built from `../classmate-tracker-design-doc.pdf`.

## Run it

```bash
python -m venv .venv && .venv/Scripts/activate      # or: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                 # then edit it
docker run -d --name classtrack-pg -e POSTGRES_USER=classtrack -e POSTGRES_PASSWORD=classtrack \
  -e POSTGRES_DB=classtrack -p 5432:5432 postgres:16-alpine
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive docs are at http://localhost:8000/docs. Register with an email listed in
`ADMIN_EMAILS` to get the admin role.

Demo data: on an **empty** database, `python -m scripts.seed_demo` creates a 9-person cohort; sign in as
`demo@classtrack.dev` / `password123` (admin). It refuses to run if any users exist.

Tests: `pytest`. They use SQLite by default; set `DATABASE_URL` to run them against Postgres.
**The tests drop and recreate every table in that database**, so point it at a throwaway one.

## Layout

```
app/
  main.py            app, CORS, starts the scheduler
  config.py          settings from env / .env
  models.py          SQLAlchemy models (design doc section 4)
  schemas.py         request/response models
  scoring.py         point model, streaks, recompute_enrollment()
  scheduler.py       APScheduler: nightly lag check, weekly digest
  routers/           auth, challenges, submissions, leaderboard, members, job_applications, admin
  services/
    grading.py       Claude API article grading + optional code review
    article_fetch.py URL fetch + boilerplate stripping (blocks private IPs)
    notifications.py lag detection, nudge messages, admin digest
    whatsapp.py      console sender (dev) / Meta Cloud API sender
    leaderboard.py   ranked queries
alembic/             migrations
```

## Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/register` | anyone | Create an account |
| POST | `/auth/login` | anyone | OAuth2 password form (`username` = email), returns a JWT |
| GET/PATCH | `/auth/me` | member | Profile, phone number, WhatsApp opt-in |
| POST | `/challenges` | admin | Create a challenge (optional `scoring_rules` overrides) |
| GET | `/challenges[?active_only=]`, `/challenges/{id}` | member | List / view |
| GET | `/challenges/mine` | member | Challenges I'm enrolled in |
| PATCH | `/challenges/{id}` | admin | Edit; changing rules recomputes everyone's points |
| POST/DELETE | `/challenges/{id}/enroll` | member | Join / leave. Leaving deletes that member's submissions for the challenge. |
| GET | `/challenges/{id}/members` | admin | Enrolled members |
| POST | `/submissions` | member | Code (`content` + `language`) or article (`content` = URL) |
| GET | `/submissions/me?challenge_id=` | member | My history |
| GET | `/submissions/{id}` | owner/admin | Poll for grading status |
| POST | `/submissions/{id}/regrade` | owner/admin | Retry a failed grading |
| GET | `/leaderboard/{challenge_id}`, `/leaderboard/global` | member | Rankings |
| GET | `/members` | admin | All members |
| GET | `/members/{id}/dashboard?month=YYYY-MM` | self/admin | Heatmap, streaks, points, ranks, recent submissions, job stats |
| POST | `/job-applications` | member | Log an application |
| GET | `/job-applications/me` | member | My applications + stats |
| PATCH/DELETE | `/job-applications/{id}` | owner | Update status etc. / delete |
| GET | `/job-applications/feed` | member | Opt-in (`is_public`) interview/offer shout-outs from the last 7 days |
| GET | `/job-applications/user/{id}` | admin | Only if `ADMIN_CAN_VIEW_JOB_APPLICATIONS=true` |
| POST | `/admin/notify/run?dry_run=true` | admin | Run the lag check now (dry run by default) |
| POST | `/admin/digest/run?dry_run=true` | admin | Build/send the admin digest |
| GET | `/admin/notifications` | admin | Notification log |
| PATCH | `/admin/submissions/{id}/grade` | admin | Override an AI score |
| POST | `/admin/recompute` | admin | Rebuild all cached stats |
| PATCH | `/admin/members/{id}/role?is_admin=` | admin | Grant/revoke admin |
| GET | `/meta` | anyone | Server timezone and today's date (for the deadline countdown) |

## Scoring

Defaults are in `app/scoring.py` (`DEFAULT_RULES`) and can be overridden per challenge:

| Rule | Default | |
|---|---|---|
| `code_points` / `article_points` | 10 / 15 | For the first submission of a day |
| `article_ai_bonus_max` | 10 | `round(ai_score / 10 * max)` |
| `streak_bonus_points` / `streak_bonus_every` | 5 / 7 | +5 per full 7-day run |
| `missed_day_penalty` | 0 | Points per missed past day |
| `backfill_days` | 1 | How late a task may be logged |
| `lag_threshold` | 2 | Missed days before a WhatsApp nudge |
| `ai_code_review` | false | AI comments on code submissions (no points) |
| `lag_message` | built in | Nudge template. Placeholders: `{name}` `{challenge}` `{days_missed}` `{streak_lost}` `{streak_clause}` `{group_avg}` `{points}` |

- Day numbers are counted from the challenge `start_date` (day 1) in `TIMEZONE`.
- A member may submit more than once per day. Only the first submission counts toward the streak and earns points; later ones still get AI feedback. A partial unique index enforces this.
- `enrollment_stats` is a cache built from submissions by `recompute_enrollment()`. It runs after every submission, grading, override, and rules change, and again in the nightly job.
- Ties on the leaderboard are broken by current streak. Members with equal points and equal streak share a rank.

## AI grading

When an article is submitted, the row is saved with `grading_status=pending` and a background task:

1. fetches the URL, checking every redirect hop against private/internal addresses;
2. strips boilerplate;
3. calls Claude (`claude-opus-5`) with the rubric from section 7 of the design doc, and stores the scores, overall feedback,
   and up to 3 strengths and 3 improvements (`ai_details`).

Without `ANTHROPIC_API_KEY`, articles are marked `failed` with a readable message (an admin can grade them by hand).

The call uses structured output (`messages.parse` with a Pydantic model) and server-side refusal fallbacks (`fallbacks="default"`). Article text is treated as untrusted input, so instructions inside an article are ignored. The frontend should poll `GET /submissions/{id}`. Pages that need a login or render with JavaScript fail with a readable message; an admin can then set the grade by hand.

Background tasks run in the API process. If grading volume grows, move `grade_submission` to a Celery/RQ worker. It already opens its own DB session.

## WhatsApp

`WHATSAPP_PROVIDER=console` logs messages instead of sending them. `meta` sends through the Meta Cloud API.

- Only members with a phone number and `whatsapp_opt_in=true` are messaged.
- A member gets at most one lagging alert per challenge per day.
- Every send is logged in `notifications`.
- Meta only allows free-form text inside the 24h window after the member has messaged the bot. Outside that window, set `WHATSAPP_LAG_TEMPLATE` to an approved template that has one body variable.

The scheduler runs inside the API process. If you run more than one replica, turn it on for exactly one (`SCHEDULER_ENABLED`).

## Design-doc open questions: defaults chosen

- **Missed days:** they break the streak and cost no points (`missed_day_penalty=0`, configurable).
- **Concurrent challenges:** supported. The global leaderboard sums across them.
- **Copy-paste checks:** trust-based. Admins can see all submissions and override grades.
- **WhatsApp opt-in:** explicit `whatsapp_opt_in` flag, plus template support for first contact.
