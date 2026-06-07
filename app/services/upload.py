import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.domain.snowflake import SnowflakeGenerator
from app.repositories.breaches import BreachRepository
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.repositories.sources import SourceRepository
from app.schemas.breach import CreateBreach
from app.schemas.ingestion_job import CreateIngestionJob
from app.services.sources import InvalidApiKeyError, SourceService

ALLOWED_UPLOAD_SUFFIXES = {".txt", ".csv", ".gz", ".zst"}


@dataclass(frozen=True)
class UploadValidationError(Exception):
    message: str
    status_code: int


class InvalidUploadExtensionError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("file extension is not allowed", 400)


class EmptyUploadFileError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("uploaded file is empty", 400)


class SourceMismatchError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("invalid API key", 401)


class UploadIngestService:
    def __init__(
        self,
        source_repository: SourceRepository,
        breach_repository: BreachRepository,
        job_repository: IngestionJobRepository,
        id_generator: Callable[[], int] | None = None,
        storage_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self._source_service = SourceService(source_repository)
        self._breach_repository = breach_repository
        self._job_repository = job_repository
        self._id_generator = id_generator or SnowflakeGenerator(
            app_id=settings.app_id,
            node_id=settings.node_id,
        ).next_id
        self._storage_path = storage_path or Path(settings.data_path) / "storage"

    def upload(
        self,
        *,
        file: UploadFile,
        source_id: int,
        breach_name: str,
        collected_at: datetime | None,
        api_key: str,
    ) -> int:
        self._validate_extension(file.filename)

        api_key_hash = self._hash_api_key(api_key)
        source = self._source_service.authenticate_by_api_key_hash(api_key_hash)
        if source.id != source_id:
            raise SourceMismatchError()

        saved_file = self._save_file(file)
        breach_id = self._id_generator()
        job_id = self._id_generator()

        breach = self._breach_repository.create_breach(
            CreateBreach(
                id=breach_id,
                source_id=source_id,
                name=breach_name,
                collected_at=collected_at,
            )
        )
        self._job_repository.create_job(
            CreateIngestionJob(
                id=job_id,
                source_id=source_id,
                breach_id=breach.id,
                original_filename=saved_file.original_filename,
                stored_filename=saved_file.stored_filename,
                local_path=str(saved_file.local_path),
                checksum_sha256=saved_file.checksum_sha256,
                file_size_bytes=saved_file.file_size_bytes,
            )
        )
        return job_id

    def _save_file(self, file: UploadFile):
        self._storage_path.mkdir(parents=True, exist_ok=True)
        original_filename = Path(file.filename or "").name
        stored_filename = f"{uuid4().hex}{Path(original_filename).suffix.lower()}"
        local_path = self._storage_path / stored_filename
        checksum = hashlib.sha256()
        file_size_bytes = 0

        with local_path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                file_size_bytes += len(chunk)
                checksum.update(chunk)
                output.write(chunk)

        if file_size_bytes == 0:
            local_path.unlink(missing_ok=True)
            raise EmptyUploadFileError()

        file.file.seek(0)
        return SavedUploadFile(
            original_filename=original_filename,
            stored_filename=stored_filename,
            local_path=local_path,
            checksum_sha256=checksum.hexdigest(),
            file_size_bytes=file_size_bytes,
        )

    @staticmethod
    def _validate_extension(filename: str | None) -> None:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise InvalidUploadExtensionError()

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        if not api_key:
            raise InvalidApiKeyError()
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SavedUploadFile:
    original_filename: str
    stored_filename: str
    local_path: Path
    checksum_sha256: str
    file_size_bytes: int
