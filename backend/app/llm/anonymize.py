"""Replace members' names, emails and phone numbers in prompts with placeholders, and put
names back in the model's output.

Prompts never include names or ids on purpose; this catches them inside text members
wrote (an article byline, "- Amina" at the end of class notes). Free-text matching is
best effort: misspellings and nicknames get through. The hard guarantee is that member
data only goes to zero-retention providers (app/llm/service.py).

- Full names match case-insensitively; single first or last names only when capitalised,
  at least 3 letters, not a common English word, and unique to one member.
- Each member gets "Student A", "Student B", ... for this one call; restore() maps them back.
- Any email becomes "[email]"; a member's phone number (any common Kenyan format) becomes
  "[phone]". Neither is restored.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PLACEHOLDER = re.compile(r"\bStudent [A-Z]{1,2}\b")
# First/last names that are also everyday words; matching them would mangle normal text.
COMMON_WORDS = frozenset(
    "will may mark grace hope joy faith rose june april august summer winter art bill frank "
    "victor patience mercy charity gift precious blessing sunday lucky king queen love peace "
    "brown white green black young long hill wood".split()
)


@dataclass(frozen=True)
class Person:
    name: str
    email: str | None = None
    phone: str | None = None


def _label(i: int) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return letters[i] if i < 26 else letters[i // 26 - 1] + letters[i % 26]


def _phone_pattern(phone: str) -> re.Pattern | None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 9:
        return None
    local = digits[-9:]  # 7XXXXXXXX: matches +254 7.., 254 7.., 07..
    body = r"[\s-]?".join(local)
    return re.compile(rf"(?<!\d)(?:\+?254[\s-]?|0)?{body}(?!\d)")


class Anonymizer:
    def __init__(self, people: Iterable[Person]):
        people = [p for p in people if p.name and p.name.strip()]
        self._restore: dict[str, str] = {}
        full: dict[str, str] = {}
        parts: dict[str, str] = {}
        part_counts = Counter(
            part for p in people for part in {w for w in re.split(r"\s+", p.name.strip()) if w}
        )
        self._phones: list[re.Pattern] = []
        for i, p in enumerate(people):
            placeholder = f"Student {_label(i)}"
            name = " ".join(p.name.split())
            self._restore[placeholder] = name
            if " " in name:
                full[name.lower()] = placeholder
            for part in name.split(" "):
                if len(part) >= 3 and part.lower() not in COMMON_WORDS and part[0].isupper():
                    # A name shared by two members can't be mapped back to one of them.
                    parts[part] = placeholder if part_counts[part] == 1 else "a student"
            if p.phone and (pattern := _phone_pattern(p.phone)):
                self._phones.append(pattern)
        self._full = full
        self._parts = parts
        self._full_re = self._alternation(full, re.IGNORECASE)
        self._parts_re = self._alternation(parts, 0)

    @staticmethod
    def _alternation(words: dict[str, str], flags: int) -> re.Pattern | None:
        if not words:
            return None
        ordered = sorted(words, key=len, reverse=True)
        return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in ordered) + r")\b", flags)

    def redact(self, text: str) -> str:
        text = EMAIL.sub("[email]", text)
        for pattern in self._phones:
            text = pattern.sub("[phone]", text)
        if self._full_re:
            text = self._full_re.sub(lambda m: self._full[m.group(0).lower()], text)
        if self._parts_re:
            text = self._parts_re.sub(lambda m: self._parts[m.group(0)], text)
        return text

    def restore(self, text: str) -> str:
        return PLACEHOLDER.sub(lambda m: self._restore.get(m.group(0), m.group(0)), text)

    def restore_model(self, obj: BaseModel) -> BaseModel:
        def walk(value):
            if isinstance(value, str):
                return self.restore(value)
            if isinstance(value, list):
                return [walk(v) for v in value]
            if isinstance(value, dict):
                return {k: walk(v) for k, v in value.items()}
            return value

        return type(obj).model_validate(walk(obj.model_dump()))


def for_members() -> Anonymizer:
    """An anonymizer for everyone registered (the table is small; read fresh each call)."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        rows = db.execute(select(User.name, User.email, User.phone_number).order_by(User.id)).all()
    return Anonymizer(Person(name, email, phone) for name, email, phone in rows)
