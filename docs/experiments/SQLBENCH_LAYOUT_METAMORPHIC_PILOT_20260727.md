# SQLBench SQL layout metamorphic pilot

Date: 2026-07-27  
Branch: `research/generalized-confirmation-metamorphic-20260727`

## Question

Can the type-scoped `sql_layout` metamorphic relation replay harmless layout
changes without creating false evaluator-flip candidates on a real collected
result set?

This is a **pressure test of the relation**, not a confirmed audit of the
official SQLBench evaluator. The available SQLGlot 30.2.1 sidecar is an
auxiliary syntax parser and does not establish execution correctness or
translation equivalence.

## Frozen transformations

For every parser-decidable SQL answer:

1. add whitespace before the first token;
2. add whitespace after the final token;
3. add one fixed, non-hint block comment before the first token.

The original SQL bytes are preserved verbatim. SQL tokens are never rewritten.
No LLM is used.

## Results

| Quantity | Value |
|---|---:|
| Input result files | 56 |
| Model answers | 4,448 |
| Parser-valid baselines | 3,136 |
| Parser-invalid baselines | 1,234 |
| Indeterminate baselines | 77 |
| Empty baselines | 1 |
| Completed metamorphic variant runs | 13,113 |
| Verdict flips | **0** |
| LLM calls | **0** |
| Confirmation-eligible findings | **0 by design** |

The 13,113 runs equal 4,371 decidable answers × 3 frozen transformations.

Reference replay is also a warning against overclaiming parser evidence:
among 550 unique reference SQL strings, SQLGlot marked 470 valid, 66 invalid,
and 14 unsupported/fallback. Therefore parser rejection alone is not evidence
that a benchmark answer is wrong.

## Reproducibility

- SQLGlot version: `30.2.1`
- Input manifest SHA-256:
  `027314c1335ce3943593e9b01ae376ff5c33abbbf6466aa4ac3d477a5c11fca3`
- Sidecar script SHA-256:
  `cceb29586bcf47902e0e721ff9a3094d5dd45f7dd92312062f2cd65ccdeed9d0`
- Two independent output files had identical SHA-256:
  `2bf9a6fe63687421478c76082d3b25dc5e393905979319273ecd2d2fa5abd1a2`

Reproduction command:

```bash
PYTHONPATH=/path/to/sqlglot-30.2.1:. \
python scripts/run_sqlbench_metamorphic_pilot.py \
  --dataset-root /path/to/SQLBench/SQL_Dialect_Translation \
  --sidecar-script /path/to/validate_syntax_sidecars.py \
  --output /tmp/sqlbench_metamorphic_pilot.json
```

## Conclusion

The SQL relation passes this zero-flip stress test and is safe to retain as an
opt-in typed relation. The north-star goal is **not met**: confirmation still
requires an official executable evaluator plus independently attested
transcripts.
