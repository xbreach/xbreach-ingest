import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class LocalStorageError(Exception):
    pass


class LocalStorageOverwriteError(LocalStorageError):
    pass


@dataclass(frozen=True)
class LocalStoredFile:
    original_filename: str
    stored_filename: str
    absolute_path: Path
    relative_path: Path
    manifest_path: Path
    checksum_sha256: str
    file_size_bytes: int


class LocalStorage:
    def __init__(self, root_path: Path) -> None:
        self._root_path = root_path

    def save(
        self,
        *,
        job_id: int,
        original_filename: str,
        source_path: Path,
        checksum_sha256: str,
        file_size_bytes: int,
        collected_date: date,
    ) -> LocalStoredFile:
        suffix = Path(original_filename).suffix.lower()
        stored_filename = f"original{suffix}"
        relative_dir = (
            Path("raw")
            / f"year={collected_date.year:04d}"
            / f"month={collected_date.month:02d}"
            / f"day={collected_date.day:02d}"
            / str(job_id)
        )
        absolute_dir = self._root_path / relative_dir
        relative_path = relative_dir / stored_filename
        absolute_path = self._root_path / relative_path
        manifest_path = absolute_dir / "manifest.json"

        try:
            absolute_dir.mkdir(parents=True, exist_ok=False)
            self._copy_without_overwrite(source_path, absolute_path)
            self._write_manifest(
                manifest_path=manifest_path,
                job_id=job_id,
                checksum_sha256=checksum_sha256,
                filename=original_filename,
                size=file_size_bytes,
            )
        except FileExistsError as exc:
            raise LocalStorageOverwriteError("storage path already exists") from exc
        except OSError as exc:
            shutil.rmtree(absolute_dir, ignore_errors=True)
            raise LocalStorageError("failed to write file to local storage") from exc

        return LocalStoredFile(
            original_filename=original_filename,
            stored_filename=stored_filename,
            absolute_path=absolute_path,
            relative_path=relative_path,
            manifest_path=manifest_path,
            checksum_sha256=checksum_sha256,
            file_size_bytes=file_size_bytes,
        )

    def remove_job_directory(self, relative_path: Path) -> None:
        job_directory = self._root_path / relative_path.parent
        shutil.rmtree(job_directory, ignore_errors=True)

    @staticmethod
    def _copy_without_overwrite(source_path: Path, destination_path: Path) -> None:
        with (
            source_path.open("rb") as source,
            destination_path.open("xb") as destination,
        ):
            shutil.copyfileobj(source, destination)

    @staticmethod
    def _write_manifest(
        *,
        manifest_path: Path,
        job_id: int,
        checksum_sha256: str,
        filename: str,
        size: int,
    ) -> None:
        manifest = {
            "job_id": job_id,
            "checksum": checksum_sha256,
            "filename": filename,
            "size": size,
        }
        with manifest_path.open("x", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, sort_keys=True)
            manifest_file.write("\n")
