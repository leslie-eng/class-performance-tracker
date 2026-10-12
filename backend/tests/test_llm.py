"""app.llm: model selection, privacy flags, retries, fallbacks and JSON validation (HTTP mocked with respx)."""

import json
import logging

import httpx
import pytest
import respx
from pydantic import BaseModel

from app.config import get_settings
from app.llm import LLMInvalidOutput, LLMNotConfigured, LLMRequestError, LLMService, LLMUnavailable
from app.llm.client import OPENROUTER_BASE_URL, make_client
from app.services import grading
from app.startup_checks import validate_llm_settings
from tests.fakes import FakeClaude

LUNA, MISTRAL, GEMINI = "openai/gpt-6-luna", "mistralai/mistral-small-2603", "google/gemini-3.8-flash"
GEMMA_FREE = "google/gemma-4-31b-it:free"


class Verdict(BaseModel):
    score: int
    reason: str


def completion(content: str, model: str = LUNA, cost: float | None = 0.0004) -> dict:
    usage = {"prompt_tokens": 120, "completion_tokens": 30}
    if cost is not None:
        usage["cost"] = cost
    return {"id": "gen-1", "model": model, "choices": [{"message": {"role": "assistant", "content": content},
                                                         "finish_reason": "stop"}], "usage": usage}


MESSAGES = [{"role": "system", "content": "Grade it."}, {"role": "user", "content": "Amina's article text"}]


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def service(sleeps):
    return LLMService(client=make_client(), sleep=sleeps.append)


@pytest.fixture
def api():
    with respx.mock(base_url=OPENROUTER_BASE_URL, assert_all_called=False) as mock:
        yield mock.post("/chat/completions")


def sent(route, i: int = -1) -> dict:
    return json.loads(route.calls[i].request.content)


# --- model selection -----------------------------------------------------------------

def test_task_models_and_fallback_chain(service, monkeypatch):
    assert service.chain("grading") == [LUNA, MISTRAL, GEMINI]
    assert service.chain("generation") == [GEMINI, MISTRAL]  # task override, duplicates dropped
    monkeypatch.setattr(get_settings(), "llm_task_models", "summary=mistral-small,generation=gemini-flash")
    assert service.chain("summary")[0] == MISTRAL
    with pytest.raises(ValueError):
        service.chain("poetry")


def test_member_data_never_routes_to_non_zdr_models(service, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_default_model", "gemma-free")
    assert GEMMA_FREE not in service.chain("grading")
    assert service.chain("grading", sensitive=False)[0] == GEMMA_FREE


# --- request and result --------------------------------------------------------------

def test_request_body_and_normalized_result(service, api):
    api.mock(return_value=httpx.Response(200, json=completion('{"score": 8, "reason": "clear"}')))
    result = service.generate("grading", MESSAGES, output=Verdict)

    body, request = sent(api), api.calls[-1].request
    assert body["models"] == [LUNA, MISTRAL, GEMINI]
    assert body["provider"] == {"require_parameters": True, "zdr": True, "data_collection": "deny"}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "Verdict"
    assert "JSON Schema" in body["messages"][0]["content"]
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["x-openrouter-title"]

    assert result.parsed == Verdict(score=8, reason="clear")
    assert (result.model_used, result.tokens_in, result.tokens_out, result.cost) == (LUNA, 120, 30, 0.0004)
    assert result.fallback_used is False and result.latency_ms >= 0


def test_fallback_model_is_reported(service, api):
    api.mock(return_value=httpx.Response(200, json=completion("plain text", model=MISTRAL)))
    result = service.generate("feedback", MESSAGES)
    assert result.text == "plain text" and result.model_used == MISTRAL and result.fallback_used is True
    assert "response_format" not in sent(api)


def test_dated_model_variant_is_not_a_fallback(service, api):
    api.mock(return_value=httpx.Response(200, json=completion("ok", model=LUNA + "-20260901")))
    assert service.generate("feedback", MESSAGES).fallback_used is False


def test_non_sensitive_calls_skip_privacy_routing(service, api):
    api.mock(return_value=httpx.Response(200, json=completion("hi", model=GEMMA_FREE, cost=None)))
    result = service.generate("feedback", MESSAGES, models=["gemma-free"], sensitive=False)
    assert sent(api)["provider"] == {"require_parameters": True} and result.cost is None


def test_explicit_non_zdr_model_is_refused_for_member_data(service, api):
    with pytest.raises(Exception, match="isn't approved for member data"):
        service.generate("feedback", MESSAGES, models=["gemma-free"])
    assert not api.called


def test_not_configured(service, api, monkeypatch):
    monkeypatch.setattr(get_settings(), "openrouter_api_key", None)
    with pytest.raises(LLMNotConfigured):
        service.generate("grading", MESSAGES)
    assert not api.called


# --- retries -------------------------------------------------------------------------

def test_retries_429_with_backoff_then_succeeds(service, api, sleeps):
    api.side_effect = [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json=completion("ok"))]
    assert service.generate("feedback", MESSAGES).text == "ok"
    assert api.call_count == 2 and sleeps == [3.0]


