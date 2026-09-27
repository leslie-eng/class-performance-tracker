"""Leaderboards read from the cached enrollment_stats table.

Ranking: total points, ties broken by current streak (design doc 3.4). Rows
that tie on both share a rank ("1, 2, 2, 4").
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Enrollment, EnrollmentStats, Submission, User
from app.schemas import LeaderboardRow


def _avg_ai_scores(db: Session, challenge_id: int | None = None) -> dict[int, float]:
    q = (
        select(Enrollment.user_id, func.avg(Submission.ai_score))
        .join(Submission, Submission.enrollment_id == Enrollment.id)
        .where(Submission.ai_score.is_not(None))
        .group_by(Enrollment.user_id)
    )
    if challenge_id is not None:
        q = q.where(Enrollment.challenge_id == challenge_id)
    return {user_id: round(float(avg), 1) for user_id, avg in db.execute(q)}


def _ranked(rows, ai_scores: dict[int, float]) -> list[LeaderboardRow]:
    out: list[LeaderboardRow] = []
    prev_key, rank = None, 0
    for i, r in enumerate(rows, start=1):
        key = (r.total_points, r.current_streak)
        if key != prev_key:
            rank, prev_key = i, key
        out.append(
            LeaderboardRow(
                rank=rank,
                user_id=r.user_id,
                name=r.name,
                total_points=r.total_points or 0,
                current_streak=r.current_streak or 0,
                longest_streak=r.longest_streak or 0,
                days_completed=r.days_completed or 0,
                avg_ai_score=ai_scores.get(r.user_id),
            )
        )
    return out


def challenge_leaderboard(db: Session, challenge_id: int) -> list[LeaderboardRow]:
    points = func.coalesce(EnrollmentStats.total_points, 0)
    streak = func.coalesce(EnrollmentStats.current_streak, 0)
    rows = db.execute(
        select(
            User.id.label("user_id"),
            User.name,
            points.label("total_points"),
            streak.label("current_streak"),
            EnrollmentStats.longest_streak,
            EnrollmentStats.days_completed,
        )
        .select_from(Enrollment)
        .join(User, User.id == Enrollment.user_id)
        .outerjoin(EnrollmentStats, EnrollmentStats.enrollment_id == Enrollment.id)
        .where(Enrollment.challenge_id == challenge_id)
        .order_by(points.desc(), streak.desc(), User.name)
    ).all()
    return _ranked(rows, _avg_ai_scores(db, challenge_id))


def global_leaderboard(db: Session) -> list[LeaderboardRow]:
    points = func.coalesce(func.sum(EnrollmentStats.total_points), 0)
    streak = func.coalesce(func.max(EnrollmentStats.current_streak), 0)
    rows = db.execute(
        select(
            User.id.label("user_id"),
            User.name,
            points.label("total_points"),
            streak.label("current_streak"),
            func.max(EnrollmentStats.longest_streak).label("longest_streak"),
            func.sum(EnrollmentStats.days_completed).label("days_completed"),
        )
        .select_from(Enrollment)
        .join(User, User.id == Enrollment.user_id)
        .outerjoin(EnrollmentStats, EnrollmentStats.enrollment_id == Enrollment.id)
        .group_by(User.id, User.name)
        .order_by(points.desc(), streak.desc(), User.name)
    ).all()
    return _ranked(rows, _avg_ai_scores(db))


def rank_of(rows: list[LeaderboardRow], user_id: int) -> int | None:
    return next((r.rank for r in rows if r.user_id == user_id), None)
