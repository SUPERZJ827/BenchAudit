# MMLU recorded-development holdout contamination protocol V2

> Frozen: 2026-08-03 (Asia/Singapore)
> Target: 500-item, subject-stratified holdout manifest
> API/network budget: 0
> Candidate content may be processed only by the sealed key-reconstruction code
> Human inspection of candidate question/gold/labels: forbidden
> No auditor execution in this phase

## 0. Claim and terminology

The only permitted claim is:

> The selected items were held out from the enumerated, locally recorded
> BenchAudit development runs and threshold-selection artifacts available at
> the frozen cutoff.

Do not use `unseen`, `model-unseen`, `never seen`, `clean`, or `held out from all
system development`. Model pretraining exposure is neither identifiable nor
relevant to this instrument-evaluation split. Unrecorded human access and
external artifacts remain outside the mechanical claim.

The output manifest is not itself an evaluation result. Detection thresholds,
methods, prompts, metrics, and review rules must be frozen in a later protocol
before the holdout is audited.

## 1. Why V1 is not extended

V1 scanned every file in the repository. That scope asked whether an item ID
occurred anywhere, rather than whether an artifact could have caused recorded
development exposure. It produced a useful exact-ID inventory but stopped on
two `synctex.gz` files.

V1 also unpacked ZIP-magic containers, including XLSX/DOCX/PPTX, but treated PDF
and Parquet as ordinary byte streams. Their compressed internal content was not
semantically expanded and was not marked unsupported. Therefore V1 must not be
described as exhaustive full-content coverage even apart from the two gzip
stops. V1 outputs remain immutable.

V2 narrows the evidence surface by causal relevance fixed before execution; it
does not add an open-ended document parser collection.

## 2. Frozen cutoff and inputs

| Object | Frozen value |
|---|---|
| Repository cutoff containing A0 result | `cdc3ae1` |
| Full MMLU-Redux dataset SHA-256 | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |
| V1 inventory SHA-256 | `a416ea4a2e3dd41865d6f0f12db46df67db91b324a7a2b6273fa66c21b5d0f10` |
| A0 availability SHA-256 | `15b777f4049799ed8538d00bbfb11a7847b9fc32d0c48ece187307308ac6f9e1` |
| A0 receipt SHA-256 | `ee2b178132191c5c81eb72322a0ca6f2f304c0e2ed351841b3039769e5c46263` |
| A0 run-bound union count | 1,087 |
| A0 run-bound union SHA-256 | `f06faeb336ef5241d76ef2342a2810d3bf460671bcfdb9d2b273a4033fdd077a` |
| Selection seed | `20260803` |
| RNG | NumPy `Generator(PCG64)` |
| Final sample size | 500 |

The V2 implementation commit may follow the protocol commit but may change only
the V2 scanner, tests, and new V2 outputs. The cutoff artifact graph remains the
state at `cdc3ae1`; protocol/implementation files created afterward are not
development exposure evidence.

## 3. Causally relevant evidence graph

The scanner admits only these code-owned node/edge types:

1. benchmark input or mutation input used by a recorded audit report;
2. frozen sampling/mutation manifest that maps that input to source item IDs;
3. JSON audit report whose `run_metadata.llm.cache_path` names a cache;
4. source-identity/coverage-ledger rows that enumerate audited item IDs;
5. digest-only JSONL cache named by such a report;
6. report-bound implementation manifest and its exact Git blobs;
7. the historical Git commit named by the report when prompt-source hashes
   match, or an explicitly empirical golden-key reconstruction otherwise.

Arbitrary attachments, papers, Office documents, PDFs, Parquet files, LaTeX
build artifacts, datasets for other benchmarks, and caches not connected to an
MMLU report are outside the graph. This is a semantic scope decision, not a
file-extension allowlist.

Discovery starts from every JSON report present at cutoff. A report is MMLU
relevant if its source identity/input hash matches a frozen MMLU input or its
audited/source IDs intersect the 5,700-ID universe. Every LLM cache reachable
from such a report must appear in the A0 seven-case manifest. A newly discovered
relevant cache, missing report, cache-path conflict, or hash drift yields
`NOT_IDENTIFIABLE_SCOPE_DRIFT`; it may not be added after inspection.

