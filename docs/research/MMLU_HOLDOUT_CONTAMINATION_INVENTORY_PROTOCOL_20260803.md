# MMLU holdout contamination inventory: frozen preflight protocol

> Frozen: 2026-08-03 (Asia/Singapore)
> Phase: G0 preflight; no holdout selection in this phase
> API/network budget: 0
> Candidate question, gold, and audit-label inspection: forbidden
> Outcome inspected before freeze: partial (`pilot` manifest union of 1,087 IDs was known)

## 0. Objective and claim boundary

Before selecting any MMLU-Redux holdout, inventory machine-readable evidence that
an item has previously entered this repository's experiments. The result may
define only a **repo-artifact-unseen** candidate pool. It must not claim that a
human never read an item, that an external machine never processed it, or that
an opaque cache key cannot correspond to it.

This phase does not create a holdout manifest, run an auditor, inspect truth
labels, tune a threshold, or make a detection/generality claim.

## 1. Frozen universe

| Input | SHA-256 |
|---|---|
| `/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl` | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |

The scanner must extract only each row's JSON `id` string using a byte-level
selective extractor. It must not JSON-decode a dataset row and must not extract,
hash, log, count, or output question text, answer options, gold,
`verified_gold`, audit labels, or other metadata. The universe must contain
exactly 5,700 unique IDs or the run stops.

## 2. Exposure sources

The scanner runs from repository commit `0eca3e4` or a descendant containing
only the scanner/tests/protocol for this preflight. It inventories two disjoint
surfaces.

### 2.1 Local Git history

Scan every unique Git blob reachable from every local ref returned by
`git for-each-ref`, not only the current branch. Do not rely on a checkout or
the current index. Record the sorted ref names and object IDs, and record the
Git executable version.

### 2.2 Current filesystem snapshot

Recursively scan regular files below the repository root, including tracked,
untracked, ignored, and hidden files. Do not follow symlinks. Exclude only:

- `.git/` (covered by the object scan);
- the output directory of this preflight;
- transient Python/pytest bytecode directories;
- Unix sockets, devices, FIFOs, and other non-regular files.

ZIP members must be scanned from their uncompressed bytes. A corrupt archive,
unreadable regular file, or Git blob read error is fail-closed; it may not be
silently skipped. Other compressed/container formats are listed as unsupported
files and prevent any claim of exhaustive byte coverage.

For every scanned filesystem file record relative path, byte size, SHA-256,
and scan disposition. For Git history record unique blob OID, byte size, and
content SHA-256; do not output blob contents.

## 3. Exact-ID exposure rule

Extract ASCII strings matching the MMLU-Redux ID syntax from every scanned byte
stream and intersect them with the frozen 5,700-ID universe. An item is exposed
if its exact ID appears at least once in either surface. Record only:

- item ID;
- surface (`git_history` or `working_tree`);
- source identifier (blob OID or relative path; ZIP member path if applicable).

Do not output surrounding text. Duplicate appearances are retained in a
source-level table but deduplicated for pool counts.

The candidate pool is `universe_ids - exposed_ids`. This set is not yet a
holdout and may not be passed to an auditor.

## 4. Opaque-cache audit

For every `*.jsonl` file whose nonblank rows have the top-level shape
`{"key": <hex digest>, "response": ...}`, report:

- path and SHA-256;
- entry count and distinct-key count;
- key-length histogram;
- whether any frozen item ID appears literally in its bytes;
- whether a companion machine-readable artifact links its entries to item IDs.

Do not output response bodies. A digest-only cache with no exact item ID and no
companion mapping is `opaque_unlinkable`, not clean. Its existence forces
`absolute_blindness_identifiable=false`. It does not automatically expose all
5,700 items, because that would make the inventory vacuous; instead it is a
separate unresolved risk that must accompany any later holdout claim.

No attempt may be made in this phase to reconstruct historical prompts from
candidate question text or to query a model/cache with candidate items.

## 5. Stable outputs

Write only under `reports/mmlu_holdout_contamination_inventory_20260803/`:

- `inventory.json`: counts, exact exposed IDs and sources, scoped candidate IDs,
  local refs, file/blob scan summaries, unsupported inputs, and opaque-cache
  risks;
- `REPORT.md`: human-readable scoped conclusion;
- `receipt.json`: protocol/scanner/input hashes, commit, environment, zero
  API/network declaration, and output hashes.

Stable outputs contain no timestamp, duration, PID, hostname, absolute temporary
path, question text, gold, label, cache response, or unordered mapping.

## 6. Outcomes

- `PASS_SCOPED_POOL_AVAILABLE`: all required surfaces scanned without error,
  exact exposed/candidate sets partition all 5,700 IDs, and the candidate pool
  is nonempty. This permits drafting a later holdout-selection protocol only.
- `NOT_IDENTIFIABLE_SCAN_COVERAGE`: unreadable/corrupt/unsupported inputs, Git
  object failures, missing refs, or an incomplete universe prevent exhaustive
  scoped coverage.
- `NO_SCOPED_CANDIDATES`: every universe item has exact-ID exposure.

Regardless of scoped outcome, `absolute_blindness_identifiable` must be false if
any opaque-unlinkable cache exists or because unrecorded human exposure cannot
be excluded.

## 7. Integrity tests

At minimum test:

1. selective dataset extraction returns IDs without JSON-decoding rows;
2. duplicate/malformed/missing IDs fail closed;
3. exact IDs are found without emitting surrounding content;
4. substrings and non-universe lookalikes do not count;
5. all local refs, including non-current worktree refs, enter the Git scan;
6. deleted-but-reachable historical blobs are scanned;
7. ignored/untracked/hidden working-tree files are scanned;
8. symlinks are not followed;
9. ZIP members are scanned and corrupt ZIPs fail closed;
10. unreadable/unsupported inputs prevent a pass;
11. digest-only cache entries become `opaque_unlinkable`;
12. cache response bodies never enter outputs;
13. exposed and candidate IDs are disjoint and union to 5,700;
14. two runs on an unchanged snapshot produce byte-identical inventory/report;
15. receipt reports zero API/network attempts and no dataset row JSON decoding.

## 8. Stop conditions

Stop without generating a holdout if any required scan fails, any candidate
dataset row is JSON-decoded, any question/gold/label is emitted, or the output
partition is inconsistent. Do not repair an archive, delete an opaque cache,
drop a ref, narrow scan roots, or exclude an inconvenient artifact after seeing
the result.
