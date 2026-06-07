import hashlib
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.domain.snowflake import SnowflakeGenerator
from app.infrastructure.local_storage import LocalStorage, LocalStorageError
from app.repositories.breaches import BreachRepository
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.repositories.sources import SourceRepository
from app.schemas.breach import CreateBreach
from app.schemas.ingestion_job import CreateIngestionJob
from app.services.sources import InvalidApiKeyError, SourceService

ALLOWED_UPLOAD_SUFFIXES = {".txt", ".csv", ".gz", ".zst"}
ALLOWED_CONTENT_TYPES_BY_SUFFIX = {
    ".txt": {"text/plain", "application/octet-stream"},
    ".csv": {
        "text/csv",
        "application/vnd.ms-excel",
        "text/plain",
        "application/octet-stream",
    },
    ".gz": {"application/gzip", "application/x-gzip", "application/octet-stream"},
    ".zst": {"application/zstd", "application/octet-stream"},
}
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class UploadValidationError(Exception):
    message: str
    status_code: int


class InvalidUploadExtensionError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("file extension is not allowed", 400)


class InvalidUploadContentTypeError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("file content type is not allowed", 400)


class EmptyUploadFileError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("uploaded file is empty", 400)


class UploadFileTooLargeError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("uploaded file exceeds the maximum allowed size", 413)


class UnsafeUploadFilenameError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("uploaded filename is not safe", 400)


class SourceMismatchError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("invalid API key", 401)


class UploadStorageError(UploadValidationError):
    def __init__(self) -> None:
        super().__init__("failed to write file to local storage", 500)


@dataclass(frozen=True)
class UploadIngestResult:
    job_id: int
    file_path: str


class UploadIngestService:
    def __init__(
        self,
        source_repository: SourceRepository,
        breach_repository: BreachRepository,
        job_repository: IngestionJobRepository,
        id_generator: Callable[[], int] | None = None,
        storage_path: Path | None = None,
        max_file_size_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self._source_service = SourceService(source_repository)
        self._breach_repository = breach_repository
        self._job_repository = job_repository
        self._id_generator = id_generator or SnowflakeGenerator(
            app_id=settings.app_id,
            node_id=settings.node_id,
        ).next_id
        self._local_storage = LocalStorage(storage_path or Path(settings.data_path))
        self._max_file_size_bytes = (
            max_file_size_bytes
            if max_file_size_bytes is not None
            else settings.upload_max_file_size_bytes
        )

    def upload(
        self,
        *,
        file: UploadFile,
        source_id: int,
        breach_name: str,
        collected_at: datetime | None,
        api_key: str,
    ) -> UploadIngestResult:
        self._validate_extension(file.filename)
        self._validate_content_type(file.filename, file.content_type)

        api_key_hash = self._hash_api_key(api_key)
        source = self._source_service.authenticate_by_api_key_hash(api_key_hash)
        if source.id != source_id:
            raise SourceMismatchError()

        staged_file = self._stage_file(file)
        existing_job = self._job_repository.find_by_checksum_sha256(
            staged_file.checksum_sha256
        )
        if existing_job is not None:
            staged_file.temp_path.unlink(missing_ok=True)
            return UploadIngestResult(
                job_id=existing_job.id,
                file_path=existing_job.local_path,
            )

        breach_id = self._id_generator()
        job_id = self._id_generator()
        try:
            stored_file = self._local_storage.save(
                job_id=job_id,
                original_filename=staged_file.original_filename,
                source_path=staged_file.temp_path,
                checksum_sha256=staged_file.checksum_sha256,
                file_size_bytes=staged_file.file_size_bytes,
                collected_date=self._storage_date(collected_at),
            )
        except LocalStorageError as exc:
            raise UploadStorageError() from exc
        finally:
            staged_file.temp_path.unlink(missing_ok=True)

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
                original_filename=stored_file.original_filename,
                stored_filename=stored_file.stored_filename,
                local_path=stored_file.relative_path.as_posix(),
                checksum_sha256=stored_file.checksum_sha256,
                file_size_bytes=stored_file.file_size_bytes,
            )
        )
        return UploadIngestResult(
            job_id=job_id,
            file_path=stored_file.relative_path.as_posix(),
        )

    def _stage_file(self, file: UploadFile):
        original_filename = self._sanitize_filename(file.filename)
        checksum = hashlib.sha256()
        file_size_bytes = 0
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_path = Path(temp_file.name)

        try:
            with temp_file:
                while chunk := file.file.read(1024 * 1024):
                    file_size_bytes += len(chunk)
                    if file_size_bytes > self._max_file_size_bytes:
                        raise UploadFileTooLargeError()
                    checksum.update(chunk)
                    temp_file.write(chunk)
        except UploadValidationError:
            temp_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise UploadStorageError() from exc

        if file_size_bytes == 0:
            temp_path.unlink(missing_ok=True)
            raise EmptyUploadFileError()

        file.file.seek(0)
        return StagedUploadFile(
            original_filename=original_filename,
            temp_path=temp_path,
            checksum_sha256=checksum.hexdigest(),
            file_size_bytes=file_size_bytes,
        )

    @staticmethod
    def _validate_extension(filename: str | None) -> None:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise InvalidUploadExtensionError()

    @staticmethod
    def _validate_content_type(filename: str | None, content_type: str | None) -> None:
        suffix = Path(filename or "").suffix.lower()
        allowed_content_types = ALLOWED_CONTENT_TYPES_BY_SUFFIX.get(suffix, set())
        if content_type not in allowed_content_types:
            raise InvalidUploadContentTypeError()

    @staticmethod
    def _sanitize_filename(filename: str | None) -> str:
        if not filename:
            raise UnsafeUploadFilenameError()
        if "/" in filename or "\\" in filename:
            raise UnsafeUploadFilenameError()

        name = Path(filename).name.strip().strip(".")
        sanitized = SAFE_FILENAME_PATTERN.sub("_", name)
        if not sanitized or Path(sanitized).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
            raise UnsafeUploadFilenameError()
        return sanitized

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        if not api_key:
            raise InvalidApiKeyError()
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _storage_date(collected_at: datetime | None):
        if collected_at is None:
            return datetime.now(UTC).date()
        return collected_at.date()


@dataclass(frozen=True)
class StagedUploadFile:
    original_filename: str
    temp_path: Path
    checksum_sha256: str
    file_size_bytes: int
