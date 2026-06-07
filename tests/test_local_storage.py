import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.infrastructure.local_storage import (
    LocalStorage,
    LocalStorageError,
    LocalStorageOverwriteError,
)


def test_local_storage_saves_file_in_partitioned_path_with_manifest(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "upload.tmp"
    source_path.write_bytes(b"content")
    checksum = hashlib.sha256(b"content").hexdigest()

    stored_file = LocalStorage(tmp_path / "data").save(
        job_id=4001,
        original_filename="input.txt",
        source_path=source_path,
        checksum_sha256=checksum,
        file_size_bytes=len(b"content"),
        collected_date=date(2026, 6, 6),
    )

    assert stored_file.relative_path == (
        Path("raw") / "year=2026" / "month=06" / "day=06" / "4001" / "original.txt"
    )
    assert stored_file.absolute_path.read_bytes() == b"content"
    manifest = json.loads(stored_file.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "job_id": 4001,
        "checksum": checksum,
        "filename": "input.txt",
        "size": len(b"content"),
    }


def test_local_storage_prevents_overwrite(tmp_path: Path) -> None:
    source_path = tmp_path / "upload.tmp"
    source_path.write_bytes(b"content")
    storage = LocalStorage(tmp_path / "data")

    storage.save(
        job_id=4001,
        original_filename="input.txt",
        source_path=source_path,
        checksum_sha256=hashlib.sha256(b"content").hexdigest(),
        file_size_bytes=len(b"content"),
        collected_date=date(2026, 6, 6),
    )

    with pytest.raises(LocalStorageOverwriteError):
        storage.save(
            job_id=4001,
            original_filename="input.txt",
            source_path=source_path,
            checksum_sha256=hashlib.sha256(b"content").hexdigest(),
            file_size_bytes=len(b"content"),
            collected_date=date(2026, 6, 6),
        )


def test_local_storage_wraps_disk_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "upload.tmp"
    source_path.write_bytes(b"content")

    def raise_disk_error(*args, **kwargs) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "open", raise_disk_error)

    with pytest.raises(LocalStorageError):
        LocalStorage(tmp_path / "data").save(
            job_id=4001,
            original_filename="input.txt",
            source_path=source_path,
            checksum_sha256=hashlib.sha256(b"content").hexdigest(),
            file_size_bytes=len(b"content"),
            collected_date=date(2026, 6, 6),
        )
