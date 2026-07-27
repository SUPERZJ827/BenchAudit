from __future__ import annotations

import json
import posixpath
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

from .checkers import _violation
from .coverage import AuditEligibility
from .llm_auditor import BaseLLMAuditor
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation


TASK_CONTRACT_SYSTEM_PROMPT = """You extract explicit file-operation contracts from benchmark task text.
This is evidence extraction, not defect adjudication. Do not infer unstated files or requirements.

Return only one JSON object with exactly this schema:
{
  "schema_version": "task-contract.v1",
  "operation": "summarize" | "transform" | "generate" | "compare" | "analyze" | "other",
  "input_requirements": [
    {
      "kind": "explicit_file",
      "path": "relative/path.txt",
      "evidence": "exact substring copied from task"
    }
    OR
    {
      "kind": "numeric_range",
      "prefix": "relative/prefix",
      "suffix": ".txt",
      "start": 1,
      "end": 100,
      "width": 0,
      "evidence": "exact substring copied from task"
    }
  ],
  "output_requirements": [
    {
      "path": "relative/output.txt",
      "evidence": "exact substring copied from task"
    }
  ],
  "coverage": "all_inputs" | "subset" | "unspecified",
  "coverage_evidence": "exact substring copied from task" | null
}

Rules:
- Evidence strings must be copied verbatim from the task.
- Extract only mechanically identifiable file requirements.
- A range such as 1.txt ... 100.txt is one numeric_range, not 100 explicit entries.
- width is the number of zero-padded digits, or 0 when there is no declared padding.
- Use coverage=all_inputs only when the task explicitly applies the operation to every listed/ranged input.
- Empty arrays are valid. Never invent a file or silently repair the task.
"""


class TaskContractValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FileRequirement:
    kind: str
    evidence: str
    path: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    start: int | None = None
    end: int | None = None
    width: int | None = None


@dataclass(frozen=True)
class OutputRequirement:
    path: str
    evidence: str


@dataclass(frozen=True)
class TaskContract:
    schema_version: str
    operation: str
    input_requirements: tuple[FileRequirement, ...]
    output_requirements: tuple[OutputRequirement, ...]
    coverage: str
    coverage_evidence: str | None
    expected_input_paths: tuple[str, ...]
    expected_output_paths: tuple[str, ...]


_TOP_LEVEL_KEYS = {
    "schema_version",
    "operation",
    "input_requirements",
    "output_requirements",
    "coverage",
    "coverage_evidence",
}
_OPERATIONS = {"summarize", "transform", "generate", "compare", "analyze", "other"}
_COVERAGE = {"all_inputs", "subset", "unspecified"}
_INPUT_INVENTORY_KEYS = {
    "input_files",
    "inputs",
    "attachments",
    "files",
    "data_files",
    "source_files",
    "input_manifest",
}
_OUTPUT_INVENTORY_KEYS = {
    "output_files",
    "outputs",
    "expected_files",
    "deliverables",
    "output_manifest",
    "reference_files",
}
_PATH_VALUE_KEYS = {"path", "name", "file", "filename", "relative_path"}
_MAX_EXPANDED_PATHS = 10_000
_MAX_EVIDENCE_PATHS = 200


def _expect_exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    actual = set(value)
    if actual != expected:
        raise TaskContractValidationError(
            f"{location} keys must be exactly {sorted(expected)}; got {sorted(actual)}"
        )


def _evidence_anchor(task: str, value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise TaskContractValidationError(f"{location} must be a non-empty string")
    if value not in task:
        raise TaskContractValidationError(
            f"{location} is not an exact substring of the task"
        )
    return value


def _safe_relative_path(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskContractValidationError(f"{location} must be a non-empty string")
    normalized = unicodedata.normalize("NFKC", value.strip()).replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or normalized in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(character) < 32 for character in normalized)
    ):
        raise TaskContractValidationError(f"{location} contains an unsafe path")
    return posixpath.normpath(normalized)


def _plain_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TaskContractValidationError(f"{location} must be an integer")
    return value


def _range_path(prefix: str, suffix: str, value: int, width: int) -> str:
    number = str(value) if width == 0 else f"{value:0{width}d}"
    return _safe_relative_path(f"{prefix}{number}{suffix}", "numeric_range path")


