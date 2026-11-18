from prometheus_client import Counter

SUBMISSIONS_GRADED = Counter(
    "submissions_graded_total",
    "Total number of code submissions graded",
    ["status"],
)

SUBMISSION_FAILURES = Counter(
    "submission_failures_total",
    "Total number of code submissions that failed or errored",
)

SANDBOX_TIMEOUTS = Counter(
    "sandbox_timeouts_total",
    "Total number of code execution sandbox timeouts",
)

LOGIN_FAILURES = Counter(
    "login_failures_total",
    "Total number of failed user login attempts",
)


def record_submission_graded(status: str) -> None:
    SUBMISSIONS_GRADED.labels(status=status).inc()


def record_submission_failure() -> None:
    SUBMISSION_FAILURES.inc()


def record_sandbox_timeout() -> None:
    SANDBOX_TIMEOUTS.inc()


def record_login_failure() -> None:
    LOGIN_FAILURES.inc()
