"""Test doubles for Claude (grading._parse) and WhatsApp, so tests make no network calls."""

import re

from app.services.coding import GenExercise, GenExercises, GenTest
from app.services.grading import CodeReview
from app.services.materials import Digest
from app.services.quizzes import GenQuestion, GenQuiz, ShortGrade, ShortGrades, difficulty_band, mcq_target
from app.services.weekly import BriefSummary, Concept
from app.services.whatsapp import WhatsAppError


def valid_questions(n: int, tag: str = "") -> list[GenQuestion]:
    short_needed = n - mcq_target(n)
    out = []
    for i in range(n):
        lo, _ = difficulty_band(i, n)
        is_short = short_needed > 0 and i % 3 == 2
        short_needed -= is_short
        if is_short:
            out.append(GenQuestion(type="short", difficulty=lo, prompt=f"{tag}Explain idea {i}", answer_key=f"idea {i}",
                                   explanation="Because."))
        else:
            out.append(GenQuestion(type="mcq", difficulty=lo, prompt=f"{tag}Pick option for {i}",
                                   options=["alpha", "beta", "gamma", "delta"], correct_option=1, answer_key="beta",
                                   explanation="Beta is right."))
    return out


class FakeClaude:
    """Stands in for grading._parse. `quiz_responses` can queue custom GenQuiz outputs."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []  # (output model name, user content)
        self.quiz_responses: list[GenQuiz] = []
        self.short_score = 1.0

    def __call__(self, system, content, output_format, model=None):
        self.calls.append((output_format.__name__, content))
        if output_format is BriefSummary:
            return BriefSummary(
                summary="Decorators wrap functions to add behaviour. Generators yield values lazily. Also: context managers.",
                concepts=[Concept(title="Decorators", one_liner="Functions that wrap functions")],
            )
        if output_format is CodeReview:
            return CodeReview(feedback="Looks correct. Consider clearer names.")
        if output_format is GenExercises:
            good = GenExercise(
                title="Add two numbers", description_md="Write add(a, b).", starter_code="def add(a, b):\n    pass\n",
                entrypoint="add", reference_solution="def add(a, b):\n    return a + b\n", difficulty=1,
                tests=[GenTest(name=f"t{i}", args_json=f"[{i}, 1]", expected_json=str(i + 1), hidden=i >= 3) for i in range(5)],
            )
            bad = good.model_copy(update={"title": "Broken", "entrypoint": "not valid"})
            return GenExercises(exercises=[good, bad])
        if output_format is Digest:
            return Digest(summary="A digest of the material.", key_terms=["decorators", "generators"])
        if output_format is GenQuiz:
            if self.quiz_responses:
                return self.quiz_responses.pop(0)
            n = int(re.search(r"Write exactly (\d+) questions", system).group(1))
            return GenQuiz(questions=valid_questions(n))
        if output_format is ShortGrades:
            ids = re.findall(r"<question id='(q\d+)'>", content)
            return ShortGrades(grades=[ShortGrade(id=i, score=self.short_score, feedback="Good.") for i in ids])
        raise AssertionError(f"unexpected output format {output_format}")

    def count(self, name: str) -> int:
        return sum(1 for n, _ in self.calls if n == name)


class FakeSender:
    def __init__(self, fail_for: set[str] | None = None, crash_for: set[str] | None = None):
        self.sent: list[tuple[str, str, str | None]] = []
        self.fail_for, self.crash_for = fail_for or set(), crash_for or set()

    def send(self, phone, message, template=None):
        if phone in self.fail_for:
            raise WhatsAppError("HTTP 400: template rejected")
        if phone in self.crash_for:
            raise RuntimeError("boom")
        self.sent.append((phone, message, template))
