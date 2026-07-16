"""Pinned, content-addressed resolver for public GDPval artifacts.

The public GDPval table declares repository-relative paths such as
``reference_files/<id>/input.xlsx`` and
``deliverable_files/<id>/answer.docx``.  This module turns one such declaration
into a stable local file without allowing callers to select another dataset,
an unpinned branch, or an arbitrary URL.

Network access is never an import or construction side effect.  ``resolve`` is
cache-only by default; callers must explicitly pass ``allow_download=True`` or
call ``fetch``.  A successful first fetch is streamed through a byte budget,
hashed, stored under its SHA-256, and bound to the declared path by an atomic
receipt.  Every cache hit re-hashes the object before returning it.

This is an artifact identity/staging primitive, not an Office parser.  Checkers
should pass ``materialized_path`` to a bounded parser and carry ``to_evidence``
into their replay receipt.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import stat
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Mapping


GDPVAL_DATASET_ID = "openai/gdpval"
GDPVAL_RESOLVER_SCHEMA_VERSION = "benchcore-gdpval-artifact-resolver-v2"
GDPVAL_RECEIPT_SCHEMA_VERSION = "benchcore-gdpval-artifact-receipt-v1"

_PINNED_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_TOP_LEVEL = frozenset({"reference_files", "deliverable_files"})
_MAX_DECLARED_PATH_CHARS = 2_048
_MAX_SEGMENT_UTF8_BYTES = 255
_COPY_CHUNK_BYTES = 1024 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024
_AUTHENTICITY_CALLER_DIGEST = "verified_against_caller_supplied_digest"
_AUTHENTICITY_NO_EXTERNAL_DIGEST = "unverified_without_external_digest"


class GDPvalArtifactError(RuntimeError):
    """Base class for fail-closed GDPval artifact resolution errors."""


class GDPvalPathError(GDPvalArtifactError, ValueError):
    """A dataset-declared artifact path is outside the accepted namespace."""


class GDPvalArtifactNotCached(GDPvalArtifactError, FileNotFoundError):
    """The caller requested cache-only resolution for an unseen artifact."""


class GDPvalDownloadError(GDPvalArtifactError):
    """The pinned Hugging Face object could not be downloaded safely."""


class GDPvalIntegrityError(GDPvalArtifactError):
    """Downloaded or cached bytes do not match their immutable receipt."""


class GDPvalBudgetExceeded(GDPvalArtifactError):
    """An artifact exceeded the configured per-file byte budget."""


@dataclass(frozen=True)
class GDPvalResolvedArtifact:
    """A cache-bound object plus an extension-preserving parser view.

    ``authenticity`` distinguishes content verified against a caller-supplied
    digest from a first fetch that is only internally self-consistent.  The
    resolver deliberately makes no claim about the provenance of that caller
    digest, and a pinned repository revision is not itself a byte digest.
    """

    dataset_id: str
    revision: str
    declared_path: str
    sha256: str
    size_bytes: int
    object_path: Path
    materialized_path: Path
    receipt_path: Path
    source_url: str
    from_cache: bool
    authenticity: str

    def to_evidence(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("object_path", "materialized_path", "receipt_path"):
            payload[key] = str(payload[key])
        payload["resolver_schema_version"] = GDPVAL_RESOLVER_SCHEMA_VERSION
        return payload


def validate_pinned_revision(revision: str) -> str:
    """Accept only an immutable, lowercase 40-hex Hugging Face commit ID."""

    if not isinstance(revision, str) or not _PINNED_REVISION.fullmatch(revision):
        raise ValueError(
            "GDPval revision must be an immutable lowercase 40-hex commit; "
            "branches, tags, and 'main' are forbidden"
        )
    return revision


def validate_declared_path(value: str) -> str:
    """Return a canonical GDPval repository-relative artifact path."""

    if not isinstance(value, str):
        raise GDPvalPathError("GDPval artifact path must be a string")
    if not value or len(value) > _MAX_DECLARED_PATH_CHARS:
        raise GDPvalPathError("GDPval artifact path is empty or too long")
    if value != unicodedata.normalize("NFC", value):
        raise GDPvalPathError("GDPval artifact path must use NFC Unicode")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise GDPvalPathError("GDPval artifact path contains a control character")
    if "\\" in value or "\x00" in value:
        raise GDPvalPathError("GDPval artifact path must use safe POSIX separators")
    if urllib.parse.urlsplit(value).scheme or value.startswith(("/", "~")):
        raise GDPvalPathError("GDPval artifact path must be relative, not a URL or absolute path")
    if "//" in value or value.endswith("/"):
        raise GDPvalPathError("GDPval artifact path is not canonical")

    path = PurePosixPath(value)
    parts = path.parts
    if len(parts) < 3 or parts[0] not in _ALLOWED_TOP_LEVEL:
        raise GDPvalPathError(
            "GDPval artifact path must live below reference_files/ or deliverable_files/"
        )
    if any(part in {"", ".", ".."} for part in parts):
        raise GDPvalPathError("GDPval artifact path contains traversal or empty segments")
    if path.as_posix() != value:
        raise GDPvalPathError("GDPval artifact path is not in canonical POSIX form")
    for part in parts:
        if len(part.encode("utf-8")) > _MAX_SEGMENT_UTF8_BYTES:
            raise GDPvalPathError("GDPval artifact path segment exceeds 255 UTF-8 bytes")
        if ":" in part:
            raise GDPvalPathError("GDPval artifact path contains a platform-ambiguous colon")
    return value


def _validate_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("expected_sha256 must be a lowercase 64-hex digest")
    return value


class GDPvalArtifactResolver:
    """Resolve only pinned ``openai/gdpval`` artifact declarations.

    Args:
        cache_dir: Private local cache root.  It must not be a symlink.
        revision: Immutable Hugging Face dataset commit (40 lowercase hex).
        max_file_bytes: Hard limit applied while streaming and on every cache hit.
        timeout_seconds: Total wall-clock deadline for an explicit download.
    """

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        revision: str,
        max_file_bytes: int = 128 * 1024 * 1024,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not isinstance(max_file_bytes, int) or isinstance(max_file_bytes, bool):
            raise ValueError("max_file_bytes must be an integer")
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.revision = validate_pinned_revision(revision)
        self.max_file_bytes = max_file_bytes
        self.timeout_seconds = float(timeout_seconds)
        lexical_cache = Path(cache_dir).expanduser()
        if lexical_cache.is_symlink():
            raise GDPvalIntegrityError("GDPval cache root must not be a symlink")
        self.cache_dir = lexical_cache.resolve(strict=False)
        self._ensure_cache_root()

    def resolve(
        self,
        declared_path: str,
        *,
        expected_sha256: str | None = None,
        allow_download: bool = False,
    ) -> GDPvalResolvedArtifact:
        """Resolve a declared path, remaining offline unless explicitly allowed."""

        canonical_path = validate_declared_path(declared_path)
        expected = _validate_sha256(expected_sha256)
        receipt_path = self._receipt_path(canonical_path)
        # lexists keeps dangling symlinks on the fail-closed receipt path; the
        # fd-based reader below will reject them with O_NOFOLLOW.
        if os.path.lexists(receipt_path):
            return self._resolve_receipt(
                canonical_path,
                receipt_path,
                expected_sha256=expected,
                from_cache=True,
            )
        if not allow_download:
            raise GDPvalArtifactNotCached(
                f"GDPval artifact is not cached; explicitly call fetch() or set "
                f"allow_download=True: {canonical_path!r}"
            )
        return self._download_and_bind(canonical_path, expected_sha256=expected)

    def fetch(
        self,
        declared_path: str,
        *,
        expected_sha256: str | None = None,
    ) -> GDPvalResolvedArtifact:
        """Explicitly permit one pinned GDPval artifact download."""

        return self.resolve(
            declared_path,
            expected_sha256=expected_sha256,
            allow_download=True,
        )

    def _ensure_cache_root(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.cache_dir.is_symlink() or not self.cache_dir.is_dir():
            raise GDPvalIntegrityError("GDPval cache root must be a real directory")
        os.chmod(self.cache_dir, 0o700)
        for name in ("objects", "receipts", "views", "tmp"):
            path = self.cache_dir / name
            path.mkdir(mode=0o700, exist_ok=True)
            if path.is_symlink() or not path.is_dir():
                raise GDPvalIntegrityError(f"GDPval cache component is unsafe: {name}")

    def _source_url(self, declared_path: str) -> str:
        encoded = urllib.parse.quote(declared_path, safe="/")
        return (
            "https://huggingface.co/datasets/openai/gdpval/resolve/"
            f"{self.revision}/{encoded}"
        )

    def _receipt_path(self, declared_path: str) -> Path:
        path_key = hashlib.sha256(declared_path.encode("utf-8")).hexdigest()
        return self.cache_dir / "receipts" / self.revision / f"{path_key}.json"

    def _object_path(self, digest: str) -> Path:
        return self.cache_dir / "objects" / "sha256" / digest[:2] / digest

    def _view_path(self, declared_path: str, digest: str) -> Path:
        path_key = hashlib.sha256(declared_path.encode("utf-8")).hexdigest()
        suffix = PurePosixPath(declared_path).suffix.lower()
        suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix) else ""
        return self.cache_dir / "views" / self.revision / path_key / f"artifact{suffix}"

    def _download_and_bind(
        self,
        declared_path: str,
        *,
        expected_sha256: str | None,
    ) -> GDPvalResolvedArtifact:
        source_url = self._source_url(declared_path)
        tmp_dir = self.cache_dir / "tmp"
        descriptor, temporary_name = tempfile.mkstemp(prefix="download-", dir=tmp_dir)
        temporary = Path(temporary_name)
        try:
            final_url = _download_pinned_file(
                source_url,
                descriptor,
                max_file_bytes=self.max_file_bytes,
                timeout_seconds=self.timeout_seconds,
            )
            digest, size = _hash_regular_descriptor(
                descriptor,
                max_file_bytes=self.max_file_bytes,
                error_subject="GDPval download staging file",
            )
            if expected_sha256 is not None and digest != expected_sha256:
                raise GDPvalIntegrityError(
                    "downloaded GDPval artifact does not match expected SHA-256"
                )
            object_path = self._install_object(temporary, descriptor, digest, size)
            receipt_path = self._receipt_path(declared_path)
            receipt = {
                "schema_version": GDPVAL_RECEIPT_SCHEMA_VERSION,
                "dataset_id": GDPVAL_DATASET_ID,
                "revision": self.revision,
                "declared_path": declared_path,
                "sha256": digest,
                "size_bytes": size,
                "source_url": source_url,
                # Redirect URLs commonly contain short-lived signed query
                # credentials.  Persist only the validated destination host.
                "final_host": urllib.parse.urlsplit(final_url).hostname,
            }
            _atomic_write_json(receipt_path, receipt)
            return self._resolve_receipt(
                declared_path,
                receipt_path,
                expected_sha256=expected_sha256,
                from_cache=False,
            )
        finally:
            try:
                temporary.unlink(missing_ok=True)
            finally:
                os.close(descriptor)

    def _install_object(
        self,
        temporary: Path,
        temporary_descriptor: int,
        digest: str,
        size: int,
    ) -> Path:
        object_path = self._object_path(digest)
        object_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if object_path.exists():
            observed_digest, observed_size = _hash_regular_file(
                object_path,
                max_file_bytes=self.max_file_bytes,
            )
            if observed_digest != digest or observed_size != size:
                raise GDPvalIntegrityError("content-addressed GDPval cache object is corrupt")
            return object_path
        _require_path_matches_descriptor(
            temporary,
            temporary_descriptor,
            subject="GDPval download staging file",
        )
        try:
            os.link(temporary, object_path, follow_symlinks=False)
        except FileExistsError:
            pass
        # The pathname source can be exchanged between the identity check and
        # link(2).  Re-opening and hashing the committed name is therefore part
        # of the commit protocol, not merely a cache-health check.
        observed_digest, observed_size = _hash_regular_file(
            object_path,
            max_file_bytes=self.max_file_bytes,
        )
        if observed_digest != digest or observed_size != size:
            raise GDPvalIntegrityError("racing GDPval cache object has wrong content")
        _chmod_regular_file(object_path, 0o400, subject="GDPval cache object")
        _fsync_directory(object_path.parent)
        observed_digest, observed_size = _hash_regular_file(
            object_path,
            max_file_bytes=self.max_file_bytes,
        )
        if observed_digest != digest or observed_size != size:
            raise GDPvalIntegrityError("committed GDPval cache object changed during binding")
        return object_path

    def _resolve_receipt(
        self,
        declared_path: str,
        receipt_path: Path,
        *,
        expected_sha256: str | None,
        from_cache: bool,
    ) -> GDPvalResolvedArtifact:
        receipt = _read_receipt(receipt_path)
        required = {
            "schema_version",
            "dataset_id",
            "revision",
            "declared_path",
            "sha256",
            "size_bytes",
            "source_url",
            "final_host",
        }
        if set(receipt) != required:
            raise GDPvalIntegrityError("GDPval artifact receipt has an invalid field set")
        if (
            receipt["schema_version"] != GDPVAL_RECEIPT_SCHEMA_VERSION
            or receipt["dataset_id"] != GDPVAL_DATASET_ID
            or receipt["revision"] != self.revision
            or receipt["declared_path"] != declared_path
            or receipt["source_url"] != self._source_url(declared_path)
            or not isinstance(receipt["final_host"], str)
            or not _is_allowed_hf_host(receipt["final_host"])
        ):
            raise GDPvalIntegrityError("GDPval artifact receipt identity mismatch")
        digest = _validate_sha256(receipt.get("sha256"))
        if digest is None:
            raise GDPvalIntegrityError("GDPval artifact receipt has no digest")
        size = receipt.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise GDPvalIntegrityError("GDPval artifact receipt has an invalid size")
        if size > self.max_file_bytes:
            raise GDPvalBudgetExceeded("cached GDPval artifact exceeds current byte budget")
        if expected_sha256 is not None and digest != expected_sha256:
            raise GDPvalIntegrityError("cached GDPval artifact does not match expected SHA-256")
        object_path = self._object_path(digest)
        observed_digest, observed_size = _hash_regular_file(
            object_path,
            max_file_bytes=self.max_file_bytes,
        )
        if observed_digest != digest or observed_size != size:
            raise GDPvalIntegrityError("cached GDPval artifact bytes differ from receipt")
        materialized = self._ensure_view(declared_path, object_path, digest, size)
        # Bind both public paths to the receipt after materialization.  In
        # particular, this detects a replacement of object_path in the window
        # between its first verification and the hard-link operation.
        _require_file_identity(
            object_path,
            digest=digest,
            size=size,
            max_file_bytes=self.max_file_bytes,
            subject="GDPval cache object",
        )
        _require_file_identity(
            materialized,
            digest=digest,
            size=size,
            max_file_bytes=self.max_file_bytes,
            subject="GDPval parser view",
        )
        return GDPvalResolvedArtifact(
            dataset_id=GDPVAL_DATASET_ID,
            revision=self.revision,
            declared_path=declared_path,
            sha256=digest,
            size_bytes=size,
            object_path=object_path,
            materialized_path=materialized,
            receipt_path=receipt_path,
            source_url=str(receipt["source_url"]),
            from_cache=from_cache,
            authenticity=(
                _AUTHENTICITY_CALLER_DIGEST
                if expected_sha256 is not None
                else _AUTHENTICITY_NO_EXTERNAL_DIGEST
            ),
        )

    def _ensure_view(
        self,
        declared_path: str,
        object_path: Path,
        digest: str,
        size: int,
    ) -> Path:
        view = self._view_path(declared_path, digest)
        view.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if view.exists():
            _require_file_identity(
                view,
                digest=digest,
                size=size,
                max_file_bytes=self.max_file_bytes,
                subject="GDPval parser view",
            )
            return view
        try:
            os.link(object_path, view, follow_symlinks=False)
        except FileExistsError:
            pass
        # Always verify after link(2), including the uncontended success path.
        # Hashing through an O_NOFOLLOW descriptor also proves this is a
        # regular file rather than a symlink swapped in during materialization.
        _require_file_identity(
            view,
            digest=digest,
            size=size,
            max_file_bytes=self.max_file_bytes,
            subject="GDPval parser view",
        )
        _fsync_directory(view.parent)
        return view


class _PinnedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: BinaryIO,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_https_hf_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_pinned_file(
    source_url: str,
    destination_descriptor: int,
    *,
    max_file_bytes: int,
    timeout_seconds: float,
) -> str:
    """Stream one fixed GDPval URL into an already-open private temp file.

    ``timeout_seconds`` is an end-to-end monotonic deadline.  Body reads use
    ``HTTPResponse.read1`` (one underlying buffered read) and reset the socket
    timeout to the remaining budget before every read.  This prevents a peer
    that sends one byte just inside a fixed idle timeout from extending the
    transfer indefinitely.
    """

    deadline = time.monotonic() + timeout_seconds
    _validate_https_hf_url(source_url)
    _remaining_download_time(deadline)
    _prepare_download_descriptor(destination_descriptor)
    opener = urllib.request.build_opener(_PinnedRedirectHandler())
    request = urllib.request.Request(
        source_url,
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "BenchCore-GDPval-ArtifactResolver/1.0",
        },
        method="GET",
    )
    try:
        response = opener.open(request, timeout=_remaining_download_time(deadline))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        if time.monotonic() >= deadline:
            raise GDPvalDownloadError(
                "GDPval artifact download exceeded its total wall-clock deadline"
            ) from exc
        raise GDPvalDownloadError(
            f"pinned GDPval artifact download failed: {type(exc).__name__}"
        ) from exc
    try:
        _remaining_download_time(deadline)
        final_url = response.geturl()
        _validate_https_hf_url(final_url)
        _remaining_download_time(deadline)
        status = getattr(response, "status", 200)
        if status != 200:
            raise GDPvalDownloadError(f"GDPval artifact server returned HTTP {status}")
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise GDPvalDownloadError("artifact Content-Length is invalid") from exc
            if declared_length < 0:
                raise GDPvalDownloadError("artifact Content-Length is negative")
            if declared_length > max_file_bytes:
                raise GDPvalBudgetExceeded(
                    "GDPval artifact exceeds byte budget before download"
                )
        copied = 0
        while True:
            remaining = _remaining_download_time(deadline)
            _set_response_socket_timeout(response, remaining)
            reader = getattr(response, "read1", None)
            if not callable(reader):
                raise GDPvalDownloadError(
                    "HTTP response cannot provide deadline-safe streaming"
                )
            try:
                chunk = reader(min(_COPY_CHUNK_BYTES, max_file_bytes - copied + 1))
            except (TimeoutError, socket.timeout) as exc:
                if time.monotonic() >= deadline:
                    raise GDPvalDownloadError(
                        "GDPval artifact download exceeded its total wall-clock deadline"
                    ) from exc
                raise GDPvalDownloadError("GDPval artifact body read timed out") from exc
            except OSError as exc:
                raise GDPvalDownloadError("GDPval artifact body read failed") from exc
            _remaining_download_time(deadline)
            if not chunk:
                break
            copied += len(chunk)
            if copied > max_file_bytes:
                raise GDPvalBudgetExceeded(
                    "GDPval artifact exceeded byte budget while streaming"
                )
            _write_all(
                destination_descriptor,
                chunk,
                subject="GDPval download staging file",
            )
        os.fsync(destination_descriptor)
        _remaining_download_time(deadline)
        if content_length is not None and copied != int(content_length):
            raise GDPvalDownloadError("artifact body length differs from Content-Length")
        return final_url
    finally:
        response.close()


def _remaining_download_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GDPvalDownloadError(
            "GDPval artifact download exceeded its total wall-clock deadline"
        )
    return remaining


def _prepare_download_descriptor(descriptor: int) -> None:
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise GDPvalIntegrityError("GDPval download staging file is not regular")
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except OSError as exc:
        raise GDPvalIntegrityError(
            "GDPval download staging descriptor is unusable"
        ) from exc


def _set_response_socket_timeout(response: Any, remaining: float) -> None:
    """Apply the shrinking total-deadline budget to urllib's live socket."""

    stream = getattr(response, "fp", None)
    raw = getattr(stream, "raw", None)
    network_socket = getattr(raw, "_sock", None)
    setter = getattr(network_socket, "settimeout", None)
    if not callable(setter):
        raise GDPvalDownloadError(
            "HTTP response socket is unavailable for deadline enforcement"
        )
    try:
        setter(remaining)
    except OSError as exc:
        raise GDPvalDownloadError(
            "HTTP response socket rejected deadline enforcement"
        ) from exc


