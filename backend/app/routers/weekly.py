from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.models import (
    BriefStatus,
    ProjectPick,
    ProjectProposal,
    QuizAttempt,
    QuizKind,
    QuizStatus,
    User,
    WeeklyBrief,
    as_utc,
    utcnow,
)
from app.schemas_weekly import (
    BriefIn,
    BriefOut,
    PickIn,
    ProposalIn,
    ProposalOut,
    QuizSlot,
    UpcomingWeek,
    WeeklyCurrent,
)
from app.services import quizzes
from app.services.weekly import summarize_brief_job
from app.weeks import current_month_key, current_week_key, now_local, upcoming_week_key

router = APIRouter(prefix="/weekly", tags=["weekly"])

SLOTS = (1, 2)


def brief_out(brief: WeeklyBrief) -> BriefOut:
    return BriefOut(
        id=brief.id, week_key=brief.week_key, status=brief.status.value, summary=brief.summary,
        concepts=brief.concepts or [], summary_error=brief.summary_error,
        has_notes=bool(brief.source_notes.strip()), updated_at=as_utc(brief.updated_at),
    )


def proposals_for(db: DB, week: date, user: User) -> list[ProposalOut]:
    picks = dict(
        db.execute(
            select(ProjectPick.proposal_id, func.count()).where(ProjectPick.week_key == week).group_by(ProjectPick.proposal_id)
        ).all()
    )
    mine = db.scalar(select(ProjectPick.proposal_id).where(ProjectPick.week_key == week, ProjectPick.user_id == user.id))
    rows = db.scalars(select(ProjectProposal).where(ProjectProposal.week_key == week).order_by(ProjectProposal.slot)).all()
    return [
        ProposalOut(
            id=p.id, week_key=p.week_key, slot=p.slot, title=p.title, description=p.description,
            proposer_id=p.proposer_id, proposer_name=p.proposer.name, picks=picks.get(p.id, 0), picked_by_me=p.id == mine,
        )
        for p in rows
    ]


def quiz_slots(db: DB, user: User, week: date, month: str) -> list[QuizSlot]:
    ai = bool(get_settings().anthropic_api_key)
    targets = [
        (QuizKind.weekly, week.isoformat(), None),
        (QuizKind.course, month, None),
        (QuizKind.interview, month, quizzes.member_specialization(user)),
    ]
    slots = []
    for kind, period, spec in targets:
        has_sources: bool | None = None
        for duration in quizzes.DURATIONS:
            quiz = quizzes.find_quiz(db, kind, period, spec, duration)
            slot = QuizSlot(
                kind=kind.value, period_key=period, specialization=spec, duration_minutes=duration,
                question_count=quizzes.DURATION_QUESTIONS[duration], available=False,
            )
            attempt = quiz and db.scalar(
                select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.user_id == user.id)
            )
            if attempt:
                quizzes.finalize_if_expired(db, attempt)
                slot.attempt_id, slot.submitted = attempt.id, attempt.submitted_at is not None
                slot.score, slot.max_score = attempt.score, attempt.max_score
            if quiz and quiz.status == QuizStatus.published:
                slot.available = True
            elif quiz and quiz.status == QuizStatus.draft:
                slot.reason = "Waiting for admin review"
            elif quiz and quiz.status == QuizStatus.generating:
                slot.reason = "Being generated, check back in a minute"
            elif quiz and quiz.status == QuizStatus.failed and not ai:
                slot.reason = "AI quizzes aren't configured yet"
            else:  # not generated yet (or failed earlier): generated when started
                if has_sources is None:
                    has_sources = bool(quizzes.gather_sources(db, kind, period, spec).text.strip())
                if not ai:
                    slot.reason = "AI quizzes aren't configured yet"
                elif not has_sources:
                    slot.reason = "No class notes for this week yet" if kind == QuizKind.weekly else "No course material yet"
                else:
                    slot.available = True
            slots.append(slot)
    return slots


