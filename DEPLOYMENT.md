# Deployment notes: Friday Drop, quizzes and coding exercises

These are the operational extras on top of the basic Render setup in [README.md](README.md#4-deploying-on-render).
Every variable named here is described in the README's
[environment table](README.md#backend-classtrack-api).

## What happens on deploy

The API's start command runs `alembic upgrade head`, so the new tables are created on the first deploy. There are
three migrations: the weekly drop and quizzes, the learning materials, and the coding exercises. Nothing else needs
running by hand.

If you deploy with the Blueprint, the new variables are created with it, including a generated `JOB_TOKEN`.
`TIMEZONE` now defaults to `Africa/Nairobi`. That also moves "today" for streaks and the 20:00 lag check.

## Waking the API for the Friday Drop

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

### Option A: cron-job.org (free, no code)

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

### Option B: GitHub Actions

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

### Checking it worked

- **Admin > Friday Drop > Preview next drop** shows the exact one-line WhatsApp text and who would get it.
- After 08:00 on a Friday, **Admin > WhatsApp nudges > Recent notifications** lists one `weekly_drop` row per
  opted-in member.
- With `WHATSAPP_PROVIDER=console`, which is the default, messages only go to the API logs as `[whatsapp -> …]`.

## WhatsApp templates

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

## Quizzes and learning materials

- **Without notes there is nothing to send.** If nobody pastes class notes (`/weekly` or Admin > Friday Drop) for the
  coming Friday, the drop goes out without a summary or weekly quiz, and admins get a reminder. Nothing is
  generated from nothing.
- Admins add materials (pasted text, a URL, or `.md`/`.txt`/`.pdf` up to 5 MB) at **/admin/materials**. Only the
  extracted text is stored, in Postgres; Render's disk isn't used. Scanned PDFs with no text layer are refused.
- **Turning on review:** set `REQUIRE_QUIZ_REVIEW=true` and generated quizzes wait in **Admin > Learning
  materials > Quizzes** until published. With it off (the default), they go live straight away, and you can still
  edit or unpublish them.
- **Cost:** a weekly drop generates three quizzes (10, 20 and 30 minutes). A monthly drop adds three course
  quizzes and three interview quizzes per specialization in use. Point `QUIZ_MODEL` at a cheaper Claude model to cut
  generation cost; grading keeps using `GRADING_MODEL`.

## Coding exercises: where code runs

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
