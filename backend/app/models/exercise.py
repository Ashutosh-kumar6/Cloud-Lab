from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(50), index=True)
    difficulty: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    test_cases: Mapped[list["TestCase"]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )
