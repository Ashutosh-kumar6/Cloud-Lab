from pydantic import BaseModel


class WeakTopic(BaseModel):
    topic: str
    weakness_score: float
    accuracy_percent: float
    unsolved_exercises: int
    reason: str


class RecommendedExercise(BaseModel):
    exercise_id: int
    title: str
    topic: str
    difficulty: str
    reason: str


class RecommendationsOut(BaseModel):
    message: str
    weak_topics: list[WeakTopic]
    recommended_exercises: list[RecommendedExercise]
