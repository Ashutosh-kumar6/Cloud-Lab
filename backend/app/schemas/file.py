from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int
    updated_at: datetime
