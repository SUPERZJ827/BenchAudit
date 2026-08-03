# MMLU-Redux deterministic mechanical-defect full-scan protocol

> Frozen: 2026-08-03 (Asia/Singapore)  
> Status: protocol only; no 5,700-item rule result had been computed when frozen  
> Budget: API 0, network 0, LLM 0  
> Parent plan commit: `c126b7e`  
> Parent plan SHA-256: `a9e0f8632ea249861ec464d700d1063f940da1519f5ecf57679f3c67bc80dadb`

## 0. Question and claim boundary

This experiment asks:

> Across the frozen 5,700 MMLU-Redux records, how many items contain one of
> three narrowly defined, deterministically replayable construction defects:
> duplicate choices, an unresolvable declared answer label, or an empty choice?

It does not estimate the total benchmark defect rate. It does not establish
that a hit changes a model score or changes the intended correct answer. It
does not evaluate the production BenchAudit method set, and it does not
authorize adding any rule to that set.

The strongest allowed interpretation of an `ok` hit is:

> The mechanical construction defect was outside the published reannotation
> label for this item and can be covered cheaply by a deterministic check.

Do not say that human annotation is poor. MMLU-Redux annotators primarily
judged answer correctness; the three construction checks need not have been
part of their explicit task.

## 1. Frozen inputs and population

| Object | Frozen value |
|---|---|
| Dataset | `/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl` |
| Dataset SHA-256 | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |
| Dataset bytes | `4,505,750` |
| Dataset rows | `5,700` |
| Exposure inventory | `reports/mmlu_holdout_contamination_inventory_20260803/inventory.json` |
| Exposure inventory SHA-256 | `a416ea4a2e3dd41865d6f0f12db46df67db91b324a7a2b6273fa66c21b5d0f10` |
| A0 availability receipt | `reports/mmlu_cache_binding_a0_20260803/availability.json` |
| A0 availability SHA-256 | `15b777f4049799ed8538d00bbfb11a7847b9fc32d0c48ece187307308ac6f9e1` |
| Recorded-development item count | `1,087` |
| Recorded-development sorted-ID SHA-256 | `f06faeb336ef5241d76ef2342a2810d3bf460671bcfdb9d2b273a4033fdd077a` |
| Remaining item count | `4,613` |
| Remaining sorted-ID SHA-256 | `28915b353b27ef6f1a71283540830fd70dd4aa0ed87b7d259fa47359e477ebff` |
| Python | `3.10.12` |
| Unicode database | `13.0.0` |

The sorted-ID hash is SHA-256 over UTF-8 item IDs in lexical order, joined by
LF and terminated by one LF. The inventory's global outcome was
`NOT_IDENTIFIABLE_SCAN_COVERAGE`, but its explicit 1,087-item exposure list is
admitted here only after its count and sorted-ID hash reproduce the independent
A0 forward-union count and hash. Unsupported arbitrary repository attachments
are irrelevant to this full-dataset construction scan.

Every source row must have exactly these top-level properties needed by the
scan: a unique string `id`, string `question`, list `choices`, string `gold`,
mapping `evaluator`, and mapping `metadata`. Every choice must be a string;
`metadata.subject` and `metadata.error_type` must be strings. The evaluator
must be exactly `{"type": "multiple_choice"}` and there must be 4 choices.
Schema drift or a malformed JSONL row stops the whole scan.

Redux labels are partitioned before reporting:

- `ok`;
- explicit defect: `wrong_groundtruth`, `bad_question_clarity`,
  `multiple_correct_answers`, `no_correct_answer`, or
  `bad_options_clarity`;
- abstention: `expert`.

No abstention may be silently counted as either `ok` or an explicit defect.

## 2. Frozen rules

All comparisons operate on source `choices`; no question semantics, verified
gold, source evidence, or model output enters a rule.

### 2.1 R1: duplicate choices, cumulative tiers

For each choice string `x`, define:

1. `T1(x)`: the exact UTF-8 content bytes of `x`. No trimming or Unicode
   normalization.
