from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.exercise import Exercise
from app.models.quiz import Quiz, QuizAttempt
from app.models.submission import Submission
from app.models.user import User
from app.schemas.progress import ProgressOut, TopicProgress


def _streaks(days: set[date], today: date) -> tuple[int, int]:
    if not days:
        return 0, 0

    current = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    previous = None
    for day in sorted(days):
        if previous is not None and day - previous == timedelta(days=1):
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        previous = day

    return current, longest


def get_progress(db: Session, user: User) -> ProgressOut:
    exercises = db.scalars(select(Exercise)).all()
    submissions = db.scalars(
        select(Submission).where(Submission.user_id == user.id)
    ).all()
    quizzes = db.scalars(select(Quiz)).all()
    quiz_attempts = db.scalars(
        select(QuizAttempt).where(QuizAttempt.user_id == user.id)
    ).all()

    topic_of_exercise = {e.id: e.topic for e in exercises}
    topic_of_quiz = {q.id: q.topic for q in quizzes}

    topics: dict[str, dict] = {}
    for e in exercises:
        t = topics.setdefault(
            e.topic,
            {
                "total_ex": 0,
                "attempted_ex": set(),
                "solved_ex": set(),
                "subs": 0,
                "passed": 0,
                "total_quizzes": 0,
                "attempted_quizzes": set(),
                "completed_quizzes": set(),
                "quiz_scores": [],
            },
        )
        t["total_ex"] += 1

    for q in quizzes:
        t = topics.setdefault(
            q.topic,
            {
                "total_ex": 0,
                "attempted_ex": set(),
                "solved_ex": set(),
                "subs": 0,
                "passed": 0,
                "total_quizzes": 0,
                "attempted_quizzes": set(),
                "completed_quizzes": set(),
                "quiz_scores": [],
            },
        )
        t["total_quizzes"] += 1

    for s in submissions:
        topic = topic_of_exercise.get(s.exercise_id)
        if topic is None:
            continue
        t = topics[topic]
        t["attempted_ex"].add(s.exercise_id)
        t["subs"] += 1
        if s.status == "passed":
            t["solved_ex"].add(s.exercise_id)
            t["passed"] += 1

    for a in quiz_attempts:
        topic = topic_of_quiz.get(a.quiz_id)
        if topic is None:
            continue
        t = topics[topic]
        t["attempted_quizzes"].add(a.quiz_id)
        if a.completed:
            t["completed_quizzes"].add(a.quiz_id)
            t["quiz_scores"].append(a.score)

    topic_list = [
        TopicProgress(
            topic=name,
            total_exercises=t["total_ex"],
            attempted_exercises=len(t["attempted_ex"]),
            solved_exercises=len(t["solved_ex"]),
            total_submissions=t["subs"],
            accuracy_percent=round(100 * t["passed"] / t["subs"], 1) if t["subs"] else 0.0,
            total_quizzes=t["total_quizzes"],
            attempted_quizzes=len(t["attempted_quizzes"]),
            completed_quizzes=len(t["completed_quizzes"]),
            quiz_accuracy_percent=round(sum(t["quiz_scores"]) / len(t["quiz_scores"]), 1)
            if t["quiz_scores"]
            else 0.0,
        )
        for name, t in sorted(topics.items())
    ]

    # Combine activity days from submissions and completed quiz attempts
    days = {s.created_at.date() for s in submissions}
    for a in quiz_attempts:
        if a.completed and a.completed_at:
            days.add(a.completed_at.date())
        elif a.created_at:
            days.add(a.created_at.date())

    current, longest = _streaks(days, datetime.utcnow().date())

    completed_attempts = [a for a in quiz_attempts if a.completed]
    quiz_avg_score = (
        round(sum(a.score for a in completed_attempts) / len(completed_attempts), 1)
        if completed_attempts
        else 0.0
    )
    completed_quiz_ids = {a.quiz_id for a in completed_attempts}

    return ProgressOut(
        total_exercises=len(exercises),
        solved_exercises=sum(tp.solved_exercises for tp in topic_list),
        total_submissions=len(submissions),
        current_streak=current,
        longest_streak=longest,
        topics=topic_list,
        total_quizzes=len(quizzes),
        completed_quizzes=len(completed_quiz_ids),
        total_quiz_attempts=len(quiz_attempts),
        quiz_average_score=quiz_avg_score,
    )
