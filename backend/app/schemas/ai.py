from pydantic import BaseModel


class ExplainOut(BaseModel):
    submission_id: int
    explanation: str
    source: str
