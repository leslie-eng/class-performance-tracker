from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.deps import DB, AdminUser, CurrentUser, today
from app.models import ApplicationStatus, JobApplication
from app.schemas import (
    FeedItem,
    JobApplicationIn,
    JobApplicationOut,
    JobApplicationUpdate,
    JobStats,
    MyJobApplications,
)

router = APIRouter(prefix="/job-applications", tags=["job applications"])

FEED_STATUSES = (ApplicationStatus.interview, ApplicationStatus.offer)
CLOSED_STATUSES = (ApplicationStatus.offer, ApplicationStatus.rejected)


def job_stats(apps: list[JobApplication], on: date) -> JobStats:
    total = len(apps)
    responses = sum(a.status != ApplicationStatus.applied for a in apps)
    return JobStats(
        total=total,
        this_month=sum(a.date_applied.year == on.year and a.date_applied.month == on.month for a in apps),
        responses=responses,
        response_rate=round(responses / total, 3) if total else 0.0,
        interviews=sum(a.status in FEED_STATUSES for a in apps),
        offers=sum(a.status == ApplicationStatus.offer for a in apps),
        follow_ups_due=sum(
            a.follow_up_date is not None and a.follow_up_date <= on and a.status not in CLOSED_STATUSES
            for a in apps
        ),
    )


def user_applications(db: Session, user_id: int) -> list[JobApplication]:
    return list(
        db.scalars(
            select(JobApplication)
            .where(JobApplication.user_id == user_id)
            .order_by(JobApplication.date_applied.desc(), JobApplication.id.desc())
        ).all()
    )


@router.post("", response_model=JobApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: JobApplicationIn, db: DB, user: CurrentUser):
    app = JobApplication(**body.model_dump(), user_id=user.id)
    db.add(app)
    db.commit()
    return app


@router.get("/me", response_model=MyJobApplications)
def my_applications(db: DB, user: CurrentUser):
    apps = user_applications(db, user.id)
    return MyJobApplications(applications=apps, stats=job_stats(apps, today()))


@router.get("/feed", response_model=list[FeedItem])
def feed(db: DB, _: CurrentUser, days: int = 7):
    """Opt-in shout-outs: public entries that reached interview/offer recently."""
    since = datetime.now(timezone.utc) - timedelta(days=min(days, 90))
    apps = db.scalars(
        select(JobApplication)
        .where(
            JobApplication.is_public,
            JobApplication.status.in_(FEED_STATUSES),
            JobApplication.status_changed_at >= since,
        )
        .options(selectinload(JobApplication.user))
        .order_by(JobApplication.status_changed_at.desc())
    ).all()
    return [
        FeedItem(user_id=a.user_id, name=a.user.name, company=a.company, role=a.role, status=a.status, at=a.status_changed_at)
        for a in apps
    ]


@router.get("/user/{user_id}", response_model=MyJobApplications)
def member_applications(user_id: int, db: DB, _: AdminUser):
    if not get_settings().admin_can_view_job_applications:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin visibility of job applications is disabled")
    apps = user_applications(db, user_id)
    return MyJobApplications(applications=apps, stats=job_stats(apps, today()))


def _own_application(db: Session, app_id: int, user_id: int) -> JobApplication:
    app = db.get(JobApplication, app_id)
    if app is None or app.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


@router.patch("/{app_id}", response_model=JobApplicationOut)
def update_application(app_id: int, body: JobApplicationUpdate, db: DB, user: CurrentUser):
    app = _own_application(db, app_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] != app.status:
        app.status_changed_at = datetime.now(timezone.utc)
    for field, value in data.items():
        setattr(app, field, value)
    db.commit()
    return app


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: int, db: DB, user: CurrentUser):
    db.delete(_own_application(db, app_id, user.id))
    db.commit()
