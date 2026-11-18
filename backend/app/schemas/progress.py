from pydantic import BaseModel


class TopicProgress(BaseModel):
    topic: str
    total_exercises: int
    attempted_exercises: int
    solved_exercises: int
    total_submissions: int
    accuracy_percent: float
    total_quizzes: int = 0
    attempted_quizzes: int = 0
    completed_quizzes: int = 0
    quiz_accuracy_percent: float = 0.0


class ProgressOut(BaseModel):
    total_exercises: int
    solved_exercises: int
    total_submissions: int
    current_streak: int
    longest_streak: int
    topics: list[TopicProgress]
    total_quizzes: int = 0
    completed_quizzes: int = 0
    total_quiz_attempts: int = 0
    quiz_average_score: float = 0.0
