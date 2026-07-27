# GDPval proof generalization assessment

Date: 2026-07-27  
Status: implementation gate for Spec P2

## Decision

Do **not** replace all 13 GDPval promotion triples with one generic
field-contradiction proof. Source inspection shows that the 13 entries do not
share one proof obligation. Treating them as equivalent would make the
confirmation policy less precise.

The safe refactor target is the declarative artifact-contract subset only.
The remaining proofs must retain their distinct prerequisites and replay
bases.

## Proof partition

| Family | Existing replay entries | Generalizable as declarative field-role consistency? |
|---|---:|---|
| Exact artifact filename | 4 | Yes |
| Declared deliverable format | 2 | Yes |
| Artifact manifest structure and pinned URIs | 1 | Partly; separate manifest predicate |
| Pretty/JSON rubric representation | 1 | No; parser and serialization equivalence |
| Record schema | 1 | No; closed schema predicate |
| Duplicate rubric identifiers | 1 | No; uniqueness predicate |
| Rubric column relations | 1 | No for confirmed; currently review-only without workbook grounding |
| Task/rubric workbook headers | 2 | No; immutable external XLSX replay |

The six filename/format entries already share a common implementation inside
`_contract_facts`: extract a typed claim, resolve the declared artifact role,
compare it with a manifest observation, and emit a replayable fact. Their
remaining GDPval-specific part is how raw fields are assigned the roles
`task`, `rubric`, `reference_manifest`, and `deliverable_manifest`.

## Safe abstraction contract

A future general detector may replace that six-entry implementation only if:

1. field roles come from an authenticated adapter/mapping receipt, not from
   field-name guessing;
2. the claim grammar remains deterministic and fail-closed;
3. observed manifests are content-bound to the live item;
4. each emitted atom states its predicate kind and role prerequisites;
5. the promotion registry preserves exact proof contracts rather than granting
   authority to the checker name;
6. old and new facts are byte-for-byte equivalent after canonical ordering on
   the frozen GDPval corpus;
7. all six old producer paths are removed only after that equivalence test.

## Falsification gate

Before deleting any GDPval path, run both implementations on the same pinned
revision and compare canonical tuples:

```text
(item_id, defect_type, evidence_level, atom, confirmation_capable)
```

Acceptance requires:

- no missing facts;
- no added confirmed facts;
- identical atom payloads;
- identical promotion outcome after live replay;
- zero changes to the representation, schema, identifier, column, and workbook
  proof families.

If exact equivalence fails, retain the existing implementation. Reducing a
source-code count is not worth weakening a proof boundary.
