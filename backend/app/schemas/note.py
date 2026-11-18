from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=50)
    body: str = Field(min_length=1)


class NoteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    topic: str


class NoteDetail(NoteSummary):
    body: str
    created_at: datetime
