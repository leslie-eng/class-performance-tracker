import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def str_enum(e: type[enum.Enum]) -> Enum:
    # Stored as VARCHAR so adding a value never needs a Postgres enum migration.
    return Enum(e, native_enum=False, length=32, values_callable=lambda x: [m.value for m in x])


class TaskTypes(str, enum.Enum):
    code = "code"
    article = "article"
    both = "both"


class SubmissionType(str, enum.Enum):
    code = "code"
    article = "article"


class GradingStatus(str, enum.Enum):
    not_applicable = "not_applicable"
    pending = "pending"
    done = "done"
    failed = "failed"


class NotificationType(str, enum.Enum):
    lagging_alert = "lagging_alert"
    weekly_digest = "weekly_digest"


class NotificationStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"


class ApplicationStatus(str, enum.Enum):
    applied = "applied"
    oa = "oa"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class ApplicationSource(str, enum.Enum):
    linkedin = "linkedin"
    referral = "referral"
    company_site = "company_site"
    other = "other"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    task_types_allowed: Mapped[TaskTypes] = mapped_column(str_enum(TaskTypes), default=TaskTypes.both)
    # Overrides on top of scoring.DEFAULT_RULES; see app/scoring.py.
    scoring_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="challenge", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def total_days(self) -> int:
        return (self.end_date - self.start_date).days + 1


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "challenge_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="enrollments")
    challenge: Mapped[Challenge] = relationship(back_populates="enrollments")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="enrollment", cascade="all, delete-orphan", passive_deletes=True)
    stats: Mapped["EnrollmentStats | None"] = relationship(back_populates="enrollment", uselist=False, cascade="all, delete-orphan", passive_deletes=True)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        # Only one submission per enrollment per day may count toward the streak.
        Index(
            "uq_submission_counted_day",
            "enrollment_id",
            "day_number",
            unique=True,
            postgresql_where=text("counts_for_streak"),
            sqlite_where=text("counts_for_streak"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    submission_type: Mapped[SubmissionType] = mapped_column(str_enum(SubmissionType))
    content: Mapped[str] = mapped_column(Text)  # code text or article URL
    language: Mapped[str | None] = mapped_column(String(40))
    problem_link: Mapped[str | None] = mapped_column(String(500))
    counts_for_streak: Mapped[bool] = mapped_column(Boolean, default=True)

    grading_status: Mapped[GradingStatus] = mapped_column(
        str_enum(GradingStatus), default=GradingStatus.not_applicable
    )
    ai_score: Mapped[float | None] = mapped_column(Float)
    ai_breakdown: Mapped[dict | None] = mapped_column(JSON)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    ai_details: Mapped[dict | None] = mapped_column(JSON)  # article title, strengths, improvements
    grade_overridden: Mapped[bool] = mapped_column(Boolean, default=False)

    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    enrollment: Mapped[Enrollment] = relationship(back_populates="submissions")


class EnrollmentStats(Base):
    """Cached streak/points per enrollment ("Streak" in the design doc).

    Always rebuilt from submissions by scoring.recompute_enrollment, so it can be
    dropped and regenerated at any time.
    """

    __tablename__ = "enrollment_stats"

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), primary_key=True
    )
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_submission_date: Mapped[date | None] = mapped_column(Date)
    days_completed: Mapped[int] = mapped_column(Integer, default=0)
    streak_bonus_points: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    enrollment: Mapped[Enrollment] = relationship(back_populates="stats")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    challenge_id: Mapped[int | None] = mapped_column(ForeignKey("challenges.id", ondelete="SET NULL"))
    type: Mapped[NotificationType] = mapped_column(str_enum(NotificationType))
    message_sent: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_on: Mapped[date] = mapped_column(Date, index=True)  # local date, for de-duplication
    status: Mapped[NotificationStatus] = mapped_column(str_enum(NotificationStatus))
    error: Mapped[str | None] = mapped_column(Text)


class JobApplication(Base):
    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    date_applied: Mapped[date] = mapped_column(Date)
    status: Mapped[ApplicationStatus] = mapped_column(str_enum(ApplicationStatus), default=ApplicationStatus.applied)
    source: Mapped[ApplicationSource] = mapped_column(str_enum(ApplicationSource), default=ApplicationSource.other)
    notes: Mapped[str | None] = mapped_column(Text)
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()