@router.get("/current", response_model=WeeklyCurrent)
def current_week(db: DB, user: CurrentUser):
    now = now_local()
    week, upcoming = current_week_key(now), upcoming_week_key(now)
    brief = db.scalar(select(WeeklyBrief).where(WeeklyBrief.week_key == week))
    upcoming_brief = db.scalar(select(WeeklyBrief).where(WeeklyBrief.week_key == upcoming))
    upcoming_projects = proposals_for(db, upcoming, user)
    return WeeklyCurrent(
        week_key=week,
        month_key=current_month_key(now),
        server_now=utcnow(),
        ai_configured=bool(get_settings().anthropic_api_key),
        brief=brief_out(brief) if brief else None,
        projects=proposals_for(db, week, user),
        my_pick=db.scalar(select(ProjectPick.proposal_id).where(ProjectPick.week_key == week, ProjectPick.user_id == user.id)),
        upcoming=UpcomingWeek(
            week_key=upcoming,
            projects=upcoming_projects,
            slots_left=len(SLOTS) - len(upcoming_projects),
            my_proposal_id=next((p.id for p in upcoming_projects if p.proposer_id == user.id), None),
            has_notes=bool(upcoming_brief and upcoming_brief.source_notes.strip()),
        ),
        quizzes=quiz_slots(db, user, week, current_month_key(now)),
    )


@router.get("/brief", response_model=BriefOut | None)
def upcoming_brief(db: DB, _: CurrentUser):
    """The notes collected so far for the next drop."""
    brief = db.scalar(select(WeeklyBrief).where(WeeklyBrief.week_key == upcoming_week_key()))
    return brief_out(brief).model_copy(update={"source_notes": brief.source_notes}) if brief else None


@router.put("/brief", response_model=BriefOut)
def save_brief(body: BriefIn, db: DB, user: CurrentUser, background: BackgroundTasks):
    """Any member or admin can paste the class notes for the next drop."""
    week = upcoming_week_key()
    brief = db.scalar(select(WeeklyBrief).where(WeeklyBrief.week_key == week))
    if brief is None:
        brief = WeeklyBrief(week_key=week, created_by=user.id, source_notes="")
        db.add(brief)
    elif brief.status == BriefStatus.sent:
        raise HTTPException(status.HTTP_409_CONFLICT, "This week's drop has already gone out")
    brief.source_notes = body.source_notes.strip()
    brief.summary, brief.concepts, brief.summary_error, brief.status = None, [], None, BriefStatus.draft
    db.commit()
    background.add_task(summarize_brief_job, brief.id)
    return brief_out(brief)


@router.post("/projects", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def propose(body: ProposalIn, db: DB, user: CurrentUser):
    week = upcoming_week_key()
    for _ in range(2):  # a lost race on slot 1 can still win slot 2
        if db.scalar(select(ProjectProposal.id).where(ProjectProposal.week_key == week, ProjectProposal.proposer_id == user.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "You've already proposed a project for this week")
        taken = set(db.scalars(select(ProjectProposal.slot).where(ProjectProposal.week_key == week)).all())
        free = [s for s in SLOTS if s not in taken]
        if not free:
            raise HTTPException(status.HTTP_409_CONFLICT, "Both project slots for this week are taken")
        proposal = ProjectProposal(
            week_key=week, slot=free[0], proposer_id=user.id, title=body.title.strip(), description=body.description.strip()
        )
        db.add(proposal)
        try:
            db.commit()
        except IntegrityError:  # the unique constraints caught a concurrent proposal
            db.rollback()
            continue
        return next(p for p in proposals_for(db, week, user) if p.id == proposal.id)
    raise HTTPException(status.HTTP_409_CONFLICT, "Both project slots for this week are taken")


@router.delete("/projects/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw(proposal_id: int, db: DB, user: CurrentUser):
    proposal = db.get(ProjectProposal, proposal_id)
    if proposal is None or (proposal.proposer_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found")
    if not user.is_admin and proposal.week_key != upcoming_week_key():
        raise HTTPException(status.HTTP_409_CONFLICT, "This project is already in a drop; ask an admin to remove it")
    db.delete(proposal)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/projects/pick", response_model=PickIn)
def pick(body: PickIn, db: DB, user: CurrentUser):
    week = current_week_key()
    proposal = db.get(ProjectProposal, body.proposal_id)
    if proposal is None or proposal.week_key != week:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can only pick one of this week's projects")
    for _ in range(2):
        existing = db.scalar(select(ProjectPick).where(ProjectPick.week_key == week, ProjectPick.user_id == user.id))
        if existing:
            existing.proposal_id, existing.picked_at = proposal.id, utcnow()
        else:
            db.add(ProjectPick(week_key=week, user_id=user.id, proposal_id=proposal.id))
        try:
            db.commit()
            return PickIn(proposal_id=proposal.id)
        except IntegrityError:  # double click created it first; update instead
            db.rollback()
    raise HTTPException(status.HTTP_409_CONFLICT, "Couldn't save your pick, try again")
