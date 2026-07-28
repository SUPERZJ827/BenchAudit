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


TASK_CONTRACT_SYSTEM_PROMPT = """You extract explicit output filenames from benchmark task text.
This is evidence extraction, not defect adjudication. Do not inspect inputs for coverage and do not infer
unstated deliverables.

Return only one JSON object with exactly this schema:
{
  "schema_version": "task-output-contract.v1",
  "output_requirements": [
    {
      "path": "relative/output.txt",
      "evidence": "exact substring copied from task"
    }
  ]
}

Rules:
- Extract only filenames or relative paths explicitly required for the final deliverable.
- Evidence strings must be copied verbatim from the task and must contain the extracted path.
- Input filenames are not outputs. For example, in "summarize 1.txt ... 100.txt as 123.txt", extract only
  "123.txt".
- An empty output_requirements array is valid. Never invent a filename or silently repair the task.
"""


class TaskContractValidationError(ValueError):
    pass


@dataclass(frozen=True)
class OutputRequirement:
    path: str
    evidence: str


@dataclass(frozen=True)
class TaskContract:
    schema_version: str
    output_requirements: tuple[OutputRequirement, ...]
    expected_output_paths: tuple[str, ...]


_TOP_LEVEL_KEYS = {"schema_version", "output_requirements"}
_OUTPUT_INVENTORY_KEYS = {
    "output_files",
    "outputs",
    "expected_files",
    "required_files",
    "deliverables",
    "output_manifest",
}
_INPUT_INVENTORY_KEYS = {
    "input_files",
    "inputs",
    "attachments",
    "data_files",
    "source_files",
    "input_manifest",
    "data_manifest",
    "reference_files",
}
# A manifest record can expose several aliases at once. Keep an explicit,
# deterministic precedence rather than depending on randomized set iteration.
_PATH_VALUE_KEYS = ("path", "relative_path", "filename", "file", "name")
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


def _safe_output_filename(value: Any, location: str) -> str:
    """Project a task-declared save path onto the published filename contract.

    Workspace records publish output basenames rather than their desktop/save
    directories.  Preserve traversal rejection, but compare only the final path
    component so ``/desktop/report.docx`` and ``report.docx`` use the same
    contract namespace.
    """

    if not isinstance(value, str) or not value.strip():
        raise TaskContractValidationError(f"{location} must be a non-empty string")
    normalized = unicodedata.normalize("NFKC", value.strip()).replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        normalized in {".", ".."}
        or any(part == ".." for part in path.parts)
        or any(ord(character) < 32 for character in normalized)
    ):
        raise TaskContractValidationError(f"{location} contains an unsafe path")
    filename = path.name
    if not filename or filename in {".", ".."}:
        raise TaskContractValidationError(f"{location} contains an unsafe path")
    return filename


def parse_task_contract(task: str, response: dict[str, Any]) -> TaskContract:
    if not isinstance(task, str) or not task:
        raise TaskContractValidationError("task must be a non-empty string")
    if not isinstance(response, dict):
        raise TaskContractValidationError("model response must be an object")
    _expect_exact_keys(response, _TOP_LEVEL_KEYS, "task contract")
    if response["schema_version"] != "task-output-contract.v1":
        raise TaskContractValidationError("unsupported task contract schema_version")

    raw_outputs = response["output_requirements"]
    if not isinstance(raw_outputs, list):
        raise TaskContractValidationError("output_requirements must be an array")

    output_requirements: list[OutputRequirement] = []
    expected_outputs: list[str] = []
    for index, raw in enumerate(raw_outputs):
        location = f"output_requirements[{index}]"
        if not isinstance(raw, dict):
            raise TaskContractValidationError(f"{location} must be an object")
        _expect_exact_keys(raw, {"path", "evidence"}, location)
        evidence = _evidence_anchor(task, raw["evidence"], f"{location}.evidence")
        path = _safe_output_filename(raw["path"], f"{location}.path")
        if path not in unicodedata.normalize("NFKC", evidence):
            raise TaskContractValidationError(
                f"{location}.path is not grounded by its evidence"
            )
        output_requirements.append(OutputRequirement(path=path, evidence=evidence))
        expected_outputs.append(path)

    return TaskContract(
        schema_version="task-output-contract.v1",
        output_requirements=tuple(output_requirements),
        expected_output_paths=tuple(dict.fromkeys(expected_outputs)),
    )


