#!/usr/bin/env python3
"""Run the frozen Workspace P0 blind review through an independent model.

The runner intentionally reads only the frozen protocol, its pre-unblinding
amendment, and the three blind-package files. Raw responses and annotations
must be written outside the git worktree.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import stat
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.validate_workspace_p0_annotations import (
    ENUMS,
    read_jsonl,
    validate_annotations,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_ROOT = Path(
    "/home/zhoujun/llmdata/after623/reports/"
    "workspace_p0_blind_adjudication_20260728"
)
BLIND_PACKAGE = DEFAULT_PRIVATE_ROOT / "blind_package"
PROTOCOL = (
    REPO / "experiments/workspace_grounding/p0_blind_adjudication/"
    "PROTOCOL_20260728.md"
)
AMENDMENT = (
    REPO / "experiments/workspace_grounding/p0_blind_adjudication/"
    "PROTOCOL_AMENDMENT_INDEPENDENT_MODEL_20260728.md"
)
MODEL = "google/gemini-3.1-pro-preview"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

ANNOTATION_FIELDS = {
    "blind_id",
    "acceptable_families",
    "confidence",
    "evaluation_objectivity",
    "evidence",
    "grounding_class",
    "is_grounding_defect",
    "primary_family",
    "root_cause_summary",
    "satisfaction_checkability",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_private_dir(path: Path) -> Path:
    path = path.resolve()
    repo = REPO.resolve()
    if path == repo or repo in path.parents:
        raise ValueError("blind review output must remain outside the git worktree")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(stat.S_IRWXU)
    return path


def annotation_schema() -> dict[str, Any]:
    evidence = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "source": {
                "type": "string",
                "pattern": "^(task|output_contract|input:.+)$",
            },
            "quote": {"type": "string"},
            "relation": {
                "type": "string",
                "enum": ["supports", "contradicts", "insufficient"],
            },
        },
        "required": ["source", "quote", "relation"],
    }
    row = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "blind_id": {"type": "string"},
            "grounding_class": {
                "type": "string",
                "enum": sorted(ENUMS["grounding_class"]),
            },
            "is_grounding_defect": {
                "type": "string",
                "enum": sorted(ENUMS["is_grounding_defect"]),
            },
            "evaluation_objectivity": {
                "type": "string",
                "enum": sorted(ENUMS["evaluation_objectivity"]),
            },
            "satisfaction_checkability": {
                "type": "string",
                "enum": sorted(ENUMS["satisfaction_checkability"]),
            },
            "primary_family": {"type": "string"},
            "acceptable_families": {
                "type": "array",
                "items": {"type": "string"},
            },
            "root_cause_summary": {"type": "string"},
            "evidence": {
                "type": "array",
                "minItems": 1,
                "items": evidence,
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": sorted(ANNOTATION_FIELDS),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "annotations": {
                "type": "array",
                "minItems": 1,
                "items": row,
            },
        },
        "required": ["annotations"],
    }


def build_system_prompt() -> str:
    return """You are the first independent blind reviewer in a benchmark-audit
study. You have no prior conversation and must use only the task bundle in this
request. Do not infer any previous model verdict or experimental stratum.

Judge whether each RUBRIC REQUIREMENT is a reasonable and grounded scoring
requirement for an agent that saw only the TASK, OUTPUT CONTRACT, and ALLOWED
INPUT EVIDENCE. Do NOT judge whether a candidate output satisfies it.

Decision rules:
- task_or_input_derived/no: explicitly stated or uniquely derivable without
  adding an unstated filter, rounding rule, threshold, or tie-break.
- intrinsic_validity/no: basic artifact validity such as opening, valid format,
  or existence of the requested artifact.
- general_quality/no: ordinary clarity, correctness, professionalism, or
  relevance requirements; objectivity may still be subjective or mixed.
- hidden_exact_constraint/yes: an exact literal, count, layout, color, title,
  filename, threshold, or other narrow requirement absent from allowed sources.
- task_contract_conflict/yes: requirement contradicts the task, contract, or
  allowed input evidence.
- insufficient_evidence/uncertain: the allowed evidence cannot establish either
  legitimacy or defect without guessing.

Evidence rules:
- Every quote must be copied EXACTLY from TASK, OUTPUT CONTRACT, or ALLOWED
  INPUT EVIDENCE in this request. Never paraphrase a quote.
- To show absence, quote the closest relevant source text and use relation
  'insufficient'; do not invent a sentence saying that something is absent.
- source must be task, output_contract, or input:<filename>.

Detector-family examples: workspace_rubric_grounding, task_contract,
artifact_execution, input_recomputation, subjective_quality_review, unknown.
Return only the JSON object required by the response schema."""


def build_user_prompt(
    task_row: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    prior_error: str | None = None,
) -> str:
    payload = {
        "task_blind_id": task_row["task_blind_id"],
        "task": task_row["task"],
        "output_contract": task_row["output_contract"],
        "allowed_input_evidence": task_row["allowed_input_evidence"],
        "evidence_status": task_row["evidence_status"],
        "candidates": [
            {"blind_id": row["blind_id"], "rubric": row["rubric"]}
            for row in candidate_rows
        ],
    }
    suffix = ""
    if prior_error:
        suffix = (
            "\n\nYour previous response failed local validation. Correct only "
            "the listed issue while using the same blind evidence:\n"
            f"{prior_error}"
        )
    return (
        "Independently annotate every candidate in this single task bundle. "
        "Return exactly one annotation per supplied blind_id.\n\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        + suffix
    )


def parse_content(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("response has no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("response message has no JSON content")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(content[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("response JSON must be an object")
    return parsed


def validate_task_annotations(
    task_row: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
) -> None:
    validate_annotations(
        [{"blind_id": row["blind_id"]} for row in candidate_rows],
        annotations,
    )
    task_text = str(task_row["task"])
    contract_text = json.dumps(
        task_row["output_contract"], ensure_ascii=False, sort_keys=True,
    )
    input_text = str(task_row["allowed_input_evidence"])
    for row in annotations:
        for evidence in row["evidence"]:
            source = evidence["source"]
            quote = evidence["quote"]
            if source == "task":
                haystack = task_text
            elif source == "output_contract":
                haystack = contract_text
            elif source.startswith("input:"):
                haystack = input_text
            else:
                raise ValueError(
                    f"{row['blind_id']}: unsupported evidence source {source!r}"
                )
            if quote not in haystack:
                raise ValueError(
                    f"{row['blind_id']}: evidence quote is not an exact "
                    f"substring of {source}: {quote!r}"
                )


def api_request(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/SUPERZJ827/BenchAudit",
            "X-Title": "BenchAudit Workspace P0 Blind Review",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body[:1000]}") from exc


def review_task(
    *,
    api_key: str,
    task_row: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    raw_dir: Path,
    max_attempts: int,
    system_prompt: str | None = None,
    attempt_offset: int = 0,
) -> dict[str, Any]:
    task_id = str(task_row["task_blind_id"])
    prior_error: str | None = None
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": build_user_prompt(
                        task_row, candidate_rows, prior_error,
                    ),
                },
            ],
            "temperature": 0,
            "reasoning": {"effort": "high"},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "workspace_p0_blind_annotations",
                    "strict": True,
                    "schema": annotation_schema(),
                },
            },
        }
        started = time.monotonic()
        try:
            response = api_request(api_key, payload)
            raw_path = (
                raw_dir
                / f"{task_id}.attempt-{attempt_offset + attempt}.json"
            )
            raw_path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            raw_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            parsed = parse_content(response)
            annotations = parsed.get("annotations")
            if not isinstance(annotations, list):
                raise ValueError("response lacks annotations array")
            validate_task_annotations(task_row, candidate_rows, annotations)
            observed_model = str(response.get("model") or "")
            if MODEL not in observed_model and observed_model != MODEL:
                raise ValueError(
                    f"unexpected response model: {observed_model!r}"
                )
            return {
                "task_blind_id": task_id,
                "annotations": annotations,
                "attempts": attempt,
                "observed_model": observed_model,
                "usage": response.get("usage") or {},
                "response_id": response.get("id"),
                "latency_seconds": round(time.monotonic() - started, 3),
            }
        except Exception as exc:
            prior_error = f"{type(exc).__name__}: {exc}"
            attempts.append({"attempt": attempt, "error": prior_error})
            if attempt == max_attempts:
                raise RuntimeError(
                    f"{task_id} failed after {attempt} attempts: {prior_error}"
                ) from exc
            time.sleep(min(2 ** (attempt - 1), 8))
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    args = parser.parse_args()
    if args.model != MODEL:
        raise ValueError(
            f"model is protocol-frozen as {MODEL}; got {args.model}"
        )
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    private_root = ensure_private_dir(args.private_root)
    raw_dir = ensure_private_dir(private_root / "gemini_3_1_pro_raw")
    tasks_path = BLIND_PACKAGE / "BLIND_TASKS.jsonl"
    candidates_path = BLIND_PACKAGE / "BLIND_CANDIDATES.jsonl"
    template_path = BLIND_PACKAGE / "ANNOTATION_TEMPLATE.jsonl"

    tasks = read_jsonl(tasks_path)
    candidates = read_jsonl(candidates_path)
    template = read_jsonl(template_path)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_task[str(row["task_blind_id"])].append(row)
    task_by_id = {str(row["task_blind_id"]): row for row in tasks}
    if set(by_task) != set(task_by_id):
        raise ValueError("task and candidate blind-id coverage differs")

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.workers,
    ) as executor:
        futures = {
            executor.submit(
                review_task,
                api_key=api_key,
                task_row=task_by_id[task_id],
                candidate_rows=rows,
                raw_dir=raw_dir,
                max_attempts=args.max_attempts,
            ): task_id
            for task_id, rows in sorted(by_task.items())
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"completed {result['task_blind_id']} "
                f"attempts={result['attempts']} "
                f"latency={result['latency_seconds']}s",
                flush=True,
            )

    annotations = [
        row
        for result in results
        for row in result["annotations"]
    ]
    template_order = {
        str(row["blind_id"]): index for index, row in enumerate(template)
    }
    annotations.sort(key=lambda row: template_order[str(row["blind_id"])])
    summary = validate_annotations(template, annotations)
    for task_id, rows in by_task.items():
        task_annotations = [
            row for row in annotations
            if row["blind_id"] in {candidate["blind_id"] for candidate in rows}
        ]
        validate_task_annotations(
            task_by_id[task_id], rows, task_annotations,
        )

    annotation_path = (
        private_root / "GEMINI_3_1_PRO_INDEPENDENT_ANNOTATIONS.jsonl"
    )
    annotation_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in annotations
        ),
        encoding="utf-8",
    )
    annotation_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    usage_totals: Counter[str] = Counter()
    observed_models = set()
    total_attempts = 0
    for result in results:
        total_attempts += int(result["attempts"])
        observed_models.add(result["observed_model"])
        for key, value in result["usage"].items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage_totals[key] += value

    receipt = {
        "protocol_version": "workspace-grounding-p0-adjudication-v1.1-20260728",
        "review_role": "independent_cross_model_blind_review",
        "requested_model": MODEL,
        "observed_models": sorted(observed_models),
        "fresh_context_per_task": True,
        "tasks": len(tasks),
        "candidates": len(annotations),
        "api_requests_including_retries": total_attempts,
        "logical_task_requests": len(tasks),
        "prohibited_files_read": [],
        "sealed_mapping_read": False,
        "prior_case_verdicts_read": False,
        "blinding_compromised": False,
        "exact_evidence_quotes_validated": True,
        "annotation_sha256": sha256(annotation_path),
        "input_sha256": {
            "protocol": sha256(PROTOCOL),
            "amendment": sha256(AMENDMENT),
            "blind_tasks": sha256(tasks_path),
            "blind_candidates": sha256(candidates_path),
            "annotation_template": sha256(template_path),
        },
        "usage": dict(sorted(usage_totals.items())),
        "grounding_defect_counts": summary["grounding_defect_counts"],
        "grounding_class_counts": summary["grounding_class_counts"],
        "raw_response_directory": str(raw_dir),
    }
    receipt_path = (
        private_root / "GEMINI_3_1_PRO_INDEPENDENT_RECEIPT.json"
    )
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
