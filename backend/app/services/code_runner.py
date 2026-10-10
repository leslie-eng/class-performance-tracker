"""Where member code runs. Never here: the API host only stores code and, when a
remote sandbox is configured, forwards it there.

- NoopRunner (CODE_RUNNER=none, the default): nothing runs server-side. Members run
  visible tests in their own browser (Pyodide / a JS worker) and the result is
  self-reported, so attempts are unverified and earn reduced points.
- RemoteRunner (CODE_RUNNER=remote): a Judge0-compatible sandbox on its own isolated
  host runs every test, hidden ones included, so attempts are verified.

The harness sent to the sandbox compares results there and prints them after a
per-run nonce. That stops accidental or casual self-reporting; a determined member
could still game a harness that shares a process with their code, which is fine for
a study group but worth knowing.
"""

import json
import logging
import secrets
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

OUTPUT_LIMIT = 64 * 1024
# Judge0 CE language ids; change these if your instance numbers them differently.
JUDGE0_LANGUAGE_IDS = {"python": 71, "javascript": 63}


class RunnerError(Exception):
    pass


@dataclass
class TestOutcome:
    __test__ = False  # not a pytest test class

    name: str
    passed: bool
    hidden: bool
    actual: str | None = None
    error: str | None = None


@dataclass
class RunResult:
    outcomes: list[TestOutcome] = field(default_factory=list)
    output: str = ""
    error: str | None = None  # compile/runtime error before tests ran, or a timeout

    @property
    def passed(self) -> int:
        return sum(o.passed for o in self.outcomes)


class CodeRunner(Protocol):
    verifies: bool

    def run(self, language: str, code: str, entrypoint: str, tests: list[dict], time_limit: int) -> RunResult: ...


class NoopRunner:
    """No server-side execution at all."""

    verifies = False

    def run(self, language: str, code: str, entrypoint: str, tests: list[dict], time_limit: int) -> RunResult:
        raise RunnerError("No code runner is configured on the server; run tests in the browser")


PY_HARNESS = """{code}

import json as __ct_json
def __ct_main():
    out = []
    for t in __ct_json.loads({tests!r}):
        try:
            got = {entrypoint}(*t["args"])
            norm = __ct_json.loads(__ct_json.dumps(got, default=repr))
            out.append({{"name": t["name"], "passed": norm == t["expected"], "actual": __ct_json.dumps(got, default=repr)[:300]}})
        except Exception as e:
            out.append({{"name": t["name"], "passed": False, "error": (type(e).__name__ + ": " + str(e))[:300]}})
    print({nonce!r} + __ct_json.dumps(out))
__ct_main()
"""

JS_HARNESS = """{code}

;(() => {{
  const tests = JSON.parse({tests});
  const out = [];
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  for (const t of tests) {{
    try {{
      const got = {entrypoint}(...t.args);
      out.push({{ name: t.name, passed: same(JSON.parse(JSON.stringify(got ?? null)), t.expected), actual: String(JSON.stringify(got)).slice(0, 300) }});
    }} catch (e) {{
      out.push({{ name: t.name, passed: false, error: String(e).slice(0, 300) }});
    }}
  }}
  console.log({nonce} + JSON.stringify(out));
}})();
"""


def build_harness(language: str, code: str, entrypoint: str, tests: list[dict], nonce: str) -> str:
    payload = json.dumps([{"name": t["name"], "args": t["args"], "expected": t["expected"]} for t in tests])
    if language == "python":
        return PY_HARNESS.format(code=code, tests=payload, entrypoint=entrypoint, nonce=nonce)
    return JS_HARNESS.format(code=code, tests=json.dumps(payload), entrypoint=entrypoint, nonce=json.dumps(nonce))


class RemoteRunner:
    """Judge0-compatible sandbox (POST /submissions?wait=true). Deploy it on its own
    isolated host; it is not part of the free Render setup."""

    verifies = True

    def __init__(self, url: str, key: str | None = None):
        self.url = url.rstrip("/")
        self.key = key

    def run(self, language: str, code: str, entrypoint: str, tests: list[dict], time_limit: int) -> RunResult:
        if language not in JUDGE0_LANGUAGE_IDS:
            raise RunnerError(f"Unsupported language: {language}")
        nonce = f"__CT_{secrets.token_hex(8)}__"
        body = {
            "source_code": build_harness(language, code, entrypoint, tests, nonce),
            "language_id": JUDGE0_LANGUAGE_IDS[language],
            "cpu_time_limit": time_limit,
            "wall_time_limit": time_limit * 2,
            "memory_limit": 256_000,
        }
        headers = {"X-Auth-Token": self.key} if self.key else {}
        try:
            resp = httpx.post(
                f"{self.url}/submissions",
                params={"base64_encoded": "false", "wait": "true"},
                json=body,
                headers=headers,
                timeout=time_limit * 2 + 20,
            )
        except httpx.HTTPError as e:
            raise RunnerError(f"Code runner unreachable ({type(e).__name__})") from e
        if resp.status_code >= 400:
            raise RunnerError(f"Code runner returned HTTP {resp.status_code}")
        data = resp.json()
        stdout = (data.get("stdout") or "")[:OUTPUT_LIMIT]
        stderr = (data.get("stderr") or data.get("compile_output") or "")[:OUTPUT_LIMIT]
        status = (data.get("status") or {}).get("description", "")
        hidden = {t["name"]: bool(t.get("hidden")) for t in tests}
        result = RunResult(output=(stdout.split(nonce)[0] + stderr)[:OUTPUT_LIMIT])
        line = next((ln for ln in stdout.splitlines() if ln.startswith(nonce)), None)
        if line is None:
            result.error = status if status and status != "Accepted" else "Your code didn't finish the tests"
            result.outcomes = [TestOutcome(name=n, passed=False, hidden=h, error=result.error) for n, h in hidden.items()]
            return result
        try:
            rows = json.loads(line[len(nonce):])
        except json.JSONDecodeError as e:
            raise RunnerError("Couldn't read the test results") from e
        by_name = {r.get("name"): r for r in rows if isinstance(r, dict)}
        for name, is_hidden in hidden.items():
            r = by_name.get(name, {})
            result.outcomes.append(
                TestOutcome(name=name, passed=r.get("passed") is True, hidden=is_hidden,
                            actual=r.get("actual"), error=r.get("error") if r else "Test didn't run")
            )
        return result


def get_runner() -> CodeRunner:
    s = get_settings()
    if s.code_runner == "remote" and s.code_runner_url:
        return RemoteRunner(s.code_runner_url, s.code_runner_key)
    return NoopRunner()
