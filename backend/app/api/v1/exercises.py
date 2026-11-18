from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.user import User
from app.schemas.exercise import ExerciseDetail, ExerciseSummary, TestCaseOut

router = APIRouter(prefix="/exercises", tags=["Exercises"])


@router.get("", response_model=list[ExerciseSummary])
def list_exercises(
    topic: str | None = None,
    difficulty: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Exercise).order_by(Exercise.id)
    if topic:
        query = query.where(Exercise.topic == topic)
    if difficulty:
        query = query.where(Exercise.difficulty == difficulty)
    return db.scalars(query).all()


@router.get("/{exercise_id}", response_model=ExerciseDetail)
def get_exercise(
    exercise_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found")

    samples = [
        TestCaseOut.model_validate(tc) for tc in exercise.test_cases if not tc.is_hidden
    ]
    return ExerciseDetail(
        id=exercise.id,
        title=exercise.title,
        topic=exercise.topic,
        difficulty=exercise.difficulty,
        description=exercise.description,
        sample_test_cases=samples,
    )
