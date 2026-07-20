"""Conservative static evidence checks for Harbor/Terminal benchmark tasks.

The checks in this module inspect one task version at a time.  They never read a
later, repaired version while producing findings; paired versions are used only
by experiment code to score whether independent audit signals localize known
repairs.

All findings are review signals.  Static source evidence can identify fragile
dependencies, tight resource envelopes, and over-specific verifier patterns,
but execution is required before promoting a benchmark defect to confirmed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    "",
    ".c",
    ".cpp",
    ".dockerfile",
    ".go",
    ".h",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".md",
    ".py",
    ".r",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

HEAVY_RESOURCE_MARKERS = {
    "browser": re.compile(r"\b(?:chrome|chromium|selenium|playwright)\b", re.I),
    "deep_learning": re.compile(
        r"\b(?:torch|pytorch|tensorflow|caffe|segment.?anything)\b", re.I
    ),
    "scientific_stack": re.compile(r"\b(?:mteb|rstan|pystan|cmdstan)\b", re.I),
    "virtual_machine": re.compile(r"\b(?:qemu|virtualbox|windows.?image)\b", re.I),
}


@dataclass(frozen=True)
class TerminalAuditFinding:
    task_id: str
    defect_type: str
    confidence: float
    severity: str
    message: str
    evidence: dict[str, object]
    confirmation: str = "review"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_terminal_task(task_dir: Path) -> list[dict[str, object]]:
    """Return bounded, deterministic review findings for one Harbor task."""

    task_id = task_dir.name
    files = read_task_text_files(task_dir)
    instruction = files.get("instruction.md", "")
    task_toml = files.get("task.toml", "")
    combined = "\n".join(files.values())
    findings: list[TerminalAuditFinding] = []

    findings.extend(_exact_system_package_pins(task_id, files))
    findings.extend(_runtime_network_dependencies(task_id, files))
    findings.extend(_resource_headroom(task_id, task_toml, combined))
    findings.extend(_overstrict_directory_tests(task_id, files))
    findings.extend(_implicit_input_immutability(task_id, instruction, files))
    findings.extend(_host_cpu_leakage(task_id, task_toml, files))
    return [finding.to_dict() for finding in _deduplicate(findings)]


def read_task_text_files(
    task_dir: Path, *, max_file_bytes: int = 2_000_000
) -> dict[str, str]:
    """Read audit-relevant text without following links or loading large assets."""

    rows: dict[str, str] = {}
    for path in sorted(task_dir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(task_dir).as_posix()
        if relative.startswith(".git/"):
            continue
        suffix = path.suffix.casefold()
        if path.name != "Dockerfile" and suffix not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
            rows[relative] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return rows


def parse_task_resources(task_toml: str) -> dict[str, float]:
    """Parse repeated Harbor scalar resources conservatively.

    ``task.toml`` may contain resource fields in more than one section.  For
    headroom auditing the smallest declared value is the relevant constraint.
    """

    result: dict[str, float] = {}
    for field in ("cpus", "memory_mb", "storage_mb"):
        values = [
            float(value)
            for value in re.findall(
                rf"^{re.escape(field)}\s*=\s*([0-9]+(?:\.[0-9]+)?)",
                task_toml,
                re.M,
            )
        ]
        if values:
            result[field] = min(values)
    timeouts = [
        float(value)
        for value in re.findall(
            r"^timeout_sec\s*=\s*([0-9]+(?:\.[0-9]+)?)", task_toml, re.M
        )
    ]
    if timeouts:
        result["timeout_sec"] = min(timeouts)
    return result


def _exact_system_package_pins(
    task_id: str, files: dict[str, str]
) -> list[TerminalAuditFinding]:
    findings: list[TerminalAuditFinding] = []
    for relative, original in files.items():
        if not (relative == "environment/Dockerfile" or relative.startswith("solution/")):
            continue
        text = original.replace("\\\n", " ")
        for command in re.finditer(
            r"\b(?:apt-get|apt)\s+[^\n;&]*?\binstall\s+([^\n;&]+)", text
        ):
            pins = sorted(
                {
                    f"{package}={version}"
                    for package, version in re.findall(
                        r"(?<![\w.-])([a-z0-9][a-z0-9+.-]*)=([0-9][^\s;&|]*)",
                        command.group(1),
                        re.I,
                    )
                }
            )
            if not pins:
                continue
            findings.append(
                TerminalAuditFinding(
                    task_id=task_id,
                    defect_type="fragile_exact_system_package_pin",
                    confidence=0.88,
                    severity="major",
                    message=(
                        "Reference/environment installation depends on exact mutable "
                        f"repository versions in {relative}."
                    ),
                    evidence={"file": relative, "pins": pins},
                )
            )
    return findings


def _runtime_network_dependencies(
    task_id: str, files: dict[str, str]
) -> list[TerminalAuditFinding]:
    findings: list[TerminalAuditFinding] = []
    patterns = (
        re.compile(r"^\s*(?:sudo\s+)?(?:curl|wget|yt-dlp|youtube-dl)\b", re.M | re.I),
        re.compile(r"\brequests\.(?:get|post|head)\s*\(", re.I),
        re.compile(r"\burllib\.request\.urlopen\s*\(", re.I),
    )
    for relative, text in files.items():
        if not relative.startswith("solution/"):
            continue
        if not any(pattern.search(text) for pattern in patterns):
            continue
        # Local health checks do not introduce an external dependency.
        stripped = re.sub(r"https?://(?:localhost|127\.0\.0\.1)[^\s'\"]*", "", text)
        if not re.search(r"https?://|\b(?:curl|wget|yt-dlp|youtube-dl)\s+\$", stripped, re.I):
            continue
        urls = sorted(
            {
                url.rstrip(".,;)'\"")
                for url in re.findall(r"https?://[^\s'\"<>]+", stripped)
                if "localhost" not in url and "127.0.0.1" not in url
            }
        )
        findings.append(
            TerminalAuditFinding(
                task_id=task_id,
                defect_type="runtime_external_dependency",
                confidence=0.66,
                severity="review",
                message="Reference execution reaches an external service at task runtime.",
                evidence={"file": relative, "urls": urls[:12]},
            )
        )
    return findings


def _resource_headroom(
    task_id: str, task_toml: str, combined: str
) -> list[TerminalAuditFinding]:
    resources = parse_task_resources(task_toml)
    memory = resources.get("memory_mb")
    if memory is None or memory > 4096:
        return []
    families = sorted(
        name for name, pattern in HEAVY_RESOURCE_MARKERS.items() if pattern.search(combined)
    )
    if not families:
        return []
    confidence = 0.78 if memory <= 2048 else 0.70
    return [
        TerminalAuditFinding(
            task_id=task_id,
            defect_type="low_resource_headroom",
            confidence=confidence,
            severity="major" if memory <= 2048 else "review",
            message=(
                f"Task allows only {memory:.0f} MiB while its environment/tests use "
                "resource-intensive components."
            ),
            evidence={"memory_mb": memory, "resource_families": families},
        )
    ]


def _overstrict_directory_tests(
    task_id: str, files: dict[str, str]
) -> list[TerminalAuditFinding]:
    findings: list[TerminalAuditFinding] = []
    pattern = re.compile(
        r"(?:os\.listdir\s*\([^\n]+\)|sorted\s*\(\s*os\.listdir\s*\([^\n]+\)\s*\))"
        r"\s*==\s*(\[[^\n]+\])"
    )
    for relative, text in files.items():
        if not relative.startswith("tests/"):
            continue
        matches = pattern.findall(text)
        if matches:
            findings.append(
                TerminalAuditFinding(
                    task_id=task_id,
                    defect_type="overstrict_directory_exactness",
                    confidence=0.92,
                    severity="major",
                    message="Verifier requires an exact directory listing, rejecting harmless byproducts.",
                    evidence={"file": relative, "expected_listings": matches[:6]},
                )
            )
    return findings


def _implicit_input_immutability(
    task_id: str, instruction: str, files: dict[str, str]
) -> list[TerminalAuditFinding]:
    if re.search(r"\b(?:do not|don't|must not|never)\s+(?:modify|change|touch|alter)\b", instruction, re.I):
        return []
    findings: list[TerminalAuditFinding] = []
    for relative, text in files.items():
        if not relative.startswith("tests/"):
            continue
        if not re.search(r"(?:sha256|md5).{0,180}(?:assert|expected)|(?:assert|expected).{0,180}(?:sha256|md5)", text, re.I | re.S):
            continue
        findings.append(
            TerminalAuditFinding(
                task_id=task_id,
                defect_type="implicit_input_byte_immutability",
                confidence=0.76,
                severity="major",
                message="Verifier appears to enforce byte-identical input state without an explicit immutability instruction.",
                evidence={"file": relative},
            )
        )
    return findings


def _host_cpu_leakage(
    task_id: str, task_toml: str, files: dict[str, str]
) -> list[TerminalAuditFinding]:
    resources = parse_task_resources(task_toml)
    cpus = resources.get("cpus")
    if cpus is None:
        return []
    hits: list[str] = []
    for relative, text in files.items():
        if relative.startswith(("solution/", "tests/")) and re.search(r"\bnproc\b", text):
            hits.append(relative)
    if not hits:
        return []
    return [
        TerminalAuditFinding(
            task_id=task_id,
            defect_type="container_host_cpu_leakage",
            confidence=0.72,
            severity="review",
            message="Task commands use nproc despite a smaller declared container CPU limit.",
            evidence={"declared_cpus": cpus, "files": sorted(set(hits))},
        )
    ]


def _deduplicate(
    findings: Iterable[TerminalAuditFinding],
) -> list[TerminalAuditFinding]:
    seen: set[tuple[str, str, str]] = set()
    result: list[TerminalAuditFinding] = []
    for finding in findings:
        file_name = str(finding.evidence.get("file", ""))
        key = (finding.task_id, finding.defect_type, file_name)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return sorted(result, key=lambda row: (row.task_id, row.defect_type, -row.confidence))
