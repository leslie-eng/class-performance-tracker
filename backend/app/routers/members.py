import calendar
from collections import Counter
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.deps import DB, AdminUser, CurrentUser, today
from app.models import Enrollment, Submission, User
from app.routers.job_applications import job_stats, user_applications
from app.schemas import ChallengeProgress, Dashboard, SubmissionOut, UserOut
from app.scoring import date_for_day
from app.services.leaderboard import challenge_leaderboard, global_leaderboard, rank_of

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=list[UserOut])
def list_members(db: DB, _: AdminUser):
    return db.scalars(select(User).order_by(User.name)).all()


@router.get("/{user_id}/dashboard", response_model=Dashboard)
def dashboard(
    user_id: int,
    db: DB,
    viewer: CurrentUser,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM, defaults to this month"),
    challenge_id: int | None = None,
):
    if viewer.id != user_id and not viewer.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only view your own dashboard")
    member = db.get(User, user_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    now = today()
    year, mon = map(int, month.split("-")) if month else (now.year, now.month)
    month_start = date(year, mon, 1)
    month_end = date(year, mon, calendar.monthrange(year, mon)[1])

    enrollments = db.scalars(
        select(Enrollment)
        .where(Enrollment.user_id == user_id)
        .options(selectinload(Enrollment.challenge), selectinload(Enrollment.stats))
    ).all()
    if challenge_id is not None:
        enrollments = [e for e in enrollments if e.challenge_id == challenge_id]

    heatmap: Counter[date] = Counter()
    progress: list[ChallengeProgress] = []
    for e in enrollments:
        counted_days = db.scalars(
            select(Submission.day_number).where(Submission.enrollment_id == e.id, Submission.counts_for_streak)
        ).all()
        for day in counted_days:
            d = date_for_day(e.challenge, day)
            if month_start <= d <= month_end:
                heatmap[d] += 1
        s = e.stats
        progress.append(
            ChallengeProgress(
                challenge_id=e.challenge_id,
                challenge=e.challenge.name,
                current_streak=s.current_streak if s else 0,
                longest_streak=s.longest_streak if s else 0,
                days_completed=s.days_completed if s else 0,
                total_days=e.challenge.total_days,
                total_points=s.total_points if s else 0,
                rank=rank_of(challenge_leaderboard(db, e.challenge_id), user_id),
            )
        )

    recent = db.scalars(
        select(Submission)
        .where(Submission.enrollment_id.in_([e.id for e in enrollments]))
        .order_by(Submission.submitted_at.desc())
        .limit(20)
    ).all()

    show_jobs = viewer.id == user_id or get_settings().admin_can_view_job_applications
    return Dashboard(
        user=UserOut.model_validate(member),
        month=f"{year:04d}-{mon:02d}",
        heatmap=dict(sorted(heatmap.items())),
        challenges=progress,
        total_points=sum(p.total_points for p in progress),
        global_rank=rank_of(global_leaderboard(db), user_id),
        recent_submissions=[SubmissionOut.model_validate(s) for s in recent],
        job_stats=job_stats(user_applications(db, user_id), now) if show_jobs else None,
    )
