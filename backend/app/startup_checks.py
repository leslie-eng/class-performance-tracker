"""Startup validation checks to catch common configuration errors early.

run_startup_checks() runs when the app starts (main.py lifespan). Errors stop the boot,
so a bad deploy fails on Render with the reason in the logs instead of at the first
request. Warnings are only logged.
"""

import logging

import httpx

from app.config import get_settings
from app.llm import registry
from app.llm.client import OPENROUTER_BASE_URL

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

    # Trailing slashes in CORS origins: main.py strips them, so this is only a tidy-up hint.
    for origin in origins:
        if origin.endswith("/"):
            logger.warning(f"CORS origin '{origin}' has a trailing slash; it's being used as {origin.rstrip('/')}")

    # AI model settings (app/llm). Checked even without a key, so a bad value can't sit unnoticed.
    errors.extend(validate_llm_settings(settings))
    if not settings.openrouter_api_key:
        logger.warning("OPENROUTER_API_KEY is not set: AI grading, summaries, quizzes and feedback are off.")

    # WhatsApp config validation
    if settings.whatsapp_provider == "meta":
        if not settings.whatsapp_token:
            errors.append("WHATSAPP_PROVIDER is 'meta' but WHATSAPP_TOKEN is not set")
        if not settings.whatsapp_phone_number_id:
            errors.append("WHATSAPP_PROVIDER is 'meta' but WHATSAPP_PHONE_NUMBER_ID is not set")

    return errors


def validate_llm_settings(settings) -> list[str]:
    errors = []
    unknown_tasks = set(settings.llm_task_model_map) - set(registry.TASKS)
    if unknown_tasks:
        errors.append(f"LLM_TASK_MODELS has unknown tasks {sorted(unknown_tasks)}; use {', '.join(registry.TASKS)}")
    names = [settings.llm_default_model, *settings.llm_task_model_map.values(), *settings.llm_fallback_list]
    for name in names:
        try:
            model_id = registry.resolve(name)
        except registry.UnknownModel as e:
            errors.append(str(e))
            continue
        if settings.llm_require_zdr and not registry.is_zdr(model_id):
            errors.append(
                f"Model {name!r} has no zero-retention endpoint, so it can't be used for member data. "
                "Pick a model marked zdr in app/llm/registry.py (free models are for testing only)."
            )
    return errors


def check_openrouter(settings, client: httpx.Client | None = None) -> list[str]:
    """With a key set: a rejected key is an error. OpenRouter being unreachable is only a
    warning, so an OpenRouter outage can't stop the app from booting. Neither request runs
    a model, so neither costs credits."""
    if not settings.openrouter_api_key or not settings.llm_startup_check:
        return []
    errors: list[str] = []
    http = client or httpx.Client(base_url=OPENROUTER_BASE_URL, timeout=8)
    try:
        resp = http.get("/key", headers={"Authorization": f"Bearer {settings.openrouter_api_key}"})
        if resp.status_code in (401, 403):
            errors.append("OPENROUTER_API_KEY was rejected by OpenRouter; create a new key at openrouter.ai/settings/keys")
        elif resp.status_code != 200:
            logger.warning("Couldn't verify OPENROUTER_API_KEY (HTTP %s); continuing", resp.status_code)
        else:
            data = resp.json().get("data") or {}
            remaining = data.get("limit_remaining")
            logger.info("OpenRouter key OK (%s)", data.get("label") or "unlabelled")
            if remaining is not None and remaining <= 0:
                logger.warning("The OpenRouter key's credit limit is used up: paid models will fail with 402")
            if data.get("is_free_tier"):
                logger.warning("This OpenRouter account has never bought credits: paid models will fail with 402")

        listed = {m["id"] for m in http.get("/models").json().get("data", [])}
        configured = {registry.resolve(n) for n in
                      [settings.llm_default_model, *settings.llm_task_model_map.values(), *settings.llm_fallback_list]}
        for model_id in sorted(configured - listed):
            logger.warning("Model %s isn't in OpenRouter's model list any more; requests to it will fail", model_id)
    except (httpx.HTTPError, ValueError, registry.UnknownModel) as e:
        logger.warning("Couldn't reach OpenRouter to check the key (%s); continuing", type(e).__name__)
    finally:
        if client is None:
            http.close()
    return errors


class ConfigError(RuntimeError):
    pass


def run_startup_checks():
    """Run all startup checks; raise ConfigError (which stops the boot) on any error."""
    logger.info("Running startup configuration checks...")
    settings = get_settings()
    errors = validate_config()
    if not errors:  # only worth a network call when the rest is valid
        errors += check_openrouter(settings)

    if errors:
        logger.error("=== CONFIGURATION ERRORS ===")
        for err in errors:
            logger.error(f"  • {err}")
        logger.error("Fix the above errors and restart the server.")
        raise ConfigError("; ".join(errors))

    logger.info("Configuration checks passed ✓")