## 4. Authoritative forward upper bound

For each of the seven A0 cases, rederive the possibly touched source-item set:

- modern reports: unique `coverage_ledger.item_id`, whose count must equal
  `source_identity.audited_rows`;
- mutation experiments: report input IDs must exactly equal
  `mutation_manifest.mutated_item_id`, then map to `source_item_id`;
- multiple reports sharing a cache: take the union, with the final report's
  `cache_entries` equal to the cache's distinct key count.

Every source ID must belong to the frozen 5,700-ID universe. The union must be
exactly 1,087 items with the frozen A0 hash. This forward set is authoritative:
all 1,087 items are excluded regardless of reverse-key results.

If the count/hash differs, stop. Do not repair a path, infer a source item from
a mutated suffix, or replace a missing report.

## 5. Reverse cache-key cross-check

Reverse reconstruction is supporting evidence, not the authority for early
runs whose prompt snapshot was not attested.

### 5.1 Historical formulas

Support exactly the two schemas observed and golden-tested by A0:

- `legacy_minimal`: `{model, temperature, system, user}`;
- `legacy_extended_without_schema_version`:
  `{model, base_url.rstrip('/'), temperature, max_tokens, dry_run,
  response_format, thinking, system, user}`.

The cache rows themselves do not store a schema version. Schema selection is
bound to the report's historical prompt commit and must reproduce the A0 golden
initial key before any candidate key is computed. Unknown or mixed schemas fail
closed.

### 5.2 Prompt-source evidence grades

- Four cases: `llm_client.py` and `llm_auditor.py` must match the report-bound
  implementation manifest and historical commit. These are `attested_snapshot`.
- Three 2026-07-13 cases: the report predates implementation manifests. The
  recorded dirty commit reproduces the golden initial key, but the snapshot is
  `empirical_unattested_snapshot` and must remain labelled as such.

The early cases are safe only because their authoritative forward bounds are
complete. Reverse absence from them may not independently certify an item.

### 5.3 Candidate reconstruction

After the deterministic subject orders in §6 are frozen in memory, reconstruct
only the initial prompt for each LLM auditor/configuration recorded by each
case. Candidate benchmark fields, including declared gold when the historical
prompt requires it, may be decoded only inside this sealed process. Verified
gold and audit labels must be stripped before prompt construction and may not be
used for selection or key computation. Stable outputs may contain only item ID,
key-schema ID, cache case, computed key, and hit/miss. Question text, choices,
gold, verified gold, audit labels, prompt text, and cache responses must never
be emitted or logged.

A reverse hit excludes the candidate even if it was absent from the forward
set. A miss means only “not found under this reconstructable historical initial
prompt format.” It is not proof of absolute non-exposure. Downstream cascade
prompts need not be reconstructed: any successful cascade begins with its
deterministic initial call; forward bounds cover failed/uncached attempts.

No API client may be instantiated. Network attempts must remain zero.

## 6. Deterministic subject-stratified selection

Let `P` be the 5,700 IDs minus the authoritative 1,087 forward-bound IDs. The
selection pass uses a selective byte extractor for only `id` and
`metadata.subject`; it must not JSON-decode whole rows or extract audit labels,
`verified_gold`, or other truth fields. The later sealed prompt-reconstruction
pass follows §5.3 and cannot alter the already-frozen order or quotas.

Allocate 500 subject quotas by Hamilton largest remainder:

1. exact quota `q_s = 500 * |P_s| / |P|`;
2. assign `floor(q_s)`;
3. distribute remaining slots by descending fractional remainder, breaking
   ties by subject string.

For each subject in sorted order, use the single frozen PCG64 generator to
permute that subject's IDs. Screen in that frozen order. Exclude forward-bound
items (a consistency check) and reverse-key hits; take the first passing IDs
until the subject quota is filled. A rejected item is replaced only by the next
ID in the same frozen subject order. No cross-subject substitution is allowed.

