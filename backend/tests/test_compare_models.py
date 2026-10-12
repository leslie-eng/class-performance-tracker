"""Step 7: the model comparison script (HTTP mocked; no database writes)."""

import json
import re

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.config import get_settings
from app.llm import LLMService
from app.llm.client import OPENROUTER_BASE_URL, make_client
from app.models import LLMCall
from scripts import compare_models

GRADE = {"clarity": 3, "technical_accuracy": 3, "depth": 1, "originality": 2, "feedback": "Clear.",
         "strengths": ["examples"], "improvements": ["more depth"]}


def answer(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    model = body["models"][0]
    if model.startswith("nvidia/"):
        return httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}})
    content = json.dumps(GRADE) if "response_format" in body else f"Reply from {model}"
    cost = None if model.endswith(":free") else 0.0004
    usage = {"prompt_tokens": 50, "completion_tokens": 25, **({"cost": cost} if cost is not None else {})}
    return httpx.Response(200, json={"model": model, "usage": usage,
                                     "choices": [{"message": {"content": content}, "finish_reason": "stop"}]})


@pytest.fixture
def api():
    with respx.mock(base_url=OPENROUTER_BASE_URL) as mock:
        yield mock.post("/chat/completions").mock(side_effect=answer)


@pytest.fixture
def service():
    return LLMService(client=make_client(), sleep=lambda s: None, recorder=lambda r: None)


def test_runs_every_model_and_prints_a_table(api, service, capsys, db):
    assert compare_models.main([], service=service) == 0
    out = capsys.readouterr().out
    for label in ("GPT-6 Luna", "Mistral Small", "Gemini 3.8 Flash", "Gemma 4 31B (free)"):
        assert label in out
    assert "Reply from openai/gpt-6-luna" in out and "0.00040" in out
    assert re.search(r"Nemotron 3 Super \(free\) +no .*LLMUnavailable", out)  # failures are rows, not crashes
    sent = {json.loads(c.request.content)["models"][0]: json.loads(c.request.content)["provider"] for c in api.calls}
    assert sent["openai/gpt-6-luna"].get("zdr") is True and "zdr" not in sent["google/gemma-4-31b-it:free"]
    assert db.scalar(select(func.count()).select_from(LLMCall)) == 0


def test_structured_mode_checks_the_schema(api, service, capsys):
    assert compare_models.main(["--structured", "--models", "luna", "--full"], service=service) == 0
    out = capsys.readouterr().out
    assert '"clarity": 3' in out and "sample article graded as JSON" in out


def test_custom_prompts_skip_free_models(api, service, capsys):
    compare_models.main(["--models", "luna,gemma-free", "--prompt", "Explain recursion"], service=service)
    out = capsys.readouterr().out
    assert "Skipped (no zero-retention provider" in out and "google/gemma-4-31b-it:free" in out
    assert [json.loads(c.request.content)["models"][0] for c in api.calls] == ["openai/gpt-6-luna"]
    assert json.loads(api.calls[0].request.content)["messages"][0]["content"] == "Explain recursion"


def test_needs_a_key_and_known_models(service, capsys, monkeypatch):
    assert compare_models.main(["--models", "nope"], service=service) == 2
    monkeypatch.setattr(get_settings(), "openrouter_api_key", None)
    assert compare_models.main([], service=service) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
