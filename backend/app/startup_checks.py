"""Startup validation checks to catch common configuration errors early."""

import logging
import sys

from app.config import get_settings

logger = logging.getLogger(__name__)


def validate_config() -> list[str]:
    """Validate critical configuration. Returns list of errors (empty if OK)."""
    errors = []
    settings = get_settings()

    # JWT secret must be changed in production
    if settings.jwt_secret == "change-me":
        errors.append(
            "JWT_SECRET is set to the default 'change-me'. "
            "Generate a secure secret: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

    # Database URL should not be the default localhost in production
    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        logger.warning(
            "DATABASE_URL points to localhost. This is expected in development, "
            "but in production you should use a hosted database."
        )

    # CORS origins should not be only localhost in production
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if all("localhost" in o or "127.0.0.1" in o for o in origins):
        logger.warning(
            "CORS_ORIGINS only includes localhost origins. In production, add your frontend's URL "
            "(e.g., https://yourapp.onrender.com) or cross-origin requests will fail."
        )

    # Check for trailing slashes in CORS origins (common mistake)
    for origin in origins:
        if origin.endswith("/"):
            errors.append(
                f"CORS origin '{origin}' has a trailing slash. "
                "Browsers send Origin headers without trailing slashes, so this will never match. "
                f"Change to: {origin.rstrip('/')}"
            )

    # Validate grading model if API key is set
    if settings.anthropic_api_key:
        valid_models = [
            "claude-opus-5-5",
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
            "claude-fable-5-1",
            "claude-opus-5",
            "claude-sonnet-5",
        ]
        if settings.grading_model not in valid_models:
            logger.warning(
                f"GRADING_MODEL '{settings.grading_model}' may not be a valid Claude model. "
                f"Valid models: {', '.join(valid_models)}"
            )

    # WhatsApp config validation
    if settings.whatsapp_provider == "meta":
        if not settings.whatsapp_token:
            errors.append("WHATSAPP_PROVIDER is 'meta' but WHATSAPP_TOKEN is not set")
        if not settings.whatsapp_phone_number_id:
            errors.append("WHATSAPP_PROVIDER is 'meta' but WHATSAPP_PHONE_NUMBER_ID is not set")

    return errors


def run_startup_checks():
    """Run all startup checks and exit if critical errors are found."""
    logger.info("Running startup configuration checks...")
    errors = validate_config()

    if errors:
        logger.error("=== CONFIGURATION ERRORS ===")
        for err in errors:
            logger.error(f"  • {err}")
        logger.error("Fix the above errors and restart the server.")
        sys.exit(1)

    logger.info("Configuration checks passed ✓")