2. `T2(x)`:
   - `unicodedata.normalize("NFKC", x)`;
   - Python `str.casefold()`;
   - replace every maximal run of characters for which `str.isspace()` is true
     with one ASCII space;
   - remove an ASCII space at either boundary.
3. `T3(x)`: start from `T2(x)` and repeat until fixed:
   - remove boundary ASCII spaces;
   - remove the maximal leading and trailing runs whose Unicode general
     category begins with `P`;
   - remove newly exposed boundary ASCII spaces.

The Python and Unicode-database versions in §1 are part of the frozen
semantics. A normalized empty string is excluded from R1 comparison at that
tier; R3 owns actual empty/whitespace choices, and punctuation-only choices are
not converted into duplicate findings merely because T3 erases them.

At tier `Tk`, R1 triggers when a non-empty normalized value occurs at two or
more distinct choice indices. Duplicate groups are maximal groups of equal
values and indices are zero-based, unique, and ascending.

The tiers are cumulative and must all be reported:

- a T1 hit is necessarily recorded at T1, T2, and T3;
- a T2-only hit is recorded at T2 and T3;
- a T3-only hit is recorded only at T3.

No tier may be selected as the sole headline after seeing results. The report
must show T1, T2, and T3 separately, plus the disjoint increments
`T1`, `T2_only`, and `T3_only`.

### 2.2 R2: declared gold label is not uniquely resolvable

R2 is bound to the frozen MMLU four-choice label contract. It does not attempt
free-form text-to-choice matching.

1. `gold` must be a string.
2. Apply Python `str.strip()` and `str.upper()`.
3. The result must be exactly one of `A`, `B`, `C`, `D`.
4. The corresponding zero-based index must exist and its raw choice must not
   be empty under R3's definition.

R2 triggers for a missing/non-string/empty/out-of-domain label, a label whose
index is outside the explicit choice domain, or a label pointing to an empty
choice. Under the frozen unique `A`–`D` label grammar, “maps to multiple
indices” is structurally unreachable. If a future dataset introduces aliases,
compound gold, or a text-valued answer contract, this scanner fails schema
validation rather than widening R2 after inspection.

R2 does not claim that the declared gold is factually wrong. It proves only
that the declared label cannot select one usable choice under the frozen
contract.

### 2.3 R3: empty choice

R3 triggers when at least one raw choice is empty after Python `str.strip()`.
All zero-based empty-choice indices are recorded. Non-string choices are schema
failures, not coerced to text and not skipped.

## 3. Prior knowledge and non-activation

R1 is partially informed: `mmlu-redux-public_relations-36` was already known to
contain a byte-identical duplicate pair at indices `[2, 3]` in the 1,000-item
development subset. The earlier mechanical receipt is:

`reports/mmlu_redux_ok_mechanical_20260803/receipt.json`  
SHA-256:
`2634748bb9cbbf67efeac9bf9cd94166709c0ef390c8546052b4063f67a92365`

This known item is a frozen positive control: it must hit R1 at T1, T2, and T3,
retain Redux label `ok`, and belong to the 1,087-item development partition.
Failure stops the scan. It is not a blind discovery and must be identified as
such in the result.

R2 and R3 are declared not previously run over this population. The receipt
must use the exact fields:

```json
{
  "r1_rule_definition_partially_informed": true,
  "r1_known_positive_count_before_freeze": 1,
  "r2_previously_run": false,
  "r3_previously_run": false
}
```

This experiment may add only a standalone script, tests, protocol/result
documents, and new scan artifacts. It must not modify `benchcore/**`, CLI
wiring, production manifests, the frozen 18-method Platinum protocol, or any
historical report. `production_activation=false` is mandatory. A later
activation requires a separately frozen protocol and a newly frozen blind-test
method set.

## 4. Counting and evidence semantics

`findings.jsonl` contains one canonical record per `(item_id, rule, tier)`.
R1 therefore may contribute up to three records for one item. R2 and R3 use
`tier=null`.

Each record contains:

- item ID, subject, Redux label, and partition (`development_1087` or
  `remaining_4613`);
- rule and tier;
- zero-based implicated indices;
- raw implicated choice text;
- rule-specific normalized text and its SHA-256 where applicable;
- a SHA-256 of the complete frozen input fields used by the rule.

