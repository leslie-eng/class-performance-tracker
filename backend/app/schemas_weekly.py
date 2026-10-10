"""Request/response models for the Friday Drop and quizzes."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class BriefIn(BaseModel):
    source_notes: str = Field(min_length=20, max_length=50_000)


class BriefOut(BaseModel):
    id: int
    week_key: date
    status: str
    summary: str | None
    concepts: list[dict]
    summary_error: str | None
    has_notes: bool
    updated_at: datetime
    source_notes: str | None = None  # only on GET /weekly/brief (the notes form)


class ProposalIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=2000)


class ProposalOut(BaseModel):
    id: int
    week_key: date
    slot: int
    title: str
    description: str
    proposer_id: int
    proposer_name: str
    picks: int = 0
    picked_by_me: bool = False


class PickIn(BaseModel):
    proposal_id: int


class QuizSlot(BaseModel):
    kind: str
    period_key: str
    specialization: str | None
    duration_minutes: int
    question_count: int
    available: bool
    reason: str | None = None  # why it isn't available
    attempt_id: int | None = None
    submitted: bool = False
    score: float | None = None
    max_score: int | None = None


class UpcomingWeek(BaseModel):
    week_key: date
    projects: list[ProposalOut]
    slots_left: int
    my_proposal_id: int | None
    has_notes: bool


class WeeklyCurrent(BaseModel):
    week_key: date
    month_key: str
    server_now: datetime
    ai_configured: bool
    brief: BriefOut | None
    projects: list[ProposalOut]
    my_pick: int | None
    upcoming: UpcomingWeek
    quizzes: list[QuizSlot]


class AnswersIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


class AttemptOut(BaseModel):
    id: int
    quiz_id: int
    kind: str
    specialization: str | None
    duration_minutes: int
    started_at: datetime
    deadline_at: datetime  # includes the submit grace period
    ends_at: datetime  # what the countdown shows
    server_now: datetime
    submitted: bool
    late: bool = False
    questions: list[dict]  # no answer keys while open
    answers: dict[str, Any]
    # Only after submission:
    score: float | None = None
    max_score: int
    points_awarded: int = 0
    grading_status: str
    grading_error: str | None = None
    results: list[dict] | None = None


class QuizLeaderRow(BaseModel):
    rank: int
    user_id: int
    name: str
    points: int
    quizzes_taken: int
