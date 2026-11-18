import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.explainer import explain_error
from app.ai.rules import explain_with_rules
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.submission import Submission
from app.models.user import User
from app.schemas.ai import ExplainOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])

MAX_REQUESTS_PER_HOUR = 10
_recent_requests: dict[int, deque] = defaultdict(deque)


def _allow_request(user_id: int) -> bool:
    now = time.time()
    window = _recent_requests[user_id]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= MAX_REQUESTS_PER_HOUR:
        return False
    window.append(now)
    return True


def _ai_configured() -> bool:
    key = settings.gemini_api_key
    return bool(key) and key != "paste-your-key-here"


@router.post("/explain/{submission_id}", response_model=ExplainOut)
def explain_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.get(Submission, submission_id)
    is_staff = current_user.role in ("teacher", "admin")
    if submission is None or (submission.user_id != current_user.id and not is_staff):
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status == "passed":
        raise HTTPException(status_code=400, detail="This submission passed. Nothing to explain.")

    if _ai_configured() and _allow_request(current_user.id):
        try:
            text = explain_error(submission.code, submission.output)
            return ExplainOut(submission_id=submission.id, explanation=text, source="ai")
        except Exception as exc:
            logger.warning("AI explanation failed, using rules instead: %s", exc)

    text = explain_with_rules(submission.status, submission.output)
    return ExplainOut(submission_id=submission.id, explanation=text, source="rules")
