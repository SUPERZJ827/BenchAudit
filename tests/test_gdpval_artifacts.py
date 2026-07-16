import hashlib
import json
import os
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import benchcore.gdpval_artifacts as artifacts
from benchcore.gdpval_artifacts import (
    GDPvalArtifactNotCached,
    GDPvalArtifactResolver,
    GDPvalBudgetExceeded,
    GDPvalDownloadError,
    GDPvalIntegrityError,
    GDPvalPathError,
    validate_declared_path,
    validate_pinned_revision,
)


REVISION = "a" * 40
REFERENCE_PATH = "reference_files/0123456789abcdef0123456789abcdef/Input Data.xlsx"
DELIVERABLE_PATH = "deliverable_files/fedcba9876543210fedcba9876543210/Answer.docx"


def fake_downloader(payload: bytes, calls: list[str]):
    def download(
        source_url: str,
        destination_descriptor: int,
        *,
        max_file_bytes: int,
        timeout_seconds: float,
    ) -> str:
        del timeout_seconds
        calls.append(source_url)
        os.ftruncate(destination_descriptor, 0)
        os.lseek(destination_descriptor, 0, os.SEEK_SET)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(destination_descriptor, remaining)
            remaining = remaining[written:]
        return source_url

    return download


def test_revision_and_declared_path_validation_is_fail_closed():
    assert validate_pinned_revision(REVISION) == REVISION
    for unpinned in ("main", "refs/heads/main", "A" * 40, "a" * 39, "a" * 41):
        with pytest.raises(ValueError, match="immutable"):
            validate_pinned_revision(unpinned)

    assert validate_declared_path(REFERENCE_PATH) == REFERENCE_PATH
    assert validate_declared_path(
        "deliverable_files/0123456789abcdef0123456789abcdef/分析结果.xlsx"
    ).endswith("分析结果.xlsx")
    invalid = (
        "/reference_files/id/file.xlsx",
        "https://example.com/file.xlsx",
        "reference_files/../secret.xlsx",
        "reference_files/id/../../secret.xlsx",
        "reference_files\\id\\file.xlsx",
        "reference_files/id//file.xlsx",
        "other_files/id/file.xlsx",
        "reference_files/id/file.xlsx/",
        "reference_files/id/bad\x00name.xlsx",
    )
    for value in invalid:
        with pytest.raises(GDPvalPathError):
            validate_declared_path(value)


