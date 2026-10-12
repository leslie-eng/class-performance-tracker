"""Request/response models for coding exercises. Member models never carry hidden tests
or the reference solution."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.coding import IDENT, MAX_CODE_CHARS


class TestCase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    args: list[Any]
    expected: Any
    hidden: bool = False


class VisibleTest(BaseModel):
    name: str
    args: list[Any]
    expected: Any


class ExerciseSummary(BaseModel):
    id: int
    title: str
    language: str
    difficulty: int
    points: int
    module: str
    week_key: date | None
    solved: bool = False  # all tests passed at least once
    verified: bool = False  # ...in the remote sandbox
    points_earned: int = 0
    attempts: int = 0


class AttemptOut(BaseModel):
    id: int
    exercise_id: int
    passed_count: int
    total_count: int
    runner: str
    verified: bool
    results: list[dict] | None
    runner_error: str | None
    grading_status: str
    ai_feedback: str | None
    points_awarded: int
    created_at: datetime


class ExerciseOut(ExerciseSummary):
    description_md: str
    starter_code: str
    entrypoint: str
    time_limit_seconds: int
    visible_tests: list[VisibleTest]
    hidden_test_count: int
    draft: str | None
    draft_updated_at: datetime | None
    runner: Literal["browser", "remote"]
    unverified_points: int  # what a browser-verified full pass earns
    recent_attempts: list[AttemptOut]


class DraftIn(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)


class BrowserResults(BaseModel):
    passed: int = Field(ge=0)
    total: int = Field(ge=0)


class SubmitIn(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    browser_results: BrowserResults | None = None  # self-reported; ignored when a remote runner is set


class ExerciseIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description_md: str = Field(min_length=1, max_length=20_000)
    language: Literal["python", "javascript"] = "python"
    starter_code: str = Field(default="", max_length=MAX_CODE_CHARS)
    entrypoint: str = Field(min_length=1, max_length=80)
    tests: list[TestCase] = Field(min_length=1, max_length=30)
    difficulty: int = Field(default=1, ge=1, le=5)
    points: int = Field(default=10, ge=1, le=100)
    module: str = Field(default="", max_length=120)
    week_key: date | None = None
    material_id: int | None = None
    time_limit_seconds: int = Field(default=10, ge=1, le=30)
    reference_solution: str | None = Field(default=None, max_length=MAX_CODE_CHARS)

    @field_validator("entrypoint")
    @classmethod
    def identifier(cls, v: str) -> str:
        if not IDENT.match(v):
            raise ValueError("must be a valid function name")
        return v

    @field_validator("tests")
    @classmethod
    def unique_names(cls, tests: list[TestCase]) -> list[TestCase]:
        if len({t.name for t in tests}) != len(tests):
            raise ValueError("test names must be unique")
        return tests


class ExerciseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description_md: str | None = Field(default=None, min_length=1, max_length=20_000)
    starter_code: str | None = Field(default=None, max_length=MAX_CODE_CHARS)
    entrypoint: str | None = Field(default=None, min_length=1, max_length=80)
    tests: list[TestCase] | None = Field(default=None, min_length=1, max_length=30)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    points: int | None = Field(default=None, ge=1, le=100)
    module: str | None = Field(default=None, max_length=120)
    week_key: date | None = None
    time_limit_seconds: int | None = Field(default=None, ge=1, le=30)
    reference_solution: str | None = Field(default=None, max_length=MAX_CODE_CHARS)
    status: Literal["draft", "published"] | None = None


class AdminExerciseOut(BaseModel):
    id: int
    title: str
    description_md: str
    language: str
    starter_code: str
    entrypoint: str
    tests: list[dict]  # including hidden
    difficulty: int
    points: int
    module: str
    week_key: date | None
    material_id: int | None
    time_limit_seconds: int
    status: str
    reference_solution: str | None
    tests_verified: bool
    created_at: datetime


class GenerateExercisesIn(BaseModel):
    material_ids: list[int] = Field(min_length=1)
    language: Literal["python", "javascript"] = "python"
    count: int = Field(default=1, ge=1, le=5)


class VerifyIn(BaseModel):
    passed: int = Field(ge=0)  # reference solution's browser run, reported by the admin UI
    total: int = Field(ge=0)
