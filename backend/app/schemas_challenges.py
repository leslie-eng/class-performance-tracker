"""Schemas for member challenge proposals and the admin approval queue."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import TaskTypes
from app.schemas import ChallengeOut

MAX_DAYS = 366


class ProposalIn(BaseModel):
    """What a member can propose. Scoring rules aren't accepted (they move everyone's points);
    an admin can change them after approval."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date
    end_date: date
    task_types_allowed: TaskTypes = TaskTypes.both

    @field_validator("name", "description")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_dates(self):
        check_dates(self.start_date, self.end_date)
        return self


class ProposalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    task_types_allowed: TaskTypes | None = None

    @field_validator("name", "description")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


def check_dates(start: date, end: date) -> None:
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"A challenge can last at most {MAX_DAYS} days")


class PersonRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProposalOut(ChallengeOut):
    """A challenge plus its review state, for its creator and admins."""

    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    review_note: str | None = None  # approval note, or the reason for a rejection


class AdminChallengeOut(ProposalOut):
    """Adds the audit trail: who proposed it and who reviewed it."""

    creator: PersonRef | None = None
    reviewer: PersonRef | None = None
    enrolled: int = 0


class AdminChallengePage(BaseModel):
    items: list[AdminChallengeOut]
    total: int
    limit: int
    offset: int


class ApproveIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RejectIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000, description="Reason shown to the member")