def _write_all(descriptor: int, payload: bytes, *, subject: str) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(descriptor, view)
        except OSError as exc:
            raise GDPvalIntegrityError(f"{subject} write failed") from exc
        if written <= 0:
            raise GDPvalIntegrityError(f"{subject} write made no progress")
        view = view[written:]


def _validate_https_hf_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise GDPvalDownloadError("artifact URL must be credential-free HTTPS on port 443")
    host = parsed.hostname.rstrip(".").lower()
    if not _is_allowed_hf_host(host):
        raise GDPvalDownloadError(f"artifact redirect host is not allowlisted: {host}")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise GDPvalDownloadError("artifact host DNS resolution failed") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise GDPvalDownloadError("artifact host resolved to a non-public address")


def _is_allowed_hf_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    return bool(
        normalized == "huggingface.co"
        or normalized.endswith(".huggingface.co")
        or normalized == "hf.co"
        or normalized.endswith(".hf.co")
        or normalized == "xethub.hf.co"
        or normalized.endswith(".xethub.hf.co")
    )


def _hash_regular_file(
    path: Path,
    *,
    max_file_bytes: int,
    error_subject: str = "GDPval cache object",
) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GDPvalIntegrityError(f"{error_subject} cannot be opened safely") from exc
    try:
        return _hash_regular_descriptor(
            descriptor,
            max_file_bytes=max_file_bytes,
            error_subject=error_subject,
        )
    finally:
        os.close(descriptor)