def _paths_from_inventory(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, (list, dict)):
                return _paths_from_inventory(decoded)
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


def _output_inventory(item: BenchmarkItem) -> tuple[bool, tuple[str, ...]]:
    paths: list[str] = []
    available = False
    containers: list[dict[str, Any]] = [item.raw]
    if isinstance(item.output_contract, dict):
        containers.append(item.output_contract)
    for container in containers:
        for key, value in container.items():
            if str(key).casefold() in _OUTPUT_INVENTORY_KEYS:
                available = True
                paths.extend(_paths_from_inventory(value))
    return available, tuple(dict.fromkeys(paths))


def _input_inventory(item: BenchmarkItem) -> tuple[bool, tuple[str, ...]]:
    paths: list[str] = []
    available = False
    for key, value in item.raw.items():
        if str(key).casefold() in _INPUT_INVENTORY_KEYS:
            available = True
            paths.extend(_paths_from_inventory(value))
    return available, tuple(dict.fromkeys(paths))


def replay_task_contract_inventory(
    item: BenchmarkItem, contract: TaskContract
) -> dict[str, Any]:
    output_inventory_available, observed_outputs = _output_inventory(item)
    input_inventory_available, observed_inputs = _input_inventory(item)
    expected_outputs = set(contract.expected_output_paths)
    observed_output_set = set(observed_outputs)
    missing_candidates = (
        expected_outputs - observed_output_set if output_inventory_available else set()
    )
    # Exact grounding proves that a filename occurs in the task, but it does not
    # prove that the filename denotes an output. If a model-extracted requirement
    # is explicitly listed as an input, abstain on that candidate instead of
    # converting a role-classification mistake into a benchmark defect.
    suppressed_role_ambiguous = sorted(
        missing_candidates & set(observed_inputs)
        if input_inventory_available
        else set()
    )
    missing_outputs = sorted(
        missing_candidates - set(suppressed_role_ambiguous)
    )
    return {
        "output_inventory_available": output_inventory_available,
        "input_inventory_available": input_inventory_available,
        "expected_output_count": len(contract.expected_output_paths),
        "observed_output_count": len(observed_outputs),
        "observed_input_count": len(observed_inputs),
        "suppressed_input_output_overlap_count": len(suppressed_role_ambiguous),
        "suppressed_input_output_overlap_paths": suppressed_role_ambiguous[
            :_MAX_EVIDENCE_PATHS
        ],
        "suppressed_input_output_overlap_paths_truncated": (
            len(suppressed_role_ambiguous) > _MAX_EVIDENCE_PATHS
        ),
        "missing_output_count": len(missing_outputs),
        "missing_output_paths": missing_outputs[:_MAX_EVIDENCE_PATHS],
        "missing_output_paths_truncated": len(missing_outputs) > _MAX_EVIDENCE_PATHS,
    }


class LLMTaskContractAuditor(BaseLLMAuditor):
    """Extract output filenames with an LLM, then replay them against a manifest."""

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
        return AuditEligibility.applicable(
            "task text can be projected into an output filename contract"
        )

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
        if not (
            replay["output_inventory_available"]
            and replay["missing_output_count"]
        ):
            return []
        return [
            _violation(
                item,
                "task_artifact_contract_mismatch",
                0.75,
                "Published output inventory omits a task-declared deliverable filename.",
                {
                    "evidence_level": "llm_extraction_static_inventory_replay",
                    "contract": asdict(contract),
                    **replay,
                },
                severity="review",
                review_only=True,
                repair="Publish the required filename or correct the task/output inventory.",
                method=self.name,
                artifact="expected_output",
            )
        ]
