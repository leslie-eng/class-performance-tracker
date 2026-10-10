"""Admin-only request/response models for learning materials and quiz review."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.config import get_settings


def _known_specialization(value: str | None) -> str | None:
    if value is not None and value not in get_settings().specialization_list:
        raise ValueError(f"must be one of: {', '.join(get_settings().specialization_list)}")
    return value


class MaterialIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "url"]
    text: str | None = None
    url: HttpUrl | None = None
    module: str = Field(default="", max_length=120)
    week_key: date | None = None
    specialization: str | None = None

    _spec = field_validator("specialization")(_known_specialization)

    @model_validator(mode="after")
    def source_matches_kind(self):
        if self.kind == "text" and not (self.text and self.text.strip()):
            raise ValueError("text is required for pasted materials")
        if self.kind == "url" and not self.url:
            raise ValueError("url is required for URL materials")
        return self


class MaterialUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    module: str | None = Field(default=None, max_length=120)
    week_key: date | None = None
    specialization: str | None = None
    status: Literal["active", "archived"] | None = None
    content_text: str | None = None  # replaces the text (and regenerates the digest)

    _spec = field_validator("specialization")(_known_specialization)


class MaterialSummary(BaseModel):
    id: int
    title: str
    kind: str
    module: str
    week_key: date | None
    specialization: str | None
    status: str
    source_url: str | None
    original_filename: str | None
    char_count: int
    digest_ready: bool
    digest_error: str | None
    created_at: datetime


class MaterialOut(MaterialSummary):
    content_text: str
    digest: str | None
    quiz_ids: list[int]


class GenerateQuizIn(BaseModel):
    kind: Literal["weekly", "interview", "course"]
    material_ids: list[int] | None = None
    module: str | None = None
    week_key: date | None = None  # weekly: which drop; monthly kinds: month of this date
    specialization: str | None = None
    durations: list[Literal[10, 20, 30]] = Field(default_factory=lambda: [10, 20, 30], min_length=1)

    _spec = field_validator("specialization")(_known_specialization)


class QuizQuestionIn(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    type: Literal["mcq", "short"]
    difficulty: int = Field(ge=1, le=5)
    prompt: str = Field(min_length=1, max_length=4000)
    options: list[str] | None = None
    answer_key: int | str
    explanation: str = Field(default="", max_length=4000)
    points: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def consistent(self):
        if self.type == "mcq":
            if not self.options or len(self.options) < 2 or not all(o.strip() for o in self.options):
                raise ValueError("multiple-choice questions need at least 2 non-empty options")
            if not isinstance(self.answer_key, int) or not 0 <= self.answer_key < len(self.options):
                raise ValueError("answer_key must be the index of the correct option")
        else:
            if not isinstance(self.answer_key, str) or not self.answer_key.strip():
                raise ValueError("short-answer questions need a model answer")
            self.options = None
        return self


class QuizUpdate(BaseModel):
    questions: list[QuizQuestionIn] | None = Field(default=None, min_length=1)
    status: Literal["draft", "published"] | None = None


class SourceRef(BaseModel):
    id: int
    title: str


class AdminQuizSummary(BaseModel):
    id: int
    kind: str
    period_key: str
    specialization: str | None
    duration_minutes: int
    status: str
    error: str | None
    question_count: int
    attempts: int
    sources: list[SourceRef]
    created_at: datetime


class AdminQuizOut(AdminQuizSummary):
    questions: list[dict]  # includes answer keys and explanations
