from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator

from app.config import get_settings
from app.models import (
    ApplicationSource,
    ApplicationStatus,
    GradingStatus,
    SubmissionType,
    TaskTypes,
)
from app.scoring import DEFAULT_RULES


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users -----------------------------------------------------------

class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str | None = Field(default=None, pattern=r"^\+?[1-9]\d{7,14}$")
    whatsapp_opt_in: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr
    phone_number: str | None
    is_admin: bool
    whatsapp_opt_in: bool
    specialization: str | None = None
    joined_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone_number: str | None = Field(default=None, pattern=r"^\+?[1-9]\d{7,14}$")
    whatsapp_opt_in: bool | None = None
    specialization: str | None = None

    @field_validator("specialization")
    @classmethod
    def known_specialization(cls, value: str | None) -> str | None:
        allowed = get_settings().specialization_list
        if value is not None and value not in allowed:
            raise ValueError(f"must be one of: {', '.join(allowed)}")
        return value


# --- challenges ------------------------------------------------------------

class ScoringRules(BaseModel):
    """Partial override of the default point model; unknown keys rejected."""

    model_config = ConfigDict(extra="forbid")

    code_points: int | None = Field(default=None, ge=0)
    article_points: int | None = Field(default=None, ge=0)
    article_ai_bonus_max: int | None = Field(default=None, ge=0)
    streak_bonus_points: int | None = Field(default=None, ge=0)
    streak_bonus_every: int | None = Field(default=None, ge=1)
    missed_day_penalty: int | None = Field(default=None, ge=0)
    backfill_days: int | None = Field(default=None, ge=0, le=30)
    lag_threshold: int | None = Field(default=None, ge=1)
    ai_code_review: bool | None = None
    lag_message: str | None = Field(default=None, max_length=1000)

    def overrides(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ChallengeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    start_date: date
    end_date: date
    task_types_allowed: TaskTypes = TaskTypes.both
    scoring_rules: ScoringRules = ScoringRules()

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ChallengeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    end_date: date | None = None
    task_types_allowed: TaskTypes | None = None
    scoring_rules: ScoringRules | None = None


class ChallengeOut(ORM):
    id: int
    name: str
    description: str | None
    start_date: date
    end_date: date
    total_days: int
    task_types_allowed: TaskTypes
    scoring_rules: dict
    effective_rules: dict = {}

    @model_validator(mode="after")
    def fill_rules(self):
        self.effective_rules = {**DEFAULT_RULES, **self.scoring_rules}
        return self


class EnrollmentOut(ORM):
    id: int
    user_id: int
    challenge_id: int
    joined_at: datetime


# --- submissions ------------------------------------------------------------

class SubmissionIn(BaseModel):
    challenge_id: int
    submission_type: SubmissionType
    content: str = Field(min_length=1, max_length=50_000, description="Code text, or the article URL")
    language: str | None = Field(default=None, max_length=40)
    problem_link: HttpUrl | None = None
    day_number: int | None = Field(default=None, ge=1, description="Defaults to today's day in the challenge")

    @model_validator(mode="after")
    def check_type(self):
        if self.submission_type == SubmissionType.article:
            HttpUrl(self.content.strip())  # raises if not a URL
            self.content = self.content.strip()
        elif not self.language:
            raise ValueError("language is required for code submissions")
        return self


class SubmissionOut(ORM):
    id: int
    enrollment_id: int
    day_number: int
    submission_type: SubmissionType
    content: str
    language: str | None
    problem_link: str | None
    counts_for_streak: bool
    grading_status: GradingStatus
    ai_score: float | None
    ai_breakdown: dict | None
    ai_feedback: str | None
    ai_details: dict | None
    grade_overridden: bool
    points_awarded: int
    submitted_at: datetime


class GradeOverride(BaseModel):
    ai_score: float = Field(ge=0, le=10)
    ai_feedback: str | None = None


# --- leaderboard / dashboard -----------------------------------------------

class LeaderboardRow(BaseModel):
    rank: int
    user_id: int
    name: str
    total_points: int
    current_streak: int
    longest_streak: int
    days_completed: int
    avg_ai_score: float | None = None


class ChallengeProgress(BaseModel):
    challenge_id: int
    challenge: str
    current_streak: int
    longest_streak: int
    days_completed: int
    total_days: int
    total_points: int
    rank: int | None


class Dashboard(BaseModel):
    user: UserOut
    month: str
    heatmap: dict[date, int]  # date -> number of counted submissions that day
    challenges: list[ChallengeProgress]
    total_points: int
    global_rank: int | None
    recent_submissions: list[SubmissionOut]
    job_stats: "JobStats | None"


# --- job applications ------------------------------------------------------

class JobApplicationIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    date_applied: date
    status: ApplicationStatus = ApplicationStatus.applied
    source: ApplicationSource = ApplicationSource.other
    notes: str | None = None
    follow_up_date: date | None = None
    is_public: bool = False


class JobApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    date_applied: date | None = None
    status: ApplicationStatus | None = None
    source: ApplicationSource | None = None
    notes: str | None = None
    follow_up_date: date | None = None
    is_public: bool | None = None


class JobApplicationOut(ORM):
    id: int
    user_id: int
    company: str
    role: str
    date_applied: date
    status: ApplicationStatus
    source: ApplicationSource
    notes: str | None
    follow_up_date: date | None
    is_public: bool
    created_at: datetime
    updated_at: datetime


class JobStats(BaseModel):
    total: int
    this_month: int
    responses: int
    response_rate: float  # share of applications that got past "applied"
    interviews: int
    offers: int
    follow_ups_due: int


class MyJobApplications(BaseModel):
    applications: list[JobApplicationOut]
    stats: JobStats


class FeedItem(BaseModel):
    user_id: int
    name: str
    company: str
    role: str
    status: ApplicationStatus
    at: datetime


Dashboard.model_rebuild()
