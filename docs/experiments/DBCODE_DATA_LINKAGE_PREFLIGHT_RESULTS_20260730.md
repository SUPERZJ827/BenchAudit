# DBCode data-linkage preflight results

Date: 2026-07-30

Decision: **`NOT_IDENTIFIABLE_DATA_LINKAGE`**

## 1. Purpose

Before writing a SQL-function adapter, this preflight measured whether the
collected DBCode artifacts could be joined by stable item identity:

```text
task → candidate → declared reference → score → execution trace
```

It inspected schema keys, allowlisted identity/status values, relative
filenames, counts, and hashes only. It did not emit task text, code, raw item
IDs, trajectories, or patches.

## 2. Result

| Family | Candidate records / IDs | Score records | Task IDs | Reference IDs | Score IDs | Trace IDs | Candidate∩trace | Full chain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SQLite | 321 / 79 | 321 | 79 | 0 | 0 | 5 | 5 | **0** |
| PostgreSQL | 1,092 / 286 | 1,092 | 286 | 0 | 0 | 6 | 6 | **0** |

Frozen full-chain threshold: **30** per family.

Neither family is close to the execution-trace requirement. Candidate files
cover many task IDs, but the archived trajectories represent only five SQLite
and six PostgreSQL identities under the frozen filename grammar.

## 3. Robustness to schema aliases

The aggregate schema diagnostics revealed two previously unseen keys:

- `origin_code`, plausibly a declared-reference field;
- `is_success`, plausibly a score/status field.

The protocol explicitly prohibits adding aliases after observing the result,
so they remain unrecognized in the frozen receipt. This does not drive the
No-Go:

- SQLite `candidate ∩ trace = 5`;
- PostgreSQL `candidate ∩ trace = 6`.

Even if every candidate ID were optimistically granted both a reference and a
score, the full chain could not exceed 5 or 6, still far below 30.

The high exact-duplicate candidate-triple counts are not interpreted as
dataset duplication. Candidate records come from several model/dependency
files, while the frozen scanner does not infer missing model/variant metadata
from filenames. They are diagnostic only and do not affect the linkage gate.

## 4. Decision and next action

No A1 DBCode adapter protocol will be written from the current artifact
package. Doing so would require reconstructing missing trace-to-item coverage
or inventing joins that the archived data does not attest.

The DBCode line may be reconsidered only if a new versioned package provides:

- an explicit task/reference/score schema receipt;
- a trace-to-item mapping;
- at least 30 complete executable chains;
- hashes binding those mappings to the collected artifacts.

That must begin with a new A0 protocol and cannot reinterpret this receipt.
The project should now move to the separately planned repair-identifiability
study rather than hand-building a DBCode adapter around six traced functions.

## 5. Safety and reproducibility

| Property | Result |
|---|---:|
| In-scope files | 218 |
| In-scope bytes | 126,374,595 |
| Identity conflicts | 0 in both families |
| Candidate/SQL executions | 0 / 0 |
| LLM/API calls | 0 |
| Raw content emitted | false |
| Raw item IDs emitted | false |
| Synthetic scanner tests | 6 passed |
| Full repository tests | 789 passed |
| Deterministic repetitions | byte-identical under `PYTHONHASHSEED=1,7` |

Hashes:

| Artifact | SHA-256 |
|---|---|
| Protocol | `95f215b6b1e6814d37b5047011e37bc02a9cf45eb6d421247a102f81d4da3fd4` |
| Scanner | `3a6c3e3064ec1ae8a133fa23649e56106a015fdfab3f596d9723d224a1c65e5a` |
| Source manifest | `e4e24e4264b2d36138a1e185f62a361b87b1d0938f8699624a875de8674809d0` |
| Stable summary | `b5a407f421ae546deed02121d4ab43a2f6c570e5fc40a4f1434ed84182f1147b` |
| Receipt file | `90be01692ee71da926579d7321e4aee0d24523c134184d6fbba43278643b4b70` |

The source dataset is not committed. Independent re-execution requires the
same 218-file package and verification of the source-manifest hash.
