# MMLU holdout contamination protocol V2: pre-implementation clarification

> Frozen before V2 implementation or candidate selection
> Parent V2 commit: `5aa4f76`
> Parent V2 SHA-256: `a075213c0a2c3bb574ff0fdab2c1948d4e8842f42c26fc9272e072df7025695e`

## Clarification

V2 §5.3 says to reconstruct initial prompts for each recorded case. That applies
only when the candidate item exists in the exact frozen source input used by
that historical run. It does not authorize constructing counterfactual prompts
for items that were absent from the run input.

The seven A0 cases split as follows:

| Reverse applicability | Cases | Rule |
|---|---|---|
| Full 5,700-item source input | `mmlu1000`, `mmlu200`, `mmlu200_comparable` | Reconstruct every applicable initial LLM-auditor key under the recorded prompt snapshot/configuration. |
| Preselected or mutated subset input | `ranking_impact`, `universal_clean10`, `universal_llm10`, `universal_llm10_v2` | Forward input/manifest membership is decisive. Candidates absent from that input are `reverse_not_applicable_forward_excluded`; do not synthesize a hypothetical prompt. |

For the second group, a candidate cannot have generated any call in that run
because it was not an input row. Mutation experiments additionally lack a
defined mutated form for an unselected candidate. Creating one would introduce
a post hoc transformation that never existed historically.

Golden-key controls from A0 remain mandatory for all seven cases: they verify
that each cache/report/key-formula binding is live. They do not make reverse
candidate screening applicable outside the historical input domain.

## Output and tests

V2 diagnostics must record one of these mutually exclusive per-case candidate
states:

- `reverse_hit`;
- `reconstructable_format_miss`;
- `reverse_not_applicable_forward_excluded`.

Add tests that:

1. a full-source case reconstructs candidate keys;
2. a subset-source case never calls a prompt builder for an absent candidate;
3. adding a candidate to a historical subset in memory is rejected as
   counterfactual rather than screened;
4. all seven golden controls still execute before selection.

No other V2 formula, scope, quota, cutoff, output, or stopping rule changes.
