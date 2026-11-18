from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.exercise import Exercise
from app.models.submission import Submission
from app.models.user import User
from app.schemas.recommendation import (
    RecommendationsOut,
    RecommendedExercise,
    WeakTopic,
)
from app.services.progress_service import get_progress

DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
WEAK_THRESHOLD = 0.3
MAX_TOTAL = 5
MAX_PER_TOPIC = 2


def get_recommendations(db: Session, user: User) -> RecommendationsOut:
    progress = get_progress(db, user)
    exercises = db.scalars(select(Exercise).order_by(Exercise.id)).all()
    solved_ids = set(
        db.scalars(
            select(Submission.exercise_id).where(
                Submission.user_id == user.id, Submission.status == "passed"
            )
        ).all()
    )

    ranked: list[WeakTopic] = []
    for tp in progress.topics:
        unsolved = tp.total_exercises - tp.solved_exercises
        if unsolved <= 0:
            continue
        if tp.total_submissions == 0:
            score = 0.5
            reason = "You have not started this topic yet."
        elif tp.accuracy_percent >= 100:
            score = 0.0
            reason = "You are doing well here. Try the remaining exercises."
        else:
            score = round(1 - tp.accuracy_percent / 100, 2)
            reason = (
                f"Only {tp.accuracy_percent}% of your {tp.total_submissions} "
                f"submissions in this topic passed."
            )
        ranked.append(
            WeakTopic(
                topic=tp.topic,
                weakness_score=score,
                accuracy_percent=tp.accuracy_percent,
                unsolved_exercises=unsolved,
                reason=reason,
            )
        )
    ranked.sort(key=lambda w: (-w.weakness_score, w.topic))

    recommended: list[RecommendedExercise] = []
    for w in ranked:
        candidates = [
            e for e in exercises if e.topic == w.topic and e.id not in solved_ids
        ]
        candidates.sort(key=lambda e: (DIFFICULTY_ORDER.get(e.difficulty, 1), e.id))
        for e in candidates[:MAX_PER_TOPIC]:
            recommended.append(
                RecommendedExercise(
                    exercise_id=e.id,
                    title=e.title,
                    topic=e.topic,
                    difficulty=e.difficulty,
                    reason=f"Practice for {w.topic}: {w.reason}",
                )
            )
            if len(recommended) >= MAX_TOTAL:
                break
        if len(recommended) >= MAX_TOTAL:
            break

    weak_topics = [w for w in ranked if w.weakness_score >= WEAK_THRESHOLD]

    if not exercises:
        message = "No exercises are available yet."
    elif not recommended:
        message = "You have solved every exercise. Great work!"
    elif weak_topics:
        message = f"Focus on {weak_topics[0].topic} first."
    else:
        message = "You are doing well. Keep going with the exercises below."

    return RecommendationsOut(
        message=message,
        weak_topics=weak_topics,
        recommended_exercises=recommended,
    )
