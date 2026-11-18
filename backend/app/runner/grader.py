import logging

from docker.errors import DockerException
from sqlalchemy.orm import Session

from app.core.metrics import (
    record_sandbox_timeout,
    record_submission_failure,
    record_submission_graded,
)
from app.models.exercise import Exercise
from app.models.submission import Submission
from app.runner.checker import is_correct
from app.runner.sandbox import TIME_LIMIT_SECONDS, run_python

logger = logging.getLogger(__name__)


def grade(db: Session, submission_id: int) -> None:
    submission = db.get(Submission, submission_id)
    if submission is None:
        return
    exercise = db.get(Exercise, submission.exercise_id)
    if exercise is None:
        submission.status = "error"
        submission.output = "Exercise not found"
        db.commit()
        record_submission_graded("error")
        record_submission_failure()
        return

    submission.status = "running"
    db.commit()

    passed = 0
    status = "passed"
    output = ""

    try:
        for tc in exercise.test_cases:
            try:
                result = run_python(submission.code, tc.input_text)
            except DockerException as exc:
                status = "error"
                output = f"Sandbox unavailable: {exc}"
                break

            if result.timed_out:
                status = "timeout"
                output = f"Time limit exceeded ({TIME_LIMIT_SECONDS} seconds)"
                break
            if result.exit_code != 0:
                status = "error"
                output = result.stderr
                break
            if is_correct(result.stdout, tc.expected_output):
                passed += 1
            elif status == "passed":
                status = "failed"
                if tc.is_hidden:
                    output = "Your program gave a wrong answer on a hidden test case."
                else:
                    output = (
                        f"Input:\n{tc.input_text}\n"
                        f"Expected:\n{tc.expected_output}\n"
                        f"Got:\n{result.stdout}"
                    )
    except Exception:
        logger.exception("Unexpected error while grading submission %s", submission_id)
        status = "error"
        output = "Internal error while grading your code. Please try again."

    submission.status = status
    submission.passed_count = passed
    submission.total_count = len(exercise.test_cases)
    submission.output = output
    db.commit()

    record_submission_graded(status)
    if status == "timeout":
        record_sandbox_timeout()
        record_submission_failure()
    elif status in ("failed", "error"):
        record_submission_failure()
