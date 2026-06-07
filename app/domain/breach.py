from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Breach:
    id: int
    source_id: int
    name: str
    description: str | None
    collected_at: datetime | None
    created_at: datetime