def parse_task_contract(task: str, response: dict[str, Any]) -> TaskContract:
    if not isinstance(task, str) or not task:
        raise TaskContractValidationError("task must be a non-empty string")
    if not isinstance(response, dict):
        raise TaskContractValidationError("model response must be an object")
    _expect_exact_keys(response, _TOP_LEVEL_KEYS, "task contract")
    if response["schema_version"] != "task-contract.v1":
        raise TaskContractValidationError("unsupported task contract schema_version")
    operation = response["operation"]
    if operation not in _OPERATIONS:
        raise TaskContractValidationError("unsupported task contract operation")
    coverage = response["coverage"]
    if coverage not in _COVERAGE:
        raise TaskContractValidationError("unsupported task contract coverage")

    raw_inputs = response["input_requirements"]
    raw_outputs = response["output_requirements"]
    if not isinstance(raw_inputs, list) or not isinstance(raw_outputs, list):
        raise TaskContractValidationError("requirement fields must be arrays")

    input_requirements: list[FileRequirement] = []
    expected_inputs: list[str] = []
    for index, raw in enumerate(raw_inputs):
        location = f"input_requirements[{index}]"
        if not isinstance(raw, dict):
            raise TaskContractValidationError(f"{location} must be an object")
        kind = raw.get("kind")
        if kind == "explicit_file":
            _expect_exact_keys(raw, {"kind", "path", "evidence"}, location)
            evidence = _evidence_anchor(task, raw["evidence"], f"{location}.evidence")
            path = _safe_relative_path(raw["path"], f"{location}.path")
            if path not in unicodedata.normalize("NFKC", evidence):
                raise TaskContractValidationError(
                    f"{location}.path is not grounded by its evidence"
                )
            input_requirements.append(
                FileRequirement(kind=kind, path=path, evidence=evidence)
            )
            expected_inputs.append(path)
        elif kind == "numeric_range":
            keys = {"kind", "prefix", "suffix", "start", "end", "width", "evidence"}
            _expect_exact_keys(raw, keys, location)
            evidence = _evidence_anchor(task, raw["evidence"], f"{location}.evidence")
            prefix = raw["prefix"]
            suffix = raw["suffix"]
            if not isinstance(prefix, str) or not isinstance(suffix, str):
                raise TaskContractValidationError(
                    f"{location} prefix and suffix must be strings"
                )
            start = _plain_int(raw["start"], f"{location}.start")
            end = _plain_int(raw["end"], f"{location}.end")
            width = _plain_int(raw["width"], f"{location}.width")
            if start < 0 or end < start or width < 0 or width > 12:
                raise TaskContractValidationError(f"{location} has invalid range bounds")
            count = end - start + 1
            if count > _MAX_EXPANDED_PATHS:
                raise TaskContractValidationError(
                    f"{location} expands beyond {_MAX_EXPANDED_PATHS} paths"
                )
            paths = tuple(
                _range_path(prefix, suffix, value, width)
                for value in range(start, end + 1)
            )
            normalized_evidence = unicodedata.normalize("NFKC", evidence)
            if paths[0] not in normalized_evidence or paths[-1] not in normalized_evidence:
                raise TaskContractValidationError(
                    f"{location} endpoints are not grounded by its evidence"
                )
            input_requirements.append(
                FileRequirement(
                    kind=kind,
                    prefix=prefix,
                    suffix=suffix,
                    start=start,
                    end=end,
                    width=width,
                    evidence=evidence,
                )
            )
            expected_inputs.extend(paths)
        else:
            raise TaskContractValidationError(f"{location} has unsupported kind")

    output_requirements: list[OutputRequirement] = []
    expected_outputs: list[str] = []
    for index, raw in enumerate(raw_outputs):
        location = f"output_requirements[{index}]"
        if not isinstance(raw, dict):
            raise TaskContractValidationError(f"{location} must be an object")
        _expect_exact_keys(raw, {"path", "evidence"}, location)
        evidence = _evidence_anchor(task, raw["evidence"], f"{location}.evidence")
        path = _safe_relative_path(raw["path"], f"{location}.path")
        if path not in unicodedata.normalize("NFKC", evidence):
            raise TaskContractValidationError(
                f"{location}.path is not grounded by its evidence"
            )
        output_requirements.append(OutputRequirement(path=path, evidence=evidence))
        expected_outputs.append(path)

    coverage_evidence = response["coverage_evidence"]
    if coverage_evidence is not None:
        coverage_evidence = _evidence_anchor(
            task, coverage_evidence, "coverage_evidence"
        )
    if coverage == "all_inputs" and coverage_evidence is None:
        raise TaskContractValidationError(
            "all_inputs coverage requires an exact evidence anchor"
        )

    return TaskContract(
        schema_version="task-contract.v1",
        operation=operation,
        input_requirements=tuple(input_requirements),
        output_requirements=tuple(output_requirements),
        coverage=coverage,
        coverage_evidence=coverage_evidence,
        expected_input_paths=tuple(dict.fromkeys(expected_inputs)),
        expected_output_paths=tuple(dict.fromkeys(expected_outputs)),
    )


