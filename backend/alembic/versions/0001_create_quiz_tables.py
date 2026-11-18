"""create quiz tables

Revision ID: 0001_create_quiz_tables
Revises: 
Create Date: 2026-11-18 01:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_create_quiz_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_quizzes_topic"), "quizzes", ["topic"], unique=False)

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("quiz_id", sa.Integer(), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_option", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_questions_quiz_id"), "questions", ["quiz_id"], unique=False)

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quiz_id", sa.Integer(), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_answers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_quiz_attempts_user_id"), "quiz_attempts", ["user_id"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_quiz_id"), "quiz_attempts", ["quiz_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quiz_attempts_quiz_id"), table_name="quiz_attempts")
    op.drop_index(op.f("ix_quiz_attempts_user_id"), table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index(op.f("ix_questions_quiz_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_quizzes_topic"), table_name="quizzes")
    op.drop_table("quizzes")
