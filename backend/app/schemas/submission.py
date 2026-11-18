from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubmissionCreate(BaseModel):
    exercise_id: int
    code: str = Field(min_length=1, max_length=10000)


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: int
    status: str
    passed_count: int
    total_count: int
    output: str
    created_at: datetime
