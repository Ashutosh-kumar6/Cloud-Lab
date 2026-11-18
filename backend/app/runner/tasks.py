from app.db.session import SessionLocal
from app.runner.celery_app import celery_app
from app.runner.grader import grade


@celery_app.task(name="run_submission")
def run_submission(submission_id: int) -> None:
    db = SessionLocal()
    try:
        grade(db, submission_id)
    finally:
        db.close()