def test_resolver_is_offline_by_default(tmp_path: Path):
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(b"must not download", calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        with pytest.raises(GDPvalArtifactNotCached, match="explicitly"):
            resolver.resolve(REFERENCE_PATH)

    assert calls == []


def test_downloader_rejects_non_hf_and_private_network_destinations():
    for url in (
        "http://huggingface.co/datasets/openai/gdpval/file",
        "https://evil.example/file",
        "https://user:secret@huggingface.co/file",
        "https://huggingface.co:8443/file",
    ):
        with pytest.raises(GDPvalDownloadError):
            artifacts._validate_https_hf_url(url)

    private_answer = [
        (artifacts.socket.AF_INET, artifacts.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
    ]
    with patch.object(artifacts.socket, "getaddrinfo", return_value=private_answer):
        with pytest.raises(GDPvalDownloadError, match="non-public"):
            artifacts._validate_https_hf_url("https://huggingface.co/file")


def test_cache_root_symlink_is_refused(tmp_path: Path):
    real = tmp_path / "real-cache"
    real.mkdir()
    link = tmp_path / "cache-link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(GDPvalIntegrityError, match="must not be a symlink"):
        GDPvalArtifactResolver(link, revision=REVISION)


def test_explicit_fetch_creates_verified_content_addressed_cache(tmp_path: Path):
    payload = b"PK\x03\x04fake-but-stable-xlsx"
    digest = hashlib.sha256(payload).hexdigest()
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(payload, calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        fetched = resolver.fetch(REFERENCE_PATH, expected_sha256=digest)
        cached = resolver.resolve(REFERENCE_PATH, expected_sha256=digest)

    assert len(calls) == 1
    assert "%20" in calls[0]
    assert f"/openai/gdpval/resolve/{REVISION}/" in calls[0]
    assert fetched.from_cache is False
    assert cached.from_cache is True
    assert fetched.sha256 == cached.sha256 == digest
    assert fetched.object_path == cached.object_path
    assert fetched.object_path.name == digest
    assert fetched.materialized_path.suffix == ".xlsx"
    assert fetched.materialized_path.read_bytes() == payload
    assert fetched.object_path.stat().st_mode & 0o777 == 0o400
    receipt = json.loads(fetched.receipt_path.read_text(encoding="utf-8"))
    assert receipt["dataset_id"] == "openai/gdpval"
    assert receipt["revision"] == REVISION
    assert receipt["declared_path"] == REFERENCE_PATH
    assert receipt["sha256"] == digest
    assert cached.to_evidence()["resolver_schema_version"].endswith("-v2")
    assert (
        fetched.to_evidence()["authenticity"]
        == "verified_against_caller_supplied_digest"
    )
    assert cached.authenticity == "verified_against_caller_supplied_digest"


def test_identical_bytes_share_object_but_keep_parser_suffix_views(tmp_path: Path):
    payload = b"same bytes"
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(payload, calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        left = resolver.fetch(REFERENCE_PATH)
        right = resolver.fetch(DELIVERABLE_PATH)

    assert len(calls) == 2
    assert left.object_path == right.object_path
    assert left.materialized_path != right.materialized_path
    assert left.materialized_path.suffix == ".xlsx"
    assert right.materialized_path.suffix == ".docx"
    objects = [path for path in (tmp_path / "cache" / "objects").rglob("*") if path.is_file()]
    assert objects == [left.object_path]
    assert left.to_evidence()["authenticity"] == "unverified_without_external_digest"
    assert right.authenticity == "unverified_without_external_digest"


def test_expected_digest_and_byte_budget_are_enforced_before_binding(tmp_path: Path):
    calls: list[str] = []
    resolver = GDPvalArtifactResolver(
        tmp_path / "cache",
        revision=REVISION,
        max_file_bytes=4,
    )
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(b"five!", calls),
    ):
        with pytest.raises(GDPvalBudgetExceeded):
            resolver.fetch(REFERENCE_PATH)
    assert not resolver._receipt_path(REFERENCE_PATH).exists()

    resolver = GDPvalArtifactResolver(tmp_path / "other", revision=REVISION)
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(b"content", calls),
    ):
        with pytest.raises(GDPvalIntegrityError, match="expected SHA"):
            resolver.fetch(REFERENCE_PATH, expected_sha256="0" * 64)
    assert not resolver._receipt_path(REFERENCE_PATH).exists()


def test_every_cache_hit_rejects_object_tampering(tmp_path: Path):
    payload = b"trusted first fetch"
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(payload, calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        resolved = resolver.fetch(REFERENCE_PATH)
    resolved.object_path.chmod(0o600)
    resolved.object_path.write_bytes(b"tampered cache")

    with pytest.raises(GDPvalIntegrityError, match="differ from receipt"):
        resolver.resolve(REFERENCE_PATH)


def test_corrupt_receipt_fails_closed_without_redownload(tmp_path: Path):
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(b"content", calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        resolved = resolver.fetch(REFERENCE_PATH)
        resolved.receipt_path.write_text('{"sha256":"bad"}\n', encoding="utf-8")
        with pytest.raises(GDPvalIntegrityError, match="field set"):
            resolver.resolve(REFERENCE_PATH, allow_download=True)

    assert len(calls) == 1


def test_failed_download_leaves_no_receipt_or_temporary_payload(tmp_path: Path):
    resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=GDPvalDownloadError("synthetic failure"),
    ):
        with pytest.raises(GDPvalDownloadError):
            resolver.fetch(REFERENCE_PATH)

    assert not resolver._receipt_path(REFERENCE_PATH).exists()
    assert list((tmp_path / "cache" / "tmp").iterdir()) == []


def test_receipt_expected_digest_is_checked_before_return(tmp_path: Path):
    payload = b"content"
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(payload, calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        resolver.fetch(REFERENCE_PATH)

    with pytest.raises(GDPvalIntegrityError, match="expected SHA"):
        resolver.resolve(REFERENCE_PATH, expected_sha256="f" * 64)


def test_receipt_reader_rejects_symlinks_and_payloads_over_64_kib(tmp_path: Path):
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(b"content", calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "symlink-cache", revision=REVISION)
        resolved = resolver.fetch(REFERENCE_PATH)

    external_receipt = tmp_path / "external-receipt.json"
    external_receipt.write_bytes(resolved.receipt_path.read_bytes())
    resolved.receipt_path.unlink()
    resolved.receipt_path.symlink_to(external_receipt)
    with pytest.raises(GDPvalIntegrityError, match="without following links"):
        resolver.resolve(REFERENCE_PATH)

    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(b"content", calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "oversize-cache", revision=REVISION)
        resolved = resolver.fetch(REFERENCE_PATH)
    resolved.receipt_path.chmod(0o600)
    resolved.receipt_path.write_bytes(b"{" + b"x" * artifacts._MAX_RECEIPT_BYTES)
    with pytest.raises(GDPvalIntegrityError, match="exceeds 64 KiB"):
        resolver.resolve(REFERENCE_PATH)


def test_download_keeps_private_temp_fd_and_rejects_path_exchange(tmp_path: Path):
    victim = tmp_path / "must-not-be-truncated.txt"
    victim.write_bytes(b"keep this payload")
    created_paths: list[Path] = []
    real_mkstemp = artifacts.tempfile.mkstemp

    def recording_mkstemp(*args, **kwargs):
        descriptor, name = real_mkstemp(*args, **kwargs)
        created_paths.append(Path(name))
        return descriptor, name

    def exchange_staging_path(
        source_url: str,
        destination_descriptor: int,
        *,
        max_file_bytes: int,
        timeout_seconds: float,
    ) -> str:
        del max_file_bytes, timeout_seconds
        staging_path = created_paths[0]
        staging_path.unlink()
        staging_path.symlink_to(victim)
        os.ftruncate(destination_descriptor, 0)
        os.lseek(destination_descriptor, 0, os.SEEK_SET)
        os.write(destination_descriptor, b"downloaded bytes")
        return source_url

    resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
    with (
        patch.object(artifacts.tempfile, "mkstemp", side_effect=recording_mkstemp),
        patch.object(
            artifacts,
            "_download_pinned_file",
            side_effect=exchange_staging_path,
        ),
        pytest.raises(GDPvalIntegrityError, match="pathname changed during download"),
    ):
        resolver.fetch(REFERENCE_PATH)

    assert victim.read_bytes() == b"keep this payload"
    assert not resolver._receipt_path(REFERENCE_PATH).exists()
    assert list((tmp_path / "cache" / "tmp").iterdir()) == []


def test_object_to_view_race_is_detected_on_successful_link_path(tmp_path: Path):
    payload = b"original verified bytes"
    calls: list[str] = []
    with patch.object(
        artifacts,
        "_download_pinned_file",
        side_effect=fake_downloader(payload, calls),
    ):
        resolver = GDPvalArtifactResolver(tmp_path / "cache", revision=REVISION)
        resolved = resolver.fetch(REFERENCE_PATH)

    resolved.materialized_path.unlink()
    real_link = os.link

    def exchange_before_link(source, destination, *args, **kwargs):
        if Path(destination) == resolved.materialized_path:
            Path(source).chmod(0o600)
            Path(source).write_bytes(b"changed between object hash and view link")
        return real_link(source, destination, *args, **kwargs)

    with (
        patch.object(artifacts.os, "link", side_effect=exchange_before_link),
        pytest.raises(GDPvalIntegrityError, match="parser view.*receipt digest"),
    ):
        resolver.resolve(REFERENCE_PATH)


def test_streaming_download_has_total_wall_clock_deadline(tmp_path: Path):
    class RecordingSocket:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def settimeout(self, timeout: float) -> None:
            self.timeouts.append(timeout)

    class DripResponse:
        status = 200
        headers: dict[str, str] = {}

        def __init__(self, url: str) -> None:
            self.url = url
            self.socket = RecordingSocket()
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=self.socket))
            self.read_calls = 0
            self.closed = False

        def geturl(self) -> str:
            return self.url

        def read1(self, _amount: int) -> bytes:
            self.read_calls += 1
            time.sleep(0.01)
            # A fixed per-read timeout would permit this peer to continue for
            # roughly one second.  The total deadline must stop it first.
            return b"x" if self.read_calls < 100 else b""

        def close(self) -> None:
            self.closed = True

    class FakeOpener:
        def __init__(self, response: DripResponse) -> None:
            self.response = response
            self.open_timeout: float | None = None

        def open(self, _request, *, timeout: float):
            self.open_timeout = timeout
            return self.response

    source_url = f"https://huggingface.co/datasets/openai/gdpval/resolve/{REVISION}/file"
    response = DripResponse(source_url)
    opener = FakeOpener(response)
    destination = tmp_path / "download.tmp"
    descriptor = os.open(destination, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    started = time.monotonic()
    try:
        with (
            patch.object(artifacts, "_validate_https_hf_url", return_value=None),
            patch.object(artifacts.urllib.request, "build_opener", return_value=opener),
            pytest.raises(GDPvalDownloadError, match="wall-clock deadline"),
        ):
            artifacts._download_pinned_file(
                source_url,
                descriptor,
                max_file_bytes=1_024,
                timeout_seconds=0.04,
            )
    finally:
        os.close(descriptor)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert response.read_calls < 20
    assert response.closed is True
    assert len(response.socket.timeouts) >= 2
    assert response.socket.timeouts[-1] < response.socket.timeouts[0]
