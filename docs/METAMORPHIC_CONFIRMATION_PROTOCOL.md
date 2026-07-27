# Metamorphic evaluator confirmation protocol

Status: frozen Phase-1 protocol  
Branch: `research/generalized-confirmation-metamorphic-20260727`

## Research target

The falsifiable target is:

> Confirm at least one real defect in a benchmark for which BenchAudit has no
> benchmark-specific proof validator.

Phase 1 implements the reusable MR-1/MR-2 core. It does not claim that the
target has already been reached.

## Trust decomposition

A metamorphic finding is confirmable only when all three statements hold:

1. A deterministic, type-scoped transformer reproduces a semantics proof.
2. The same evaluator identity returns different verdicts for the original and
   transformed representations, or rejects its own gold.
3. An independent verifier accepts an attestation bound to the exact
   verdict-bearing transcript.

Missing any statement caps the result at `review`. Confidence, an LLM vote,
an evaluator-provided trust string, or a well-shaped hash cannot replace the
attestation.

## Phase-1 relations

### MR-1: gold self-consistency

If an executable evaluator rejects the benchmark's own gold answer, the gold,
evaluator, or their declared contract is inconsistent.

### MR-2: evaluator format invariance

Only the following semantic profiles are supported:

| Profile | Transformations | Replayed proof |
|---|---|---|
| `mcq_choice` | fixed option permutation plus synchronized gold-label permutation | explicit label namespace and preservation of the selected choice |
| `numeric_value` | fractional trailing zero, optional leading zero, trailing token-external space | exact finite `Decimal` equality |
| `python_ast` | terminal newline, trailing comment | equality of Python ASTs with attributes removed |
| `sql_layout` | leading/trailing token-external whitespace, fixed non-hint leading comment | opt-in SQL contract plus byte-for-byte preservation of the original SQL |
| `trim_insensitive_text` | leading/trailing ASCII space | explicit trim-insensitive contract plus equal stripped text |

`free_text` has no confirmable transformation. Python indentation, arbitrary
whitespace edits, SQL token rewriting, paraphrases, and LLM-generated
transformations are forbidden.

Every contract must bind an exact `evaluator_identity`. Every emitted relation
contains a non-empty `semantics_preserving_rationale`, but promotion does not
trust the prose or a stored `verified=true` flag: it regenerates the variant
from the live gold and contract and compares the complete evidence payload.

### MR-3: MCQ permutation consistency

This relation is enabled only when the contract supplies an explicit,
cardinality-matched choice-label namespace. BenchAudit reverses the option
sequence, moves the gold label to the selected choice's new position, and
replays the evaluator on the cloned canonical item. Unknown, ambiguous, or
inferred encodings are not transformed. The original and transformed selected
choice must have identical canonical bytes. Without independent transcript
attestation, a verdict flip remains review.

## Execution boundary

The core consumes an evaluator adapter implementing:

```python
evaluate(item, answer) -> EvaluatorObservation
```

This is an integration boundary, not confirmation authority. Without a
separate transcript attester and verifier, all detected flips remain review.
Timeout and execution error are `indeterminate`; they are never interpreted as
semantic rejection.

Phase 1 transforms the canonical gold string. Adapters for archived candidate
outputs and external command harnesses are later integrations and must not
weaken the proof rules.

## Frozen acceptance gates

1. 100 injected clean numeric evaluator cases produce zero findings.
2. An exact-lexeme evaluator produces a format-invariance candidate.
3. The candidate is review without independent attestation.
4. The same candidate is confirmed only with accepted, transcript-bound
   attestation and successful local semantics replay.
5. Gold rejection follows the same attestation requirement.
6. Timeout produces no substantive finding and records `indeterminate`.
7. GDPval and WorkspaceBench regression runs must not lose existing confirmed
   findings before integration is merged.
8. Two identical experiment runs must have identical stable summary hashes.
9. Failure to find a new-benchmark confirmed defect is retained as a negative
   result; semantic-preservation rules are not relaxed.

## Not yet claimed

- No command evaluator adapter is enabled in the main CLI.
- No new public benchmark has passed the north-star gate.
- MR-3 option permutation and MR-4 weak/strong oracle pairs are not part of
  this Phase-1 implementation.
