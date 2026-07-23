# Response-triage experiments

This directory contains the frozen protocols and analysis scripts used to
evaluate response-based candidate triage.

## Contents

- `mmlu_subject_grouped_robustness_20260723.py`: compares simple response-error
  fusion with majority-disagreement and psychometric alternatives across
  subject-grouped folds.
- `svamp_deepseek_view_triage_20260723.py`: evaluates correlated prompt views
  as a degraded fallback when independent multi-model responses are absent.
- `svamp_response_semantic_cascade_20260723.py`: evaluates a behavior-first,
  semantic-second review cascade.
- `protocols/`: frozen experiment specifications. Their recorded hashes are
  intentionally checked by the scripts.

Generated outputs and model caches belong under `reports/` or an
`experiments/**/outputs/` directory and are not committed by default.

These scripts are research reproductions, not part of the stable CLI. The
production implementation is `benchcore.response_triage`, exposed through:

```bash
benchcore triage-responses --help
```