Records are sorted by `(item_id, rule, tier order)` and serialized as canonical
JSON lines with UTF-8, sorted keys, compact separators, and LF termination.

All table cells are counts of **distinct item IDs**, never JSONL record counts.
The report must include:

1. R1 T1, T2, T3 counts and disjoint T1/T2-only/T3-only increments;
2. R2 and R3 counts;
3. for each row: total, Redux `ok`, explicit defect, and `expert` abstention;
4. the union count across R1/R2/R3 and a rule-overlap table, preventing
   double-counting;
5. the same counts separately for `development_1087` and `remaining_4613`;
6. a complete itemized list of every Redux-`ok` hit with raw implicated choices.

## 5. Execution, outputs, and determinism

The standalone scanner reads only the frozen dataset, inventory, A0
availability, protocol, and earlier R1 receipt. It must not instantiate an API
client, read API-key environment variables, access the network, or import
`benchcore.llm_client`.

Each of two independent runs uses a new empty output directory. Both runs must
produce byte-identical:

- `findings.jsonl`;
- `REPORT.md`;
- `receipt.json`.

The published directory is
`reports/mmlu_redux_mechanical_scan_20260803/`.

The stable receipt contains input hashes/sizes/counts, protocol and scanner
hashes, interpreter/Unicode versions, partition hashes, rule versions, output
hashes, zero API/network/LLM/threshold flags, non-activation flags, and stable
counts. It must not contain wall-clock timestamps, PID, temporary paths, or
elapsed time.

Each run also emits `raw_run.json`, which records start/end timestamps, PID,
elapsed time, invoked paths, and the stable receipt hash. Raw logs are expected
to differ and are excluded from the byte-identity gate. This separation
resolves the plan's simultaneous requirements to record execution time and to
make the evidentiary receipt reproducible.

The scanner first builds all outputs in memory. Any row error produces
`SCAN_INCOMPLETE`, names the row number and reason on stderr/raw execution state,
and publishes none of `findings.jsonl`, `REPORT.md`, or a PASS receipt. No row is
skipped or coerced.

Outcomes:

- `SCAN_COMPLETE`: every row validates, every rule runs on all 5,700 rows, the
  positive control passes, stable outputs are published, and two independent
  runs match byte for byte;
- `SCAN_INCOMPLETE`: any binding, schema, parsing, rule-coverage, positive
  control, output-integrity, or determinism condition fails.

## 6. Required tests

At minimum:

1. byte-identical choices hit R1 T1/T2/T3;
2. case/Unicode-compatibility/whitespace-only differences miss T1 and hit
   T2/T3;
3. boundary-punctuation-only differences miss T1/T2 and hit T3;
4. normalization that becomes empty does not create an R1 hit;
5. gold labels A–D map uniquely; missing, empty, out-of-range, and empty-target
   gold trigger R2;
6. empty and Unicode-whitespace-only choices trigger R3;
7. a clean item triggers no rule;
8. overlaps do not inflate distinct-item union counts;
9. `expert` remains a separate reporting class;
10. malformed row, duplicate ID, schema drift, or unknown Redux label fails the
    entire scan;
11. the frozen positive control hits all three R1 tiers;
12. two empty output directories yield byte-identical stable outputs;
13. scanner source contains no LLM/API/network path and no production module
    imports;
14. a fresh clone runs all constructive tests and independently verifies the
    committed findings/report/receipt hashes; external-dataset integration may
    be explicitly skipped only when the frozen dataset artifact is absent.

## 7. Publication wording

After `SCAN_COMPLETE`, report a union of distinct items, not the sum of rule
rows. The public sentence must instantiate `N` and `M` from the receipt:

> In the frozen 5,700-item MMLU-Redux artifact, `N` distinct items contain at
> least one of three preregistered, deterministic construction defects; `M` of
> those items carry the Redux label `ok`. The rules cover only duplicate
> choices, unresolvable declared labels, and empty choices. They do not estimate
> the benchmark's total error rate or establish score impact.

T1, T2, and T3 must remain separately visible. If only T2/T3 adds an item, its
normalization tier must accompany every citation of that item.
