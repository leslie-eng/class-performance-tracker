"""Step 6: startup checks run when the app starts; a rejected OpenRouter key stops the boot."""

import logging

import httpx
import pytest
import respx

from app.config import get_settings
from app.llm.client import OPENROUTER_BASE_URL
from app.startup_checks import ConfigError, check_openrouter, run_startup_checks

MODELS = {"data": [{"id": "openai/gpt-6-luna"}, {"id": "mistralai/mistral-small-2603"}, {"id": "google/gemini-3.8-flash"}]}


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_startup_check", True)
    return s


@pytest.fixture
def api():
    with respx.mock(base_url=OPENROUTER_BASE_URL, assert_all_called=False) as mock:
        mock.get("/models").mock(return_value=httpx.Response(200, json=MODELS))
        yield mock


def test_valid_key_passes(settings, api, caplog):
    api.get("/key").mock(return_value=httpx.Response(200, json={"data": {"label": "classtrack", "limit_remaining": 4.5}}))
    with caplog.at_level(logging.INFO):
        assert check_openrouter(settings) == []
    assert "OpenRouter key OK (classtrack)" in caplog.text
    assert api.calls[0].request.headers["authorization"] == "Bearer test-key"


def test_rejected_key_is_an_error_and_stops_startup(settings, api):
    api.get("/key").mock(return_value=httpx.Response(401, json={"error": {"code": 401, "message": "bad"}}))
    assert "was rejected" in check_openrouter(settings)[0]
    with pytest.raises(ConfigError, match="was rejected"):
        run_startup_checks()


def test_unreachable_openrouter_only_warns(settings, api, caplog):
    api.get("/key").mock(side_effect=httpx.ConnectTimeout("down"))
    assert check_openrouter(settings) == []
    assert "Couldn't reach OpenRouter" in caplog.text


def test_warnings_for_no_credit_and_missing_models(settings, api, caplog, monkeypatch):
    monkeypatch.setattr(settings, "llm_fallback_models", "mistral-small,vendor/retired-model")
    api.get("/key").mock(return_value=httpx.Response(200, json={"data": {"limit_remaining": 0, "is_free_tier": True}}))
    assert check_openrouter(settings) == []
    assert "credit limit is used up" in caplog.text and "never bought credits" in caplog.text
    assert "vendor/retired-model isn't in OpenRouter's model list" in caplog.text


def test_no_key_or_check_disabled_makes_no_requests(settings, api, monkeypatch):
    monkeypatch.setattr(settings, "llm_startup_check", False)
    assert check_openrouter(settings) == [] and not api.calls
    monkeypatch.setattr(settings, "llm_startup_check", True)
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    assert check_openrouter(settings) == [] and not api.calls


def test_bad_model_settings_stop_startup(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_default_model", "nope")
    with pytest.raises(ConfigError, match="Unknown model 'nope'"):
        run_startup_checks()
