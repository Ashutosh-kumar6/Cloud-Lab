import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import check_rate_limit
from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.submission import Submission
from app.models.user import User
from app.schemas.submission import SubmissionCreate, SubmissionOut
from app.services.activity_tracker import touch_user
from app.services.submission_service import create_submission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["Submissions"])


def _get_redis():
    """Return a redis.Redis client, or None if unavailable (e.g. in tests)."""
    try:
        from app.core.config import settings
        if settings.environment.lower() == "testing":
            return None
        import redis as redis_module
        return redis_module.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    except Exception:
        return None


@router.post("", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
def submit_code(
    data: SubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_rate_limit(
        key=f"sub:{current_user.id}",
        max_requests=10,
        window_seconds=60,
        detail="Submission rate limit exceeded. Please wait a minute before submitting again.",
    )

    exercise = db.get(Exercise, data.exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found")

    result = create_submission(db, current_user, exercise, data.code)

    # Record activity — best-effort, never fail the request on tracker errors.
    try:
        redis = _get_redis()
        if redis is not None:
            touch_user(redis, current_user.id)
    except Exception:
        logger.debug("activity_tracker: could not touch user %s", current_user.id)

    return result


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.get(Submission, submission_id)
    is_staff = current_user.role in ("teacher", "admin")
    if submission is None or (submission.user_id != current_user.id and not is_staff):
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission
