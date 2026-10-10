import json
import re

import pytest

from app.services import grading
from app.services.code_runner import RemoteRunner, RunResult, TestOutcome
from tests.conftest import register
from tests.fakes import FakeClaude

TESTS = [
    {"name": "small", "args": [1, 2], "expected": 3, "hidden": False},
    {"name": "zero", "args": [0, 0], "expected": 0, "hidden": False},
    {"name": "SECRET_EDGE_CASE", "args": [-987654, 1], "expected": -987653, "hidden": True},
]


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(grading, "_parse", fake)
    return fake


@pytest.fixture
def exercise(client, admin):
    r = client.post("/admin/exercises", headers=admin, json={
        "title": "Add", "description_md": "Write add(a, b).", "starter_code": "def add(a, b):\n    pass\n",
        "entrypoint": "add", "tests": TESTS, "points": 10, "module": "basics",
        "reference_solution": "def add(a, b):\n    return a + b\n",
    })
    assert r.status_code == 201, r.text
    ex = r.json()
    assert ex["status"] == "draft" and ex["tests_verified"] is False
    assert client.post(f"/admin/exercises/{ex['id']}/publish", headers=admin).status_code == 200
    return ex


class FakeRunner:
    verifies = True

    def __init__(self, passed_all=True):
        self.passed_all, self.calls = passed_all, []

    def run(self, language, code, entrypoint, tests, time_limit):
        self.calls.append(code)
        return RunResult(outcomes=[TestOutcome(name=t["name"], passed=self.passed_all, hidden=t["hidden"], actual="3") for t in tests])


def submit(client, h, ex, passed=2, total=2, code="def add(a, b):\n    return a + b\n"):
    return client.post(f"/coding/exercises/{ex['id']}/submit", headers=h,
                       json={"code": code, "browser_results": {"passed": passed, "total": total}})


def test_hidden_tests_never_reach_members(client, exercise, claude):
    h, _ = register(client, "m@example.com")
    responses = [
        client.get("/coding/exercises", headers=h),
        client.get(f"/coding/exercises/{exercise['id']}", headers=h),
        submit(client, h, exercise),
    ]
    responses.append(client.get(f"/coding/attempts/{responses[-1].json()['id']}", headers=h))
    for r in responses:
        assert r.status_code in (200, 201), r.text
        assert "SECRET_EDGE_CASE" not in r.text and "987654" not in r.text and "reference_solution" not in r.text
    detail = responses[1].json()
    assert [t["name"] for t in detail["visible_tests"]] == ["small", "zero"] and detail["hidden_test_count"] == 1
    # nor do they reach the AI reviewer
    review_prompt = next(c for n, c in claude.calls if n == "CodeReview")
    assert "987654" not in review_prompt and "SECRET" not in review_prompt


def test_draft_autosave_and_restore(client, exercise):
    h, _ = register(client, "d@example.com")
    assert client.get(f"/coding/exercises/{exercise['id']}", headers=h).json()["draft"] is None
    assert client.put(f"/coding/exercises/{exercise['id']}/draft", headers=h, json={"code": "def add(a, b): return 1"}).status_code == 204
    assert client.put(f"/coding/exercises/{exercise['id']}/draft", headers=h, json={"code": "def add(a, b): return 2"}).status_code == 204
    assert client.get(f"/coding/exercises/{exercise['id']}", headers=h).json()["draft"] == "def add(a, b): return 2"
    other, _ = register(client, "o@example.com")
    assert client.get(f"/coding/exercises/{exercise['id']}", headers=other).json()["draft"] is None


def test_oversized_code_is_rejected(client, exercise):
    h, _ = register(client, "big@example.com")
    huge = "x" * 20_001
    assert client.put(f"/coding/exercises/{exercise['id']}/draft", headers=h, json={"code": huge}).status_code == 422
    assert submit(client, h, exercise, code=huge).status_code == 422


def test_unverified_points_are_reduced_and_awarded_once(client, exercise, claude):
    h, _ = register(client, "p@example.com")
    first = submit(client, h, exercise).json()
    assert (first["verified"], first["runner"], first["points_awarded"]) == (False, "browser", 5)
    assert submit(client, h, exercise).json()["points_awarded"] == 0  # already earned
    assert submit(client, h, exercise, passed=1).json()["points_awarded"] == 0
    # A misreported total doesn't count as a pass.
    h2, _ = register(client, "liar@example.com")
    assert submit(client, h2, exercise, passed=3, total=3).json()["passed_count"] == 0
    assert client.get(f"/coding/attempts/{first['id']}", headers=h).json()["grading_status"] == "done"


