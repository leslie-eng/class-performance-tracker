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


def as_utc(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes even for timezone=True columns.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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
    weekly_drop = "weekly_drop"
    monthly_quizzes = "monthly_quizzes"
    admin_alert = "admin_alert"  # missing notes, failed quiz generation


class BriefStatus(str, enum.Enum):
    draft = "draft"  # notes in, no summary yet
    ready = "ready"  # summary generated
    sent = "sent"  # included in a Friday drop


class MaterialKind(str, enum.Enum):
    text = "text"
    url = "url"
    file = "file"


class MaterialStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class ExerciseStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class RunnerKind(str, enum.Enum):
    browser = "browser"  # self-reported, visible tests only
    remote = "remote"  # external sandbox, all tests


class QuizKind(str, enum.Enum):
    weekly = "weekly"
    interview = "interview"
    course = "course"


class QuizStatus(str, enum.Enum):
    generating = "generating"
    failed = "failed"
    draft = "draft"  # awaiting admin review (REQUIRE_QUIZ_REVIEW)
    published = "published"


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
    specialization: Mapped[str | None] = mapped_column(String(40))  # one of settings.specialization_list
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


# --- Friday Drop -------------------------------------------------------------
# week_key is the date of the Friday drop a row belongs to (see app/weeks.py).


class WeeklyBrief(Base):
    __tablename__ = "weekly_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_key: Mapped[date] = mapped_column(Date, unique=True)
    source_notes: Mapped[str] = mapped_column(Text)  # raw class notes, untrusted
    summary: Mapped[str | None] = mapped_column(Text)
    concepts: Mapped[list] = mapped_column(JSON, default=list)  # [{title, one_liner}]
    summary_error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BriefStatus] = mapped_column(str_enum(BriefStatus), default=BriefStatus.draft)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectProposal(Base):
    __tablename__ = "project_proposals"
    # The two-slot cap and one-proposal-per-member are database guarantees.
    __table_args__ = (UniqueConstraint("week_key", "slot"), UniqueConstraint("week_key", "proposer_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    week_key: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[int] = mapped_column(Integer)  # 1 or 2
    proposer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    proposer: Mapped[User] = relationship()


class ProjectPick(Base):
    __tablename__ = "project_picks"
    __table_args__ = (UniqueConstraint("week_key", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    week_key: Mapped[date] = mapped_column(Date, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    proposal_id: Mapped[int] = mapped_column(ForeignKey("project_proposals.id", ondelete="CASCADE"), index=True)
    picked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[QuizKind] = mapped_column(str_enum(QuizKind))
    period_key: Mapped[str] = mapped_column(String(10))  # week "2026-10-16" or month "2026-10"
    specialization: Mapped[str | None] = mapped_column(String(40))  # interview quizzes only
    duration_minutes: Mapped[int] = mapped_column(Integer)
    # kind|period|specialization|duration. One non-null key, because a unique constraint
    # over a nullable specialization would let duplicate weekly/course quizzes through.
    cache_key: Mapped[str] = mapped_column(String(100), unique=True)
    questions: Mapped[list] = mapped_column(JSON, default=list)  # ordered easy -> hard
    status: Mapped[QuizStatus] = mapped_column(str_enum(QuizStatus), default=QuizStatus.generating)
    error: Mapped[str | None] = mapped_column(Text)
    source_material_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (UniqueConstraint("quiz_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answers: Mapped[dict] = mapped_column(JSON, default=dict)  # question id -> option index | text
    score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[int] = mapped_column(Integer, default=0)
    per_question: Mapped[list | None] = mapped_column(JSON)
    grading_status: Mapped[GradingStatus] = mapped_column(
        str_enum(GradingStatus), default=GradingStatus.not_applicable
    )
    grading_error: Mapped[str | None] = mapped_column(Text)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)

    quiz: Mapped[Quiz] = relationship()
    user: Mapped[User] = relationship()


class JobRun(Base):
    """Claim row for scheduled jobs, so the scheduler, the startup catch-up and the
    external cron can't run the same drop twice at once."""

    __tablename__ = "job_runs"
    __table_args__ = (UniqueConstraint("job", "run_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(40))
    run_key: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16))  # running | done | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text)


# --- Learning materials (admin only) ------------------------------------------------


class LearningMaterial(Base):
    """Admin-curated course material. Only extracted text is stored (no files: Render's
    disk is ephemeral). Contents are untrusted when sent to Claude; log ids, never text."""

    __tablename__ = "learning_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[MaterialKind] = mapped_column(str_enum(MaterialKind))
    content_text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    digest: Mapped[str | None] = mapped_column(Text)  # Claude summary + key terms, made once at ingest
    digest_error: Mapped[str | None] = mapped_column(Text)
    module: Mapped[str] = mapped_column(String(120), default="", index=True)
    week_key: Mapped[date | None] = mapped_column(Date, index=True)
    specialization: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[MaterialStatus] = mapped_column(str_enum(MaterialStatus), default=MaterialStatus.active)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    char_count: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# --- Coding exercises ------------------------------------------------------------------
# Member code is stored here and, at most, forwarded to an external sandbox. It is never
# executed on the API host.


class CodingExercise(Base):
    __tablename__ = "coding_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description_md: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20))  # python | javascript
    starter_code: Mapped[str] = mapped_column(Text)
    entrypoint: Mapped[str] = mapped_column(String(80))  # function the tests call
    tests: Mapped[list] = mapped_column(JSON, default=list)  # [{name, args, expected, hidden}]
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    points: Mapped[int] = mapped_column(Integer, default=10)
    module: Mapped[str] = mapped_column(String(120), default="")
    week_key: Mapped[date | None] = mapped_column(Date)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("learning_materials.id", ondelete="SET NULL"))
    time_limit_seconds: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[ExerciseStatus] = mapped_column(str_enum(ExerciseStatus), default=ExerciseStatus.draft)
    reference_solution: Mapped[str | None] = mapped_column(Text)  # admin only
    tests_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # reference passes every test
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CodeDraft(Base):
    __tablename__ = "code_drafts"
    __table_args__ = (UniqueConstraint("exercise_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("coding_exercises.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CodeAttempt(Base):
    __tablename__ = "code_attempts"
    __table_args__ = (Index("ix_code_attempts_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("coding_exercises.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(Text)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    runner: Mapped[RunnerKind] = mapped_column(str_enum(RunnerKind))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list | None] = mapped_column(JSON)  # visible-test details from a remote run
    runner_error: Mapped[str | None] = mapped_column(Text)
    grading_status: Mapped[GradingStatus] = mapped_column(str_enum(GradingStatus), default=GradingStatus.pending)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    exercise: Mapped[CodingExercise] = relationship()
