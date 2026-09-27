# ClassTrack frontend

React + TypeScript + Vite + Tailwind v4, built from the Stitch screens in
`../stitch_classtrack_study_platform` and wired to the FastAPI backend in `../backend`.

## Run it

```bash
# 1. backend (see ../backend/README.md), on :8000
# 2. frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

For a demo cohort to click around in, seed an **empty** database from `backend/`:
`python -m scripts.seed_demo`, then sign in as `demo@classtrack.dev` / `password123` (admin).

`npm run build` type-checks and produces `dist/`. Set `VITE_API_URL` when the API lives on another origin
(and add that origin to the backend's `CORS_ORIGINS`).

## Screens

| Route | Stitch screen | Data |
|---|---|---|
| `/login` | login_welcome | `POST /auth/login`, `/auth/register` |
| `/` | member_dashboard | `/submissions/me`, `/leaderboard/{id}`, `/meta` |
| `/submit` | submit_daily_task | `POST /submissions` |
| `/leaderboard` | cohort_leaderboard | `/leaderboard/{id}`, `/leaderboard/global` |
| `/grading/:id` | ai_grading_results | `/submissions/{id}` (polls while grading) |
| `/jobs` | job_application_tracker | `/job-applications/*` |
| `/join`, `/settings`, `/admin` | not in the mockups | enrolment, WhatsApp opt-in, admin tools |

Design tokens (colors, type scale, shadows) from `classtrack/DESIGN.md` live in `src/index.css` under `@theme`.

## Where the UI differs from the mockups

The mockups include things the backend doesn't have. Rather than show made-up numbers, these were dropped or swapped for real data:

- Google/GitHub sign-in, search, notification bell: not built (email + password only).
- "Today's challenge" titles/specs per day: the backend has no per-day prompts, so the card shows the day number and challenge description.
- Local test runner, lint status, reflection text, GitHub sync: removed from Submit. Drafts auto-save to the browser instead.
- Weekly rank trend, "this week / this month" leaderboard tabs: no history is stored. The toggle is challenge vs. global.
- Cohort percentiles, confidence, turnaround time, PDF export on the grading page: not produced by the grader. The page shows the real rubric scores, feedback, strengths and improvements.
- Job cards: salary, interview times and tags aren't in the data model. Cards show source, dates, follow-ups and notes.