def test_gives_up_after_retries_on_5xx(service, api, sleeps):
    api.mock(return_value=httpx.Response(502, json={"error": {"code": 502, "message": "down"}}))
    with pytest.raises(LLMUnavailable, match="HTTP 502"):
        service.generate("feedback", MESSAGES)
    assert api.call_count == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_timeouts_are_retried(service, api):
    api.side_effect = [httpx.ReadTimeout("slow"), httpx.Response(200, json=completion("ok"))]
    assert service.generate("feedback", MESSAGES).text == "ok"


@pytest.mark.parametrize("status, message", [(401, "API key"), (402, "out of credit"), (400, "bad schema")])
def test_client_errors_are_not_retried(service, api, sleeps, status, message):
    api.mock(return_value=httpx.Response(status, json={"error": {"code": status, "message": "bad schema"}}))
    with pytest.raises(LLMRequestError, match=message) as e:
        service.generate("feedback", MESSAGES)
    assert e.value.status == status and api.call_count == 1 and sleeps == []


def test_error_inside_a_200_response_is_handled(service, api):
    api.side_effect = [
        httpx.Response(200, json={"error": {"code": 502, "message": "provider died mid-generation"}}),
        httpx.Response(200, json=completion("ok")),
    ]
    assert service.generate("feedback", MESSAGES).text == "ok" and api.call_count == 2


# --- structured output ---------------------------------------------------------------

def test_invalid_json_is_retried_once_with_the_problem(service, api):
    api.side_effect = [
        httpx.Response(200, json=completion('{"score": "high"}')),
        httpx.Response(200, json=completion('```json\n{"score": 6, "reason": "ok"}\n```', cost=0.0006)),
    ]
    result = service.generate("grading", MESSAGES, output=Verdict)
    assert result.parsed == Verdict(score=6, reason="ok")
    retry = sent(api)["messages"]
    assert retry[-2] == {"role": "assistant", "content": '{"score": "high"}'}
    assert "not valid for the schema" in retry[-1]["content"]
    assert result.tokens_in == 240 and result.cost == pytest.approx(0.001)


def test_invalid_json_twice_raises(service, api):
    api.mock(return_value=httpx.Response(200, json=completion("Sure! The score is 7.")))
    with pytest.raises(LLMInvalidOutput):
        service.generate("grading", MESSAGES, output=Verdict)
    assert api.call_count == 2


# --- hygiene -------------------------------------------------------------------------

def test_logs_hold_no_key_or_content(service, api, caplog):
    api.mock(return_value=httpx.Response(200, json=completion('{"score": 8, "reason": "clear"}')))
    with caplog.at_level(logging.DEBUG):
        service.generate("grading", MESSAGES, output=Verdict)
    assert "model=openai/gpt-6-luna" in caplog.text
    assert "test-key" not in caplog.text and "Amina" not in caplog.text and "clear" not in caplog.text


def test_startup_validation_of_llm_settings(monkeypatch):
    s = get_settings()
    assert validate_llm_settings(s) == []
    monkeypatch.setattr(s, "llm_task_models", "poetry=luna,grading=nope")
    monkeypatch.setattr(s, "llm_fallback_models", "gemma-free")
    errors = " | ".join(validate_llm_settings(s))
    assert "unknown tasks ['poetry']" in errors and "Unknown model 'nope'" in errors and "zero-retention" in errors


def test_features_use_their_tasks(client, admin, monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(grading, "_parse", fake)
    client.put("/weekly/brief", headers=admin, json={"source_notes": "Decorators and generators this week."})
    assert fake.tasks == ["summary"]
