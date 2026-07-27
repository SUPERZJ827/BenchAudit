from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.run_evalplus_differential_confirmation import (
    PinnedWorkerVerifier,
    _summary,
)


def test_pinned_worker_verifier_rejects_signature_or_identity_tampering():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    payload_sha256 = "ab" * 32
    attestation = {
        "run_id": "run-1",
        "payload_sha256": payload_sha256,
        "public_key_ed25519": base64.b64encode(public).decode("ascii"),
        "signature_ed25519": base64.b64encode(
            private.sign(bytes.fromhex(payload_sha256))
        ).decode("ascii"),
    }
    verifier = PinnedWorkerVerifier(attestation)
    assert verifier.verify(attestation, payload_sha256) is True
    assert verifier.verify({**attestation, "run_id": "run-2"}, payload_sha256) is False
    assert verifier.verify(
        {**attestation, "signature_ed25519": base64.b64encode(b"x" * 64).decode()},
        payload_sha256,
    ) is False


def test_stable_summary_excludes_random_attestation_material():
    rows = {
        "humaneval": [{
            "task_id": "HumanEval/0",
            "status": "valid",
            "candidates": 1,
            "completed_pairs": 1,
            "indeterminate_pairs": 0,
            "timeout_pairs": 0,
            "swapped_direction_pairs": 0,
            "confirmed": 1,
            "unattested_confirmed_control": 0,
            "attestation": {"signature": "random-one"},
        }],
        "mbpp": [{
            "task_id": "3",
            "status": "valid",
            "candidates": 1,
            "completed_pairs": 1,
            "indeterminate_pairs": 0,
            "timeout_pairs": 0,
            "swapped_direction_pairs": 0,
            "confirmed": 1,
            "unattested_confirmed_control": 0,
            "attestation": {"signature": "random-two"},
        }],
    }
    first = _summary(
        rows,
        image="image:v1",
        image_resolved="sha256:" + "1" * 64,
        per_family=2,
        per_probe_timeout=10.0,
        task_timeout=90.0,
        workers=8,
    )
    rows["humaneval"][0]["attestation"]["signature"] = "changed"
    second = _summary(
        rows,
        image="image:v1",
        image_resolved="sha256:" + "1" * 64,
        per_family=2,
        per_probe_timeout=10.0,
        task_timeout=90.0,
        workers=8,
    )
    assert first == second
