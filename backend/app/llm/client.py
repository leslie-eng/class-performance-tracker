"""HTTP client for OpenRouter's OpenAI-compatible API.

Plain httpx rather than the openai SDK: OpenRouter's own fields (`models`, `provider`)
are ordinary JSON here, and tests can mock it with respx. The API key is added per
request (never stored on the client or logged).
"""

import httpx

from app.config import get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def make_client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=OPENROUTER_BASE_URL,
        timeout=httpx.Timeout(s.llm_timeout_seconds, connect=10),
        headers={
            # Optional attribution, used only for OpenRouter's public app rankings.
            "HTTP-Referer": s.frontend_url,
            "X-OpenRouter-Title": s.app_name,
        },
    )
