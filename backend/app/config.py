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
    grading_model: str = "claude-opus-5-5"
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
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
