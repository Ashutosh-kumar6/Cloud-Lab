import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.quiz import Quiz, QuizAttempt
from app.models.user import User
from app.schemas.quiz import (
    QuestionStudentOut,
    QuestionTeacherOut,
    QuizAttemptResultOut,
    QuizAttemptStartOut,
    QuizAttemptSummary,
    QuizCreate,
    QuizDetailStudent,
    QuizDetailTeacher,
    QuizSubmitRequest,
    QuizSummary,
    QuizUpdate,
)
from app.services import quiz_service
from app.services.activity_tracker import touch_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


def _get_redis():
    """Return a redis.Redis client, or None if unavailable (e.g. in tests)."""
    try:
        import redis as redis_module
        from app.core.config import settings
        return redis_module.from_url(settings.redis_url, decode_responses=False)
    except Exception:
        return None


def _touch(user_id: int) -> None:
    """Best-effort activity touch — never raises."""
    try:
        redis = _get_redis()
        if redis is not None:
            touch_user(redis, user_id)
    except Exception:
        logger.debug("activity_tracker: could not touch user %s", user_id)


@router.get("", response_model=list[QuizSummary])
def list_quizzes(
    topic: str | None = Query(None, description="Filter by topic"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Quiz).order_by(Quiz.id)
    if topic:
        query = query.where(Quiz.topic == topic)
    quizzes = db.scalars(query).all()

    return [
        QuizSummary(
            id=q.id,
            title=q.title,
            topic=q.topic,
            description=q.description,
            total_questions=len(q.questions),
            created_at=q.created_at,
        )
        for q in quizzes
    ]


@router.post("", response_model=QuizDetailTeacher, status_code=status.HTTP_201_CREATED)
def create_quiz(
    data: QuizCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    quiz = quiz_service.create_quiz(db, current_user, data)
    return QuizDetailTeacher(
        id=quiz.id,
        title=quiz.title,
        topic=quiz.topic,
        description=quiz.description,
        created_at=quiz.created_at,
        questions=[QuestionTeacherOut.model_validate(q) for q in quiz.questions],
    )


@router.get("/{quiz_id}")
def get_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    if current_user.role in ("teacher", "admin"):
        return QuizDetailTeacher(
            id=quiz.id,
            title=quiz.title,
            topic=quiz.topic,
            description=quiz.description,
            created_at=quiz.created_at,
            questions=[QuestionTeacherOut.model_validate(q) for q in quiz.questions],
        )

    # For students: hide correct_option and explanation
    return QuizDetailStudent(
        id=quiz.id,
        title=quiz.title,
        topic=quiz.topic,
        description=quiz.description,
        created_at=quiz.created_at,
        questions=[QuestionStudentOut.model_validate(q) for q in quiz.questions],
    )


@router.put("/{quiz_id}", response_model=QuizDetailTeacher)
def update_quiz(
    quiz_id: int,
    data: QuizUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    updated = quiz_service.update_quiz(db, quiz, data)
    return QuizDetailTeacher(
        id=updated.id,
        title=updated.title,
        topic=updated.topic,
        description=updated.description,
        created_at=updated.created_at,
        questions=[QuestionTeacherOut.model_validate(q) for q in updated.questions],
    )


@router.delete("/{quiz_id}", status_code=status.HTTP_200_OK)
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    db.delete(quiz)
    db.commit()
    return {"message": "Quiz deleted successfully"}


# ── Attempt Endpoints ─────────────────────────────────────────────────────────

@router.post("/{quiz_id}/attempts", response_model=QuizAttemptStartOut, status_code=status.HTTP_201_CREATED)
def start_quiz_attempt(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    attempt = quiz_service.start_attempt(db, current_user, quiz)
    _touch(current_user.id)
    return QuizAttemptStartOut(
        attempt_id=attempt.id,
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        topic=quiz.topic,
        created_at=attempt.created_at,
        completed=attempt.completed,
        questions=[QuestionStudentOut.model_validate(q) for q in quiz.questions],
    )


@router.post("/{quiz_id}/attempts/{attempt_id}/submit", response_model=QuizAttemptResultOut)
def submit_quiz_attempt(
    quiz_id: int,
    attempt_id: int,
    data: QuizSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    result = quiz_service.submit_attempt(db, current_user, quiz, attempt, data)
    _touch(current_user.id)
    return result


@router.get("/attempts/{attempt_id}", response_model=QuizAttemptResultOut)
def get_attempt_result(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    if current_user.role not in ("teacher", "admin") and attempt.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this attempt")

    if not attempt.completed:
        raise HTTPException(status_code=400, detail="Attempt has not been completed yet")

    quiz = db.get(Quiz, attempt.quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Associated quiz not found")

    return quiz_service.format_attempt_result(attempt, quiz)


@router.get("/{quiz_id}/my-attempts", response_model=list[QuizAttemptSummary])
def get_my_quiz_attempts(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")

    attempts = db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == current_user.id)
        .order_by(QuizAttempt.id.desc())
    ).all()

    return [
        QuizAttemptSummary(
            id=a.id,
            quiz_id=quiz.id,
            quiz_title=quiz.title,
            topic=quiz.topic,
            score=a.score,
            total_questions=a.total_questions,
            correct_answers=a.correct_answers,
            completed=a.completed,
            created_at=a.created_at,
            completed_at=a.completed_at,
        )
        for a in attempts
    ]
