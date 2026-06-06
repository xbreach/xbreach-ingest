from dataclasses import dataclass
from datetime import datetime

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class IngestionJob:
    id: int
    source_id: int
    breach_id: int | None
    original_filename: str
    stored_filename: str
    local_path: str
    checksum_sha256: str
    file_size_bytes: int
    status: str
    total_lines: int
    parsed_lines: int
    rejected_lines: int
    inserted_lines: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