def test_verified_runs_earn_full_points_and_top_up(client, exercise, claude, monkeypatch):
    h, _ = register(client, "u@example.com")
    assert submit(client, h, exercise).json()["points_awarded"] == 5  # browser first

    runner = FakeRunner()
    monkeypatch.setattr("app.routers.coding.get_runner", lambda: runner)
    r = submit(client, h, exercise, passed=0, total=0).json()  # browser numbers are ignored
    assert (r["verified"], r["runner"], r["passed_count"], r["total_count"]) == (True, "remote", 3, 3)
    assert r["points_awarded"] == 5  # topped up to the full 10
    assert submit(client, h, exercise).json()["points_awarded"] == 0
    assert all("SECRET" not in json.dumps(x) for x in r["results"])  # hidden tests only as a count
    assert r["results"][-1]["name"] == "1 hidden test"

    fresh, _ = register(client, "v@example.com")
    assert submit(client, fresh, exercise).json()["points_awarded"] == 10
    lst = client.get("/coding/exercises", headers=fresh).json()[0]
    assert (lst["solved"], lst["verified"], lst["points_earned"]) == (True, True, 10)


def test_unpublished_exercises_are_invisible(client, admin, exercise):
    client.patch(f"/admin/exercises/{exercise['id']}", headers=admin, json={"status": "draft"})
    h, _ = register(client, "x@example.com")
    assert client.get("/coding/exercises", headers=h).json() == []
    assert client.get(f"/coding/exercises/{exercise['id']}", headers=h).status_code == 404
    assert submit(client, h, exercise).status_code == 404
    assert client.get(f"/admin/exercises/{exercise['id']}", headers=admin).json()["reference_solution"]


def test_submissions_are_rate_limited(client, exercise, claude):
    h, _ = register(client, "r@example.com")
    for _ in range(10):
        assert submit(client, h, exercise).status_code == 201
    r = submit(client, h, exercise)
    assert r.status_code == 429


def test_generated_exercises_are_validated_drafts(client, admin, claude):
    m = client.post("/admin/materials", headers=admin, json={
        "title": "Functions", "kind": "text", "text": "Functions take arguments and return values. " * 5}).json()
    r = client.post("/admin/exercises/generate", headers=admin, json={"material_ids": [m["id"]], "count": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["created"]) == 1 and "Broken" in body["dropped"][0]
    ex = body["created"][0]
    assert (ex["status"], ex["tests_verified"], ex["material_id"]) == ("draft", False, m["id"])
    assert sum(t["hidden"] for t in ex["tests"]) == 2
    # the admin UI's browser run of the reference solution marks the tests verified
    v = client.post(f"/admin/exercises/{ex['id']}/verify", headers=admin, json={"passed": 5, "total": 5})
    assert v.json()["tests_verified"] is True
    h, _ = register(client, "g@example.com")
    assert client.get("/coding/exercises", headers=h).json() == []  # still a draft


def test_remote_runner_harness_and_parsing(monkeypatch):
    """The remote runner only sends code over HTTP; parse its reply. Nothing runs locally."""
    sent = {}

    class Resp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    def fake_post(url, params, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers)
        nonce = re.search(r"'(__CT_[0-9a-f]+__)'", json["source_code"]).group(1)
        rows = [{"name": "small", "passed": True, "actual": "3"}, {"name": "SECRET_EDGE_CASE", "passed": False, "error": "boom"}]
        return Resp({"stdout": "member print\n" + nonce + __import__("json").dumps(rows) + "\n", "status": {"description": "Accepted"}})

    monkeypatch.setattr("app.services.code_runner.httpx.post", fake_post)
    result = RemoteRunner("https://judge0.example.com/", "k").run("python", "def add(a, b):\n    return a + b", "add", TESTS, 5)
    assert sent["url"] == "https://judge0.example.com/submissions" and sent["headers"] == {"X-Auth-Token": "k"}
    assert "def add(a, b)" in sent["body"]["source_code"] and sent["body"]["language_id"] == 71
    assert [(o.name, o.passed) for o in result.outcomes] == [("small", True), ("zero", False), ("SECRET_EDGE_CASE", False)]
    assert result.output.startswith("member print") and "__CT_" not in result.output


def test_no_member_code_execution_primitives_in_server_code():
    """Guard rail: the API host must never execute member code."""
    import pathlib

    banned = re.compile(r"(?<![\w.])(exec|eval|compile)\(|\bsubprocess\b|\bos\.system\b|\bos\.popen\b")
    for path in pathlib.Path("app").rglob("*.py"):
        match = banned.search(path.read_text(encoding="utf-8"))
        assert match is None, f"{match.group(0)} in {path}"
