from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.exercise import ExerciseCreate, ExerciseSummary

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_role("teacher", "admin"))],
)


@router.post("/exercises", response_model=ExerciseSummary, status_code=status.HTTP_201_CREATED)
def create_exercise(
    data: ExerciseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    if not data.test_cases:
        raise HTTPException(status_code=400, detail="At least one test case is required")

    exercise = Exercise(
        title=data.title,
        topic=data.topic,
        difficulty=data.difficulty,
        description=data.description,
        created_by=current_user.id,
        test_cases=[
            TestCase(
                input_text=tc.input_text,
                expected_output=tc.expected_output,
                is_hidden=tc.is_hidden,
            )
            for tc in data.test_cases
        ],
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise
