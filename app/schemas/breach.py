from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateBreach(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    source_id: int
    name: str
    collected_at: datetime | None = None
    description: str | None = None
