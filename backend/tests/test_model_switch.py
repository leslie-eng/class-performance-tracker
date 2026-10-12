"""Step 4: admins switch the model per task live, test a model, and AI outputs record their model."""

import json

import httpx
import pytest
import respx

from app.llm import get_llm
from app.llm.client import OPENROUTER_BASE_URL
from tests.conftest import register

LUNA, MISTRAL, GEMMA_FREE = "openai/gpt-6-luna", "mistralai/mistral-small-2603", "google/gemma-4-31b-it:free"


def reply(content: str, model: str = LUNA, cost: float | None = 0.0002) -> dict:
    usage = {"prompt_tokens": 40, "completion_tokens": 20, **({"cost": cost} if cost is not None else {})}
    return {"model": model, "usage": usage, "choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


@pytest.fixture
def api():
    with respx.mock(base_url=OPENROUTER_BASE_URL, assert_all_called=False) as mock:
        yield mock.post("/chat/completions")


def tasks(body: dict) -> dict:
    return {t["task"]: (t["model_id"], t["source"]) for t in body["tasks"]}


def test_config_lists_models_and_where_each_task_model_comes_from(client, admin):
    body = client.get("/admin/llm", headers=admin).json()
    assert body["configured"] is True and body["require_zdr"] is True
    assert tasks(body)["grading"] == (LUNA, "default")
    assert tasks(body)["generation"] == ("google/gemini-3.8-flash", "env")
    free = next(m for m in body["models"] if m["key"] == "gemma-free")
    assert free["zdr"] is False and free["allowed_for_member_data"] is False


def test_members_cannot_see_or_change_models(client):
    h, _ = register(client, "m@example.com")
    assert client.get("/admin/llm", headers=h).status_code == 403
    assert client.put("/admin/llm/tasks/grading", headers=h, json={"model": "mistral-small"}).status_code == 403


def test_switching_a_task_model_applies_immediately_and_can_be_reset(client, admin):
    body = client.put("/admin/llm/tasks/summary", headers=admin, json={"model": "mistral-small"}).json()
    assert tasks(body)["summary"] == (MISTRAL, "admin")
    assert get_llm().chain("summary")[0] == MISTRAL
    assert get_llm().chain("grading")[0] == LUNA  # other tasks untouched

    body = client.put("/admin/llm/tasks/summary", headers=admin, json={"model": None}).json()
    assert tasks(body)["summary"] == (LUNA, "default")


@pytest.mark.parametrize("model, status, message", [
    ("gemma-free", 400, "zero-retention"),
    ("nope", 400, "Unknown model"),
])
def test_bad_choices_are_rejected(client, admin, model, status, message):
    r = client.put("/admin/llm/tasks/grading", headers=admin, json={"model": model})
    assert r.status_code == status and message in r.json()["detail"]
    assert client.put("/admin/llm/tasks/poetry", headers=admin, json={"model": "luna"}).status_code == 404


def test_test_button_reports_text_latency_and_cost(client, admin, api):
    api.mock(return_value=httpx.Response(200, json=reply("A list comprehension builds a list. [x*x for x in xs]")))
    body = client.post("/admin/llm/test", headers=admin, json={"model": "luna", "prompt": "Say hi"}).json()
    assert body["text"].startswith("A list comprehension") and body["model_used"] == LUNA
    assert body["cost"] == 0.0002 and body["cost_estimated"] is False and body["latency_ms"] >= 0
    sent = json.loads(api.calls[-1].request.content)
    assert sent["models"] == [LUNA] and sent["provider"]["zdr"] is True  # no fallbacks; private routing
    assert sent["messages"] == [{"role": "user", "content": "Say hi"}]


def test_free_models_only_get_the_sample_prompt(client, admin, api):
    r = client.post("/admin/llm/test", headers=admin, json={"model": "gemma-free", "prompt": "Grade Amina's essay"})
    assert r.status_code == 400 and not api.called

    api.mock(return_value=httpx.Response(200, json=reply("Sure.", model=GEMMA_FREE, cost=None)))
    body = client.post("/admin/llm/test", headers=admin, json={"model": "gemma-free"}).json()
    sent = json.loads(api.calls[-1].request.content)
    assert "zdr" not in sent["provider"] and "list comprehension" in sent["messages"][0]["content"]
    assert body["cost"] == 0 and body["cost_estimated"] is True


def test_test_button_shows_provider_errors(client, admin, api):
    api.mock(return_value=httpx.Response(402, json={"error": {"code": 402, "message": "no credit"}}))
    r = client.post("/admin/llm/test", headers=admin, json={"model": "luna"})
    assert r.status_code == 502 and "out of credit" in r.json()["detail"]


def test_ai_outputs_record_the_model_that_wrote_them(client, admin, api):
    summary = {"summary": "Decorators wrap functions. Generators are lazy.", "concepts": [{"title": "Decorators", "one_liner": "Wrappers"}]}
    api.mock(return_value=httpx.Response(200, json=reply(json.dumps(summary), model=MISTRAL)))
    client.put("/weekly/brief", headers=admin, json={"source_notes": "Decorators and generators."})
    brief = client.get("/weekly/brief", headers=admin).json()
    assert brief["summary"].startswith("Decorators") and brief["ai_model"] == MISTRAL


def test_meta_has_labels_for_the_model_badge(client):
    assert client.get("/meta").json()["ai_model_labels"][LUNA] == "GPT-6 Luna"
