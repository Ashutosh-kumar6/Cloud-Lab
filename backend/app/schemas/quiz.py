from datetime import datetime
from pydantic import BaseModel, Field


# ── Question Schemas ──────────────────────────────────────────────────────────

class QuestionBase(BaseModel):
    question_text: str = Field(..., min_length=1)
    options: list[str] = Field(..., min_length=2)
    correct_option: int = Field(..., ge=0)
    explanation: str | None = None


class QuestionCreate(QuestionBase):
    pass


class QuestionUpdate(BaseModel):
    question_text: str | None = None
    options: list[str] | None = None
    correct_option: int | None = None
    explanation: str | None = None


class QuestionStudentOut(BaseModel):
    id: int
    quiz_id: int
    question_text: str
    options: list[str]

    model_config = {"from_attributes": True}


class QuestionTeacherOut(QuestionBase):
    id: int
    quiz_id: int

    model_config = {"from_attributes": True}


# ── Quiz Schemas ──────────────────────────────────────────────────────────────

class QuizBase(BaseModel):
    title: str = Field(..., max_length=200)
    topic: str = Field(..., max_length=50)
    description: str | None = None


class QuizCreate(QuizBase):
    questions: list[QuestionCreate] = []


class QuizUpdate(BaseModel):
    title: str | None = None
    topic: str | None = None
    description: str | None = None
    questions: list[QuestionCreate] | None = None


class QuizSummary(QuizBase):
    id: int
    total_questions: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizDetailStudent(QuizBase):
    id: int
    created_at: datetime
    questions: list[QuestionStudentOut]

    model_config = {"from_attributes": True}


class QuizDetailTeacher(QuizBase):
    id: int
    created_at: datetime
    questions: list[QuestionTeacherOut]

    model_config = {"from_attributes": True}


# ── Attempt & Feedback Schemas ────────────────────────────────────────────────

class AnswerSubmission(BaseModel):
    question_id: int
    selected_option: int


class QuizSubmitRequest(BaseModel):
    answers: list[AnswerSubmission]


class QuestionFeedback(BaseModel):
    question_id: int
    question_text: str
    options: list[str]
    selected_option: int | None
    correct_option: int
    is_correct: bool
    explanation: str | None = None


class QuizAttemptStartOut(BaseModel):
    attempt_id: int
    quiz_id: int
    quiz_title: str
    topic: str
    created_at: datetime
    completed: bool
    questions: list[QuestionStudentOut]


class QuizAttemptSummary(BaseModel):
    id: int
    quiz_id: int
    quiz_title: str
    topic: str
    score: float
    total_questions: int
    correct_answers: int
    completed: bool
    created_at: datetime
    completed_at: datetime | None


class QuizAttemptResultOut(BaseModel):
    id: int
    quiz_id: int
    quiz_title: str
    topic: str
    score: float
    total_questions: int
    correct_answers: int
    completed: bool
    created_at: datetime
    completed_at: datetime | None
    feedback: list[QuestionFeedback]
