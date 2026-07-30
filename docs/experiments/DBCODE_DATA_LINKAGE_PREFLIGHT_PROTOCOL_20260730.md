# DBCode data-linkage preflight protocol

Date: 2026-07-30

Protocol: `dbcode-data-linkage-preflight-v1-20260730`

Status: **frozen before parsing structured records or implementing a DBCode
adapter**

Branch: `research/dbcode-data-linkage-preflight-20260730`

## 1. Question

Before writing an adapter, determine whether the locally collected DBCode
artifacts can be joined into a replayable per-item chain:

```text
task → candidate → declared reference → score → execution trace
```

This is a data-availability measurement, not a defect audit. It does not decide
whether a candidate is correct and cannot produce a BenchAudit finding.

## 2. Frozen roots

The preflight covers:

- `SQLite_Function_Code_Generation`;
- `PostgreSQL_Function_Code_Generation`.

Both are resolved below an operator-supplied `--artifact-root`. No absolute
machine path may be embedded in library code or committed receipts.

Only files under the following relative families are in scope:

- `different_model_outputs/**`;
- `scores/per_item_status.csv`;
- `scores/score_summary.csv`;
- `logs_and_execution_traces/**`;
- benchmark-level `README.md`;
- `HARNESS_AND_VARIANTS.md`.

## 3. Allowed reads

The scanner may read:

- relative paths, file sizes, extensions, and SHA-256 values;
- CSV headers and allowlisted ID/model/variant/status fields;
- JSON container shapes and object key names;
- values of allowlisted identity fields;
- whether task/reference/candidate fields are present and non-empty;
- trace identity parsed from filenames only.

The scanner must not emit or retain:

- task text;
- candidate code;
- reference code;
- prompts, rationales, trajectories, tool messages, or patches;
- database contents;
- raw item IDs;
- raw model outputs.

No SQL, candidate, reference, harness, patch, or trajectory is executed.
LLM/API calls are fixed at zero.

## 4. Frozen structural vocabulary

Identity-key aliases:

```text
item_id, problem_id, task_id, sample_id, case_id, id,
function_name, function, name
```

Model-key aliases:

```text
model, model_id, model_name, generator, agent
```

Variant-key aliases:

```text
variant, dependency_mode, mode, setting, run_type
```

Task-presence aliases:

```text
task, question, problem, prompt, instruction, description
```

Reference-presence aliases:

```text
reference, reference_answer, reference_code, gold, gold_code,
canonical_solution, expected
```

Candidate-presence aliases:

```text
candidate, candidate_code, generated_code, generation, output,
model_output, prediction, response, answer, code
```

Score/status aliases:

```text
score, status, passed, pass, result, verdict, reward
```

Aliases are matched case-insensitively after replacing punctuation with
underscores. The scanner may report previously unseen key names as schema-only
diagnostics, but may not add them to the alias set after seeing the result.

## 5. Structured-record discovery

### CSV

- read the header;
- choose the first identity alias in the frozen order above;
- if none exists, mark the file `id_not_identifiable`;
- read only identity/model/variant/status columns.

### JSON

Records are accepted only when one of these deterministic forms applies:

1. top-level list of objects;
2. top-level object whose exactly one value is a list of objects;
3. top-level object keyed by item ID where every value is an object.

Ambiguous multi-list containers are `record_container_not_identifiable`.

For forms 1 and 2, choose the first identity alias in frozen order. For form 3,
the mapping key is the item ID unless an explicit identity alias disagrees; a
disagreement is an `identity_conflict`.

The scanner records key-name frequencies and component-presence booleans, not
the associated text/code values.

### Execution traces

Trace content is never parsed. A trace identity may be extracted from a
filename only when it matches one of these anchored forms:

```text
..._trajectory_<identity>_<YYYYMMDD>_<HHMMSS>.<ext>
..._<identity>_<YYYYMMDD>_<HHMMSS>_trajectory.<ext>
trajectory_<identity>_<YYYYMMDD>_<HHMMSS>.<ext>
```

Wrapper prefixes such as model or agent names may be removed only when they are
also present as directory or file-level model metadata. If more than one
identity parse is possible, the trace is `trace_identity_ambiguous`.

Patch files do not count as execution traces.

## 6. Aggregate linkage

All identity values are normalized by:

1. Unicode NFKC;
2. trimming;
3. casefolding;
4. collapsing internal whitespace;
5. preserving punctuation and underscores.

The receipt contains only:

- file and record counts;
- unique-ID counts;
- duplicate/conflict counts;
- component-presence counts;
- pairwise join counts and coverage;
- full-chain join count and coverage;
- SHA-256 of each normalized ID set;
- schema key-name frequencies;
- reason counts.

No raw ID or record may appear in output.

Multiple models or dependency variants for one item are expected and are not
identity conflicts. Exact duplicate `(item, model, variant)` records are
reported separately.

## 7. Frozen gate

For each protocol family:

1. candidate unique IDs ≥ 30;
2. score/status unique IDs ≥ 30;
3. IDs with task presence ≥ 30;
4. IDs with declared-reference presence ≥ 30;
5. filename-identifiable execution-trace IDs ≥ 30;
6. full intersection
   `task ∩ candidate ∩ reference ∩ score ∩ trace` ≥ 30;
7. identity conflicts = 0.

Outcomes:

- at least one family satisfies all seven conditions:
  `GO_WRITE_A1_PROTOCOL`;
- neither family satisfies the full-chain gate:
  `NOT_IDENTIFIABLE_DATA_LINKAGE`;
- malformed/ambiguous input prevents a complete aggregate:
  `OPERATIONAL_UNKNOWN`.

Pairwise joins may be reported even when the full-chain gate fails. They do not
override the stop condition.

## 8. Integrity and determinism

The scanner must:

- bind every scanned file by relative path, size, and SHA-256 in a source
  manifest hash;
- bind its own source SHA-256;
- bind this protocol SHA-256;
- produce a stable summary SHA-256;
- produce byte-identical JSON under at least two `PYTHONHASHSEED` values;
- fail closed on missing files, duplicate output paths, malformed structured
  containers, or a changed protocol hash.

## 9. Commit and execution order

1. commit this protocol and gate;
2. independently review the protocol;
3. implement scanner and tests in a second commit;
4. run scanner once;
5. repeat under a different `PYTHONHASHSEED`;
6. commit aggregate receipt and result report separately;
7. write an A1 adapter protocol only if the frozen gate says
   `GO_WRITE_A1_PROTOCOL`.

The gate must not be adjusted after observing linkage counts.
