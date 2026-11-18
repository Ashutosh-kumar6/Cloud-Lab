from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TestCase(Base):
    __tablename__ = "test_cases"
    __test__ = False  # stops pytest from treating this class as a test

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    input_text: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    exercise: Mapped["Exercise"] = relationship(back_populates="test_cases")
