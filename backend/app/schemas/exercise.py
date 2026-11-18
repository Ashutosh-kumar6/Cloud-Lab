from typing import Literal

from pydantic import BaseModel, ConfigDict


class TestCaseCreate(BaseModel):
    input_text: str = ""
    expected_output: str
    is_hidden: bool = False


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    input_text: str
    expected_output: str


class ExerciseCreate(BaseModel):
    title: str
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    description: str
    test_cases: list[TestCaseCreate]


class ExerciseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    topic: str
    difficulty: str


class ExerciseDetail(ExerciseSummary):
    description: str
    sample_test_cases: list[TestCaseOut]
