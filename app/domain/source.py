from dataclasses import dataclass
from datetime import datetime

SOURCE_STATUS_ACTIVE = "active"
SOURCE_STATUS_INACTIVE = "inactive"
SOURCE_STATUS_DISABLED = "disabled"


@dataclass(frozen=True)
class Source:
    id: int
    name: str
    type: str
    status: str
    api_key_hash: str
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.status == SOURCE_STATUS_ACTIVE
