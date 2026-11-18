from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.quiz import Question, Quiz, QuizAttempt
from app.models.user import User
from app.schemas.quiz import (
    AnswerSubmission,
    QuestionCreate,
    QuestionFeedback,
    QuizAttemptResultOut,
    QuizAttemptStartOut,
    QuizCreate,
    QuizSubmitRequest,
    QuizUpdate,
)


def create_quiz(db: Session, user: User, data: QuizCreate) -> Quiz:
    quiz = Quiz(
        title=data.title,
        topic=data.topic,
        description=data.description,
        created_by=user.id,
    )
    for q in data.questions:
        if q.correct_option < 0 or q.correct_option >= len(q.options):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"correct_option {q.correct_option} is out of bounds for options count {len(q.options)}",
            )
        question = Question(
            question_text=q.question_text,
            options=q.options,
            correct_option=q.correct_option,
            explanation=q.explanation,
        )
        quiz.questions.append(question)

    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


def update_quiz(db: Session, quiz: Quiz, data: QuizUpdate) -> Quiz:
    if data.title is not None:
        quiz.title = data.title
    if data.topic is not None:
        quiz.topic = data.topic
    if data.description is not None:
        quiz.description = data.description

    if data.questions is not None:
        quiz.questions.clear()
        for q in data.questions:
            if q.correct_option < 0 or q.correct_option >= len(q.options):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"correct_option {q.correct_option} is out of bounds for options count {len(q.options)}",
                )
            quiz.questions.append(
                Question(
                    question_text=q.question_text,
                    options=q.options,
                    correct_option=q.correct_option,
                    explanation=q.explanation,
                )
            )

    db.commit()
    db.refresh(quiz)
    return quiz


def start_attempt(db: Session, user: User, quiz: Quiz) -> QuizAttempt:
    if not quiz.questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot attempt a quiz with no questions",
        )

    attempt = QuizAttempt(
        user_id=user.id,
        quiz_id=quiz.id,
        total_questions=len(quiz.questions),
        correct_answers=0,
        score=0.0,
        completed=False,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def submit_attempt(
    db: Session, user: User, quiz: Quiz, attempt: QuizAttempt, data: QuizSubmitRequest
) -> QuizAttemptResultOut:
    if attempt.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot submit answers for another user's attempt",
        )
    if attempt.quiz_id != quiz.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attempt does not belong to this quiz",
        )
    if attempt.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attempt has already been completed",
        )

    # Map user answers by question_id
    submitted_answers: dict[int, int] = {
        ans.question_id: ans.selected_option for ans in data.answers
    }

    feedback_list: list[QuestionFeedback] = []
    correct_count = 0
    total = len(quiz.questions)

    stored_feedback = []
    for question in quiz.questions:
        selected = submitted_answers.get(question.id)
        is_correct = selected is not None and selected == question.correct_option
        if is_correct:
            correct_count += 1

        fb = QuestionFeedback(
            question_id=question.id,
            question_text=question.question_text,
            options=question.options,
            selected_option=selected,
            correct_option=question.correct_option,
            is_correct=is_correct,
            explanation=question.explanation,
        )
        feedback_list.append(fb)
        stored_feedback.append(fb.model_dump())

    score_percent = round((correct_count / total * 100.0), 1) if total > 0 else 0.0

    attempt.completed = True
    attempt.completed_at = datetime.utcnow()
    attempt.correct_answers = correct_count
    attempt.total_questions = total
    attempt.score = score_percent
    attempt.answers = stored_feedback

    db.commit()
    db.refresh(attempt)

    return QuizAttemptResultOut(
        id=attempt.id,
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        topic=quiz.topic,
        score=attempt.score,
        total_questions=attempt.total_questions,
        correct_answers=attempt.correct_answers,
        completed=attempt.completed,
        created_at=attempt.created_at,
        completed_at=attempt.completed_at,
        feedback=feedback_list,
    )


def format_attempt_result(attempt: QuizAttempt, quiz: Quiz) -> QuizAttemptResultOut:
    feedback_data = attempt.answers or []
    feedback = [QuestionFeedback(**fb) for fb in feedback_data]
    return QuizAttemptResultOut(
        id=attempt.id,
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        topic=quiz.topic,
        score=attempt.score,
        total_questions=attempt.total_questions,
        correct_answers=attempt.correct_answers,
        completed=attempt.completed,
        created_at=attempt.created_at,
        completed_at=attempt.completed_at,
        feedback=feedback,
    )
