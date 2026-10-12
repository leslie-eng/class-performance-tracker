import pytest
from pypdf import PdfWriter
import io

from app.config import get_settings
from app.main import app
from app.models import LearningMaterial, MaterialStatus, Quiz
from app.services import grading
from app.services.materials import CHUNK_CHARS, _context
from app.weeks import current_week_key
from tests.conftest import register
from tests.fakes import FakeClaude

TEXT = "Python decorators wrap a function to add behaviour. " * 5


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(grading, "_parse", fake)
    return fake


def text_pdf(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def add_text(client, admin, title="Decorators", text=TEXT, **extra):
    return client.post("/admin/materials", headers=admin, json={"title": title, "kind": "text", "text": text, **extra})


def upload(client, admin, name, data, **form):
    return client.post("/admin/materials/upload", headers=admin, files={"file": (name, data)}, data=form)


def test_members_get_403_on_every_admin_route(client, admin):
    member, _ = register(client, "m@example.com")
    checked = 0
    for path, ops in app.openapi()["paths"].items():
        if not path.startswith(("/admin/materials", "/admin/quizzes", "/admin/exercises")):
            continue
        for method in ops:
            url = path.replace("{material_id}", "1").replace("{quiz_id}", "1").replace("{exercise_id}", "1")
            r = client.request(method.upper(), url, headers=member, json={})
            assert r.status_code == 403, f"{method} {url} -> {r.status_code}"
            checked += 1
    assert checked >= 12


def test_paste_text_and_duplicate_detection(client, admin, claude):
    r = add_text(client, admin, module="python-basics", week_key=str(current_week_key()))
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["char_count"] == len(TEXT.strip()) and m["module"] == "python-basics"
    assert client.get(f"/admin/materials/{m['id']}", headers=admin).json()["digest"].startswith("A digest")
    assert "<material id=" in claude.calls[0][1]  # untrusted text is wrapped

    dup = add_text(client, admin, title="Same again", text="  " + TEXT.upper().replace(" ", "   ") + "\n")
    assert dup.status_code == 409 and f"material {m['id']}" in dup.json()["detail"]
    assert add_text(client, admin, text="too short").status_code == 422


def test_uploads(client, admin, claude):
    md = upload(client, admin, "notes.md", ("# Generators\n\n" + TEXT).encode(), module="python", week_key=str(current_week_key()))
    assert md.status_code == 201, md.text
    assert md.json()["kind"] == "file" and md.json()["original_filename"] == "notes.md"

    pdf = upload(client, admin, "slides.pdf", text_pdf("Context managers clean up resources with enter and exit methods."))
    assert pdf.status_code == 201, pdf.text
    assert "Context managers" in client.get(f"/admin/materials/{pdf.json()['id']}", headers=admin).json()["content_text"]

    scanned = upload(client, admin, "scan.pdf", blank_pdf())
    assert scanned.status_code == 422 and "no extractable text" in scanned.json()["detail"]
    assert upload(client, admin, "notes.docx", b"PK\x03\x04" + b"x" * 200).status_code == 415
    big = upload(client, admin, "big.txt", b"a" * (5 * 1024 * 1024 + 1))
    assert big.status_code == 413
    bad_spec = upload(client, admin, "x.md", TEXT.encode() + b"unique", specialization="astrology")
    assert bad_spec.status_code == 422


def test_url_material_uses_article_fetch(client, admin, claude, monkeypatch):
    monkeypatch.setattr("app.routers.materials.fetch_article", lambda url: ("Title", "Fetched page text. " * 10))
    r = client.post("/admin/materials", headers=admin, json={"title": "Docs", "kind": "url", "url": "https://docs.python.org/3/"})
    assert r.status_code == 201, r.text
    assert r.json()["source_url"] == "https://docs.python.org/3/"
    monkeypatch.setattr("app.routers.materials.fetch_article", lambda url: ("Title", "Updated page text. " * 10))
    again = client.post(f"/admin/materials/{r.json()['id']}/refetch", headers=admin)
    assert again.status_code == 200 and again.json()["content_text"].startswith("Updated")


def test_list_filters_and_archive(client, admin, claude):
    a = add_text(client, admin, "A", TEXT, module="m1").json()
    add_text(client, admin, "B", TEXT + " generators", module="m2")
    assert [m["title"] for m in client.get("/admin/materials?module=m1", headers=admin).json()] == ["A"]
    client.patch(f"/admin/materials/{a['id']}", headers=admin, json={"status": "archived"})
    assert [m["title"] for m in client.get("/admin/materials?status=active", headers=admin).json()] == ["B"]
    assert client.delete(f"/admin/materials/{a['id']}", headers=admin).status_code == 204  # unreferenced: deleted


def test_archived_materials_are_excluded_from_generation(client, admin, claude, db):
    week = str(current_week_key())
    keep = add_text(client, admin, "Keep", "KEEPME decorators and closures explained in depth here.", week_key=week).json()
    gone = add_text(client, admin, "Gone", "GONEZONE generators and iterators explained in depth here.", week_key=week).json()
    client.patch(f"/admin/materials/{gone['id']}", headers=admin, json={"status": "archived"})

    member, _ = register(client, "q@example.com")
    r = client.post("/quizzes/weekly/start?duration=10", headers=member)  # no notes: materials alone are the source
    assert r.status_code == 200, r.text
    prompt = next(c for n, c in claude.calls if n == "GenQuiz")
    assert "KEEPME" in prompt and "GONEZONE" not in prompt
    quiz = db.query(Quiz).one()
    assert quiz.source_material_ids == [keep["id"]]

    # a referenced material is archived, not deleted
    d = client.delete(f"/admin/materials/{keep['id']}", headers=admin)
    assert d.status_code == 200 and d.json()["archived"] is True
    assert db.get(LearningMaterial, keep["id"]).status == MaterialStatus.archived


def test_generate_review_and_publish(client, admin, claude, monkeypatch):
    monkeypatch.setattr(get_settings(), "require_quiz_review", True)
    m = add_text(client, admin, "Mod", TEXT, module="closures").json()
    r = client.post("/admin/quizzes/generate", headers=admin, json={"kind": "course", "module": "closures", "durations": [10]})
    assert r.status_code == 200, r.text
    quiz = r.json()[0]
    assert quiz["status"] == "draft" and quiz["sources"] == [{"id": m["id"], "title": "Mod"}]

    member, _ = register(client, "m@example.com")
    assert client.post("/quizzes/course/start?duration=10", headers=member).status_code == 404  # not reviewed yet
    slots = client.get("/weekly/current", headers=member).json()["quizzes"]
    assert next(s for s in slots if s["kind"] == "course" and s["duration_minutes"] == 10)["reason"] == "Waiting for admin review"

    full = client.get(f"/admin/quizzes/{quiz['id']}", headers=admin).json()
    assert "answer_key" in full["questions"][0]  # admins see keys
    edited = full["questions"][1:]  # delete the first question
    edited[0]["prompt"] = "Edited prompt"
    r = client.patch(f"/admin/quizzes/{quiz['id']}", headers=admin, json={"questions": edited})
    assert r.status_code == 200 and r.json()["question_count"] == 5
    bad = dict(edited[0], type="mcq", options=["a", "b"], answer_key=7)
    assert client.patch(f"/admin/quizzes/{quiz['id']}", headers=admin, json={"questions": [bad]}).status_code == 422

    assert client.post(f"/admin/quizzes/{quiz['id']}/publish", headers=admin).json()["status"] == "published"
    started = client.post("/quizzes/course/start?duration=10", headers=member)
    assert started.status_code == 200 and started.json()["questions"][0]["prompt"] == "Edited prompt"
    # editing while a member is mid-quiz is refused
    assert client.patch(f"/admin/quizzes/{quiz['id']}", headers=admin, json={"questions": edited}).status_code == 409


def test_context_sends_relevant_excerpts_not_whole_documents():
    filler = "\n\n".join(f"## Section {i}\n\n" + ("unrelated filler words about cooking. " * 80) for i in range(30))
    target = "## Decorators\n\nA decorator wraps a function; functools.wraps keeps the name. " * 3
    m = LearningMaterial(id=1, title="Big", module="python", content_text=filler + "\n\n" + target, digest="Digest text")
    text, ids = _context([m], "decorators functools wraps", budget=6_000)
    assert ids == [1] and len(text) <= 6_000 and len(m.content_text) > 100_000 // 2
    assert "functools.wraps" in text and "Digest: Digest text" in text
    assert text.index("[Decorators]") < text.index("[Section")  # most relevant chunk first
    assert all(len(body) <= CHUNK_CHARS * 2 for body in text.split("\n\n"))
