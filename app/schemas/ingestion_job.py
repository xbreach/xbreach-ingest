from pydantic import BaseModel, ConfigDict


class CreateIngestionJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    source_id: int
    breach_id: int | None
    original_filename: str
    stored_filename: str
    local_path: str
    checksum_sha256: str
    file_size_bytes: int


class IngestionJobProgress(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_lines: int
    parsed_lines: int
    rejected_lines: int
    inserted_lines: int
