"""Points, streaks and the cached per-enrollment stats.

Everything here is derived from the submissions table, so recompute_enrollment
can be re-run at any time (after a new submission, a grade override, a rules
change, or nightly) and always lands on the same answer.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Challenge, Enrollment, EnrollmentStats, Submission, SubmissionType

DEFAULT_RULES: dict = {
    "code_points": 10,
    "article_points": 15,
    "article_ai_bonus_max": 10,  # scaled from the 0-10 AI score
    "streak_bonus_points": 5,
    "streak_bonus_every": 7,  # +streak_bonus_points per N consecutive days
    "missed_day_penalty": 0,  # points deducted per missed (past) day
    "backfill_days": 1,  # how many days back a member may log a task for
    "lag_threshold": 2,  # consecutive missed days before a WhatsApp nudge
    "ai_code_review": False,  # optional AI comments on code (no effect on points)
}


def rules_for(challenge: Challenge) -> dict:
    return {**DEFAULT_RULES, **(challenge.scoring_rules or {})}


def day_number_for(challenge: Challenge, d: date) -> int:
    return (d - challenge.start_date).days + 1


def date_for_day(challenge: Challenge, day_number: int) -> date:
    return challenge.start_date + timedelta(days=day_number - 1)


def points_for_submission(sub: Submission, rules: dict) -> int:
    if not sub.counts_for_streak:
        return 0
    if sub.submission_type == SubmissionType.code:
        return rules["code_points"]
    points = rules["article_points"]
    if sub.ai_score is not None:
        points += round(sub.ai_score / 10 * rules["article_ai_bonus_max"])
    return points


@dataclass
class StreakInfo:
    current: int
    longest: int
    bonus_points: int
    runs: list[tuple[int, int]]  # (first_day, length)


def compute_streaks(days: set[int], ref_day: int, rules: dict) -> StreakInfo:
    """ref_day is "today" as a day number. A streak stays alive until the end of
    the day after the last submission, so not having submitted yet today doesn't
    reset it."""
    runs: list[tuple[int, int]] = []
    for d in sorted(days):
        if runs and runs[-1][0] + runs[-1][1] == d:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((d, 1))

    current = 0
    for start, length in runs:
        end = start + length - 1
        if end in (ref_day, ref_day - 1):
            current = length

    every = max(1, rules["streak_bonus_every"])
    bonus = sum(length // every for _, length in runs) * rules["streak_bonus_points"]
    return StreakInfo(
        current=current,
        longest=max((length for _, length in runs), default=0),
        bonus_points=bonus,
        runs=runs,
    )


def recompute_enrollment(db: Session, enrollment: Enrollment, today: date) -> EnrollmentStats:
    challenge = enrollment.challenge
    rules = rules_for(challenge)
    subs = db.scalars(select(Submission).where(Submission.enrollment_id == enrollment.id)).all()

    for sub in subs:
        sub.points_awarded = points_for_submission(sub, rules)

    counted_days = {s.day_number for s in subs if s.counts_for_streak}
    ref_day = min(day_number_for(challenge, today), challenge.total_days)
    streak = compute_streaks(counted_days, ref_day, rules)

    # Days strictly before today that have passed without a submission.
    elapsed = max(0, min(ref_day - 1, challenge.total_days))
    missed = max(0, elapsed - len([d for d in counted_days if d < ref_day]))
    penalty = missed * rules["missed_day_penalty"]

    stats = enrollment.stats or EnrollmentStats(enrollment_id=enrollment.id)
    stats.current_streak = streak.current
    stats.longest_streak = streak.longest
    stats.days_completed = len(counted_days)
    stats.last_submission_date = date_for_day(challenge, max(counted_days)) if counted_days else None
    stats.streak_bonus_points = streak.bonus_points
    stats.total_points = sum(s.points_awarded for s in subs) + streak.bonus_points - penalty
    if enrollment.stats is None:
        db.add(stats)
        enrollment.stats = stats
    return stats
