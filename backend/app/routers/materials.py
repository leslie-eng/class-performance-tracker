"""Learning materials (admin only). Members never see materials or drafts."""

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from app.deps import DB, AdminUser
from app.models import LearningMaterial, MaterialKind, MaterialStatus, Quiz, User, as_utc
from app.schemas_materials import MaterialIn, MaterialOut, MaterialSummary, MaterialUpdate, _known_specialization
from app.services import materials as svc
from app.services.article_fetch import ArticleFetchError, fetch_article

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/materials", tags=["admin: materials"])


def summary(m: LearningMaterial) -> MaterialSummary:
    return MaterialSummary(
        id=m.id, title=m.title, kind=m.kind.value, module=m.module, week_key=m.week_key, specialization=m.specialization,
        status=m.status.value, source_url=m.source_url, original_filename=m.original_filename, char_count=m.char_count,
        digest_ready=m.digest is not None, digest_error=m.digest_error, created_at=as_utc(m.created_at),
    )


def quiz_ids_using(db: DB, material_id: int) -> list[int]:
    # source_material_ids is a JSON list; the quiz table is small, so filter in Python.
    return [q.id for q in db.scalars(select(Quiz)).all() if material_id in (q.source_material_ids or [])]


def detail(db: DB, m: LearningMaterial) -> MaterialOut:
    return MaterialOut(**summary(m).model_dump(), content_text=m.content_text, digest=m.digest, quiz_ids=quiz_ids_using(db, m.id))


def get_material(db: DB, material_id: int) -> LearningMaterial:
    m = db.get(LearningMaterial, material_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found")
    return m


def set_text(db: DB, m: LearningMaterial, text: str) -> None:
    """Validates length and duplicates, then stores the text and clears the digest."""
    try:
        text = svc.check_length(text)
    except svc.MaterialError as e:
        raise HTTPException(e.status_code, str(e))
    digest = svc.content_hash(text)
    dup = db.scalar(select(LearningMaterial.id).where(LearningMaterial.content_hash == digest))
    if dup is not None and dup != m.id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This content is already uploaded (material {dup})")
    m.content_text, m.content_hash, m.char_count = text, digest, len(text)
    m.digest, m.digest_error = None, None


def create(db: DB, background: BackgroundTasks, admin: User, m: LearningMaterial, text: str) -> MaterialOut:
    set_text(db, m, text)
    m.uploaded_by = admin.id
    db.add(m)
    db.commit()
    background.add_task(svc.digest_job, m.id)
    log.info("Material %s added by admin %s (%s, %d chars)", m.id, admin.id, m.kind.value, m.char_count)
    return detail(db, m)


@router.post("", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
def add_material(body: MaterialIn, db: DB, admin: AdminUser, background: BackgroundTasks):
    """Paste text, or give a URL to fetch (same limits and SSRF checks as article grading)."""
    m = LearningMaterial(
        title=body.title.strip(), kind=MaterialKind(body.kind), module=body.module.strip(),
        week_key=body.week_key, specialization=body.specialization,
    )
    text = body.text or ""
    if body.kind == "url":
        try:
            _, text = fetch_article(str(body.url))
        except ArticleFetchError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
        m.source_url = str(body.url)
    return create(db, background, admin, m, text)


@router.post("/upload", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def upload_material(
    db: DB,
    admin: AdminUser,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
    module: Annotated[str, Form(max_length=120)] = "",
    week_key: Annotated[date | None, Form()] = None,
    specialization: Annotated[str | None, Form()] = None,
):
    """.md, .txt or .pdf up to 5 MB. Only the extracted text is kept."""
    try:
        specialization = _known_specialization(specialization or None)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"specialization {e}")
    data = await file.read(svc.MAX_UPLOAD_BYTES + 1)
    filename = (file.filename or "upload").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255]
    try:
        text = svc.extract_upload(filename, data)
    except svc.MaterialError as e:
        raise HTTPException(e.status_code, str(e))
    m = LearningMaterial(
        title=(title or filename).strip()[:200], kind=MaterialKind.file, original_filename=filename,
        module=module.strip(), week_key=week_key, specialization=specialization,
    )
    return create(db, background, admin, m, text)


@router.get("", response_model=list[MaterialSummary])
def list_materials(
    db: DB,
    _: AdminUser,
    module: str | None = None,
    week_key: date | None = None,
    specialization: str | None = None,
    status_: Annotated[MaterialStatus | None, Query(alias="status")] = None,
):
    q = select(LearningMaterial).order_by(LearningMaterial.created_at.desc())
    if module:
        q = q.where(LearningMaterial.module == module)
    if week_key:
        q = q.where(LearningMaterial.week_key == week_key)
    if specialization:
        q = q.where(LearningMaterial.specialization == specialization)
    if status_:
        q = q.where(LearningMaterial.status == status_)
    return [summary(m) for m in db.scalars(q).all()]


@router.get("/{material_id}", response_model=MaterialOut)
def get_one(material_id: int, db: DB, _: AdminUser):
    return detail(db, get_material(db, material_id))


@router.patch("/{material_id}", response_model=MaterialOut)
def update_material(material_id: int, body: MaterialUpdate, db: DB, _: AdminUser, background: BackgroundTasks):
    m = get_material(db, material_id)
    fields = body.model_dump(exclude_unset=True)
    text = fields.pop("content_text", None)
    if "status" in fields:
        fields["status"] = MaterialStatus(fields["status"])
    for name, value in fields.items():
        setattr(m, name, value.strip() if isinstance(value, str) and name in ("title", "module") else value)
    if text is not None:
        set_text(db, m, text)
    db.commit()
    if text is not None:
        background.add_task(svc.digest_job, m.id)
    return detail(db, m)


@router.delete("/{material_id}")
def delete_material(material_id: int, db: DB, _: AdminUser):
    """Deletes the material, or archives it if a quiz was generated from it."""
    m = get_material(db, material_id)
    if quiz_ids_using(db, m.id):
        m.status = MaterialStatus.archived
        db.commit()
        return {"archived": True, "deleted": False}
    db.delete(m)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{material_id}/refetch", response_model=MaterialOut)
def refetch(material_id: int, db: DB, _: AdminUser, background: BackgroundTasks):
    m = get_material(db, material_id)
    if m.kind != MaterialKind.url or not m.source_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only URL materials can be refetched")
    try:
        _, text = fetch_article(m.source_url)
    except ArticleFetchError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    set_text(db, m, text)
    db.commit()
    background.add_task(svc.digest_job, m.id)
    return detail(db, m)