def _hash_regular_descriptor(
    descriptor: int,
    *,
    max_file_bytes: int,
    error_subject: str,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        metadata_before = os.fstat(descriptor)
        if not stat.S_ISREG(metadata_before.st_mode):
            raise GDPvalIntegrityError(f"{error_subject} is not a regular file")
        if metadata_before.st_size > max_file_bytes:
            raise GDPvalBudgetExceeded("GDPval artifact exceeds configured byte budget")
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            block = os.read(
                descriptor,
                min(_COPY_CHUNK_BYTES, max_file_bytes - size + 1),
            )
            if not block:
                break
            size += len(block)
            if size > max_file_bytes:
                raise GDPvalBudgetExceeded("GDPval artifact grew beyond byte budget")
            digest.update(block)
        metadata_after = os.fstat(descriptor)
    except OSError as exc:
        raise GDPvalIntegrityError(f"{error_subject} cannot be read safely") from exc
    if (
        metadata_after.st_dev != metadata_before.st_dev
        or metadata_after.st_ino != metadata_before.st_ino
        or metadata_after.st_size != metadata_before.st_size
        or metadata_after.st_mtime_ns != metadata_before.st_mtime_ns
        or metadata_after.st_size != size
    ):
        raise GDPvalIntegrityError(f"{error_subject} changed while it was being hashed")
    return digest.hexdigest(), size


def _require_path_matches_descriptor(path: Path, descriptor: int, *, subject: str) -> None:
    try:
        path_metadata = os.lstat(path)
        descriptor_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise GDPvalIntegrityError(f"{subject} identity cannot be verified") from exc
    if (
        not stat.S_ISREG(path_metadata.st_mode)
        or not stat.S_ISREG(descriptor_metadata.st_mode)
        or path_metadata.st_dev != descriptor_metadata.st_dev
        or path_metadata.st_ino != descriptor_metadata.st_ino
    ):
        raise GDPvalIntegrityError(f"{subject} pathname changed during download")


def _require_file_identity(
    path: Path,
    *,
    digest: str,
    size: int,
    max_file_bytes: int,
    subject: str,
) -> None:
    observed_digest, observed_size = _hash_regular_file(
        path,
        max_file_bytes=max_file_bytes,
        error_subject=subject,
    )
    if observed_digest != digest or observed_size != size:
        raise GDPvalIntegrityError(f"{subject} is not bound to the receipt digest")


def _chmod_regular_file(path: Path, mode: int, *, subject: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GDPvalIntegrityError(f"{subject} cannot be opened for permission binding") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise GDPvalIntegrityError(f"{subject} is not a regular file")
        os.fchmod(descriptor, mode)
    except OSError as exc:
        raise GDPvalIntegrityError(f"{subject} permissions cannot be bound") from exc
    finally:
        os.close(descriptor)


def _read_receipt(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GDPvalIntegrityError(
            "GDPval artifact receipt cannot be opened without following links"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise GDPvalIntegrityError("GDPval artifact receipt is not a regular file")
        if metadata.st_size > _MAX_RECEIPT_BYTES:
            raise GDPvalIntegrityError("GDPval artifact receipt exceeds 64 KiB")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(8 * 1024, _MAX_RECEIPT_BYTES - total + 1))
            if not block:
                break
            total += len(block)
            if total > _MAX_RECEIPT_BYTES:
                raise GDPvalIntegrityError("GDPval artifact receipt exceeds 64 KiB")
            chunks.append(block)
        metadata_after = os.fstat(descriptor)
        if (
            metadata_after.st_dev != metadata.st_dev
            or metadata_after.st_ino != metadata.st_ino
            or metadata_after.st_size != metadata.st_size
            or metadata_after.st_mtime_ns != metadata.st_mtime_ns
            or metadata_after.st_ctime_ns != metadata.st_ctime_ns
            or metadata_after.st_size != total
        ):
            raise GDPvalIntegrityError("GDPval artifact receipt changed while being read")
        raw_payload = b"".join(chunks)
    except OSError as exc:
        raise GDPvalIntegrityError("GDPval artifact receipt is unreadable") from exc
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GDPvalIntegrityError("GDPval artifact receipt is unreadable") from exc
    if not isinstance(payload, dict):
        raise GDPvalIntegrityError("GDPval artifact receipt must be a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = text.encode("utf-8")
    if len(encoded) > _MAX_RECEIPT_BYTES:
        raise GDPvalIntegrityError("GDPval artifact receipt exceeds 64 KiB")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        _write_all(descriptor, encoded, subject="GDPval receipt staging file")
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        _require_path_matches_descriptor(
            temporary,
            descriptor,
            subject="GDPval receipt staging file",
        )
        try:
            # Receipts are immutable path-to-content bindings.  Hard-link
            # creation is atomic and, unlike replace(), cannot silently rewrite
            # an identity that another process already committed.
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            existing = _read_receipt(path)
            if existing != dict(payload):
                raise GDPvalIntegrityError(
                    "GDPval artifact path already has a different immutable receipt"
                )
        committed = _read_receipt(path)
        if committed != dict(payload):
            raise GDPvalIntegrityError(
                "committed GDPval artifact receipt differs from staged identity"
            )
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
