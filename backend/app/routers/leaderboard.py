from fastapi import APIRouter

from app.deps import DB, CurrentUser
from app.routers.challenges import visible_challenge_or_404
from app.schemas import LeaderboardRow
from app.services.leaderboard import challenge_leaderboard, global_leaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/global", response_model=list[LeaderboardRow])
def global_board(db: DB, _: CurrentUser):
    return global_leaderboard(db)


@router.get("/{challenge_id}", response_model=list[LeaderboardRow])
def challenge_board(challenge_id: int, db: DB, user: CurrentUser):
    visible_challenge_or_404(db, challenge_id, user)
    return challenge_leaderboard(db, challenge_id)
