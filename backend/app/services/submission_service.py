from sqlalchemy.orm import Session

from app.models.exercise import Exercise
from app.models.submission import Submission
from app.models.user import User
from app.runner.grader import grade


def create_submission(db: Session, user: User, exercise: Exercise, code: str) -> Submission:
    submission = Submission(
        user_id=user.id,
        exercise_id=exercise.id,
        code=code,
        status="running",
        passed_count=0,
        total_count=len(exercise.test_cases),
        output="",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    grade(db, submission.id)
    db.refresh(submission)
    return submission
