from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ClassTrack API"
    database_url: str = "postgresql+psycopg://classtrack:classtrack@localhost:5432/classtrack"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24 * 7
    # Emails that are made admins on registration (comma separated).
    admin_emails: str = ""
    # Job applications are private to each member unless the group opts in to admin visibility.
    admin_can_view_job_applications: bool = False

    # "Today" for day numbers, streaks and the nightly lag check.
    timezone: str = "UTC"

    # AI grading (Claude API). Grading is skipped when no key is configured.
    anthropic_api_key: str | None = None
    grading_model: str = "claude-opus-5"
    article_max_chars: int = 60_000

    # WhatsApp: "console" logs messages instead of sending; "meta" uses the Cloud API.
    whatsapp_provider: str = "console"
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_lag_template: str | None = None  # approved template name for first contact

    # Scheduler
    scheduler_enabled: bool = True
    lag_check_hour: int = 20
    weekly_digest_day: str = "sun"

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Member specializations (interview-prep quizzes); validated in schemas, not the DB.
    specializations: str = "data_engineering,data_science,software_engineering,ai_engineering,embedded_iot,general"

    # Friday Drop: weekly summary, project pick and quizzes.
    weekly_drop_day: str = "fri"
    weekly_drop_hour: int = 8
    monthly_quiz_week: str = "first"  # first | last
    quiz_model: str | None = None  # defaults to grading_model
    require_quiz_review: bool = False  # generated quizzes start as drafts when true
    frontend_url: str = "http://localhost:5173"  # for links in WhatsApp messages
    whatsapp_weekly_template: str | None = None
    # Shared secret for POST /internal/jobs/* (external cron). Endpoint is off when unset.
    job_token: str | None = None

    # Coding exercises: member code never runs on the API host. "remote" sends it to
    # an external sandbox (e.g. self-hosted Judge0); "none" means browser runs only.
    code_runner: str = "none"
    code_runner_url: str | None = None
    code_runner_key: str | None = None

    @field_validator("database_url")
    @classmethod
    def use_psycopg3(cls, url: str) -> str:
        # Hosts like Render/Railway/Neon hand out postgres:// or postgresql:// URLs,
        # which SQLAlchemy maps to psycopg2; we ship psycopg (v3).
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def specialization_list(self) -> list[str]:
        return [s.strip() for s in self.specializations.split(",") if s.strip()]

    @property
    def quiz_model_name(self) -> str:
        return self.quiz_model or self.grading_model

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