def _paths_from_inventory(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            return [_safe_relative_path(value, "inventory path")]
        except TaskContractValidationError:
            return []
    if isinstance(value, list):
        paths: list[str] = []
        for entry in value:
            paths.extend(_paths_from_inventory(entry))
        return paths
    if isinstance(value, dict):
        for key in _PATH_VALUE_KEYS:
            if key in value:
                return _paths_from_inventory(value[key])
        paths = []
        for key in value:
            if isinstance(key, str) and ("." in key or "/" in key or "\\" in key):
                paths.extend(_paths_from_inventory(key))
        return paths
    return []


def _inventory(
    item: BenchmarkItem, keys: set[str], *, include_context: bool
) -> tuple[bool, tuple[str, ...]]:
    paths: list[str] = []
    available = False
    containers: list[dict[str, Any]] = [item.raw]
    if include_context:
        containers.append(item.context)
    if isinstance(item.output_contract, dict):
        containers.append(item.output_contract)
    for container in containers:
        for key, value in container.items():
            if str(key).casefold() in keys:
                available = True
                paths.extend(_paths_from_inventory(value))
    return available, tuple(dict.fromkeys(paths))


def replay_task_contract_inventory(
    item: BenchmarkItem, contract: TaskContract
) -> dict[str, Any]:
    input_inventory_available, observed_inputs = _inventory(
        item, _INPUT_INVENTORY_KEYS, include_context=True
    )
    output_inventory_available, observed_outputs = _inventory(
        item, _OUTPUT_INVENTORY_KEYS, include_context=False
    )
    missing_inputs = (
        sorted(set(contract.expected_input_paths) - set(observed_inputs))
        if input_inventory_available
        else []
    )
    missing_outputs = (
        sorted(set(contract.expected_output_paths) - set(observed_outputs))
        if output_inventory_available
        else []
    )
    return {
        "input_inventory_available": input_inventory_available,
        "output_inventory_available": output_inventory_available,
        "expected_input_count": len(contract.expected_input_paths),
        "observed_input_count": len(observed_inputs),
        "missing_input_count": len(missing_inputs),
        "missing_input_paths": missing_inputs[:_MAX_EVIDENCE_PATHS],
        "missing_input_paths_truncated": len(missing_inputs) > _MAX_EVIDENCE_PATHS,
        "expected_output_count": len(contract.expected_output_paths),
        "observed_output_count": len(observed_outputs),
        "missing_output_count": len(missing_outputs),
        "missing_output_paths": missing_outputs[:_MAX_EVIDENCE_PATHS],
        "missing_output_paths_truncated": len(missing_outputs) > _MAX_EVIDENCE_PATHS,
    }


class LLMTaskContractAuditor(BaseLLMAuditor):
    """Extract a task contract with an LLM, then replay it against inventories."""

    name = "llm_task_contract"
    prompt = TASK_CONTRACT_SYSTEM_PROMPT
    remote_egress_capability = {
        "outbound_fields": ("item_id", "task"),
        "attachment_content": False,
    }

    def __init__(
        self,
        client: LLMClient,
        confirm_threshold: float = 0.75,
        review_threshold: float = 0.45,
    ) -> None:
        super().__init__(client, confirm_threshold, review_threshold)

    def audit_eligibility(
        self, item: BenchmarkItem, root=None
    ) -> AuditEligibility:
        if not item.task:
            return AuditEligibility.not_applicable("task text is absent")
        return AuditEligibility.applicable("task text can be projected into a file contract")

    def check(self, item: BenchmarkItem, root=None) -> Iterable[Violation]:
        if not item.task:
            return []
        self.last_error = None
        payload = {"item_id": item.item_id, "task": item.task}
        try:
            response = self.client.chat_json(
                self.prompt,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            contract = parse_task_contract(item.task, response)
        except (RuntimeError, TaskContractValidationError) as exc:
            self.last_error = str(exc)
            item.metadata.setdefault("_llm_observations", {})[self.name] = {
                "validation_status": "rejected",
                "audit_failure": str(exc),
            }
            return [self.failure_violation(item)]

        replay = replay_task_contract_inventory(item, contract)
        item.metadata.setdefault("_llm_observations", {})[self.name] = {
            "validation_status": "validated",
            "contract": asdict(contract),
            "inventory_replay": replay,
        }
        violations: list[Violation] = []
        if replay["input_inventory_available"] and replay["missing_input_count"]:
            violations.append(
                _violation(
                    item,
                    "artifact_data_gap",
                    0.85,
                    "Task-declared input files are absent from the supplied input inventory.",
                    {
                        "evidence_level": "llm_extraction_static_inventory_replay",
                        "contract": asdict(contract),
                        **replay,
                    },
                    severity="major",
                    review_only=True,
                    repair="Provide the missing task-declared inputs or correct the task contract.",
                    method=self.name,
                )
            )
        if replay["output_inventory_available"] and replay["missing_output_count"]:
            violations.append(
                _violation(
                    item,
                    "task_artifact_contract_mismatch",
                    0.85,
                    "Published output inventory omits a task-declared deliverable.",
                    {
                        "evidence_level": "llm_extraction_static_inventory_replay",
                        "contract": asdict(contract),
                        **replay,
                    },
                    severity="major",
                    review_only=True,
                    repair="Publish the required output or correct the task/output inventory.",
                    method=self.name,
                    artifact="expected_output",
                )
            )
        return violations