The choice of 500 is fixed before selection. At an illustrative 10% defect
prevalence it yields roughly 50 positives and a binomial prevalence standard
error of about 1.34 percentage points; this is a budget/precision compromise,
not a result-dependent power claim.

If any subject cannot fill its quota, outcome is `INSUFFICIENT_CLEAN_SAMPLE`.

## 7. Manifest and disclosure

The final manifest records:

- source dataset path, SHA-256, byte size, and 5,700-row count;
- cutoff commit, A0 hashes, V2 scanner/protocol hashes;
- seed, RNG, allocation algorithm, subject quotas;
- ordered selected IDs and source row indices;
- selected-ID list SHA-256;
- forward exclusion count/hash;
- reverse-screen cases, evidence grades, hit counts, and excluded IDs;
- explicit wording boundary from §0.

It must not contain question text, options, gold, verified gold, audit labels,
cache responses, prompts, or result-dependent statistics.

The receipt separately records all input/report/cache/manifest/code hashes,
golden-key results, zero API/network,
`candidate_truth_fields_used_for_selection=false`,
`candidate_truth_fields_emitted=false`, and output hashes.

## 8. Outcomes

- `PASS_RECORDED_DEVELOPMENT_HOLDOUT_500`: all seven forward bindings and A0
  golden controls reproduce; no relevant artifact is missing/new; all subject
  quotas fill; a 500-ID manifest is produced.
- `NOT_IDENTIFIABLE_SCOPE_DRIFT`: relevant artifact graph differs from A0 or
  cutoff hashes.
- `NOT_IDENTIFIABLE_CACHE_BINDING`: a forward binding, schema control, prompt
  snapshot, cache, or golden key cannot be reproduced.
- `INSUFFICIENT_CLEAN_SAMPLE`: deterministic within-subject replacements cannot
  fill 500 quotas.

No partial manifest is publishable under a non-PASS outcome.

## 9. Required tests

At minimum:

1. artifact discovery finds all seven and rejects an eighth relevant cache;
2. unrelated benchmark caches and arbitrary attachments are excluded by graph
   semantics rather than extension;
3. cache/report path and entry-count mismatch fail closed;
4. coverage-ledger/source-identity count mismatch fails closed;
5. mutation input IDs and mutation manifest must bijectively match;
6. forward union reproduces count 1,087 and frozen hash;
7. both historical key formulas have pinned golden tests;
8. unknown/mixed formula or golden miss fails closed;
9. attested and empirical-unattested prompt grades cannot be interchanged;
10. reverse hit excludes; reverse miss does not acquire a stronger evidence
    label than `reconstructable_format_miss`;
11. no downstream prompt is required before the initial key is checked;
12. candidate prompt/truth/cache-response bytes never enter stable outputs;
13. Hamilton quotas sum to 500 with lexical tie-breaks;
14. within-subject replacement is deterministic and never crosses subjects;
15. insufficient subject reserve fails without changing quotas;
16. same inputs/seed in two empty directories produce byte-identical manifest,
    diagnostic, and stable receipt;
17. any API/network attempt, candidate verified/audit-truth-field use in
    selection or key construction, or any candidate field emission fails closed;
18. a fresh clone containing all committed required artifacts runs the tests;
    ignored caches are supplied only through their receipt-bound absolute input
    root and must match hashes.

## 10. Stop and post-selection discipline

After a PASS manifest is committed:

- do not inspect selected questions, gold, verified labels, or audit labels;
- do not run the current or historical auditor until the evaluation protocol,
  thresholds, metrics, and methods are separately frozen;
- do not replace a selected item except under a new protocol with a disclosed
  reason unrelated to its truth or audit result;
- do not call the split `unseen`; use the exact scoped wording in §0.

V2 is the final contamination-protocol iteration for this planned holdout. Any
non-PASS result closes this MMLU split rather than triggering a V3 scope or
parser expansion.
