# SVAMP response-first semantic cascade protocol

Frozen after the DeepSeek-view response experiment and before semantic-auditor
calls on 2026-07-23.

## Question

Can an inexpensive behavior-first cascade reduce full-dataset LLM auditing
while improving the review order of the highest-risk SVAMP items?

This is a follow-up diagnostic on a dataset whose aggregate labels have already
been inspected.  It is not a pristine holdout and cannot revise the frozen
headline of the preceding experiment.

## Fixed selection

- Select exactly the top 100 of 300 items by frozen
  `deepseek_view_error_rate`.
- Ties are ordered by item ID.
- Selection reads `triage.json` and `public_items.jsonl`; it must not read
  `labels.json`.
- Only the selected public task, gold, output contract, and evaluator may be
  sent to DeepSeek.

## Semantic pass

- Model: `deepseek-v4-flash`, thinking disabled.
- BenchAudit auditors: `gold,question,quantity,event`.
- Gold evidence mode: `cascade`.
- One pass per enabled auditor; no multi-vote.
- Dedicated cache; 24 workers; 2,000 maximum output tokens.
- Exact API attempt accounting is required.

No LLM-backed finding may become `confirmed`; semantic evidence remains
`review`.

## Frozen ranking

Compare:

1. behavior error-rate ranking over all 300;
2. semantic-gated ranking:
   - selected items with a `priority` semantic candidate first;
   - remaining selected items second;
   - unselected items third;
   - within every group, retain behavior error-rate order.

This lexicographic rule has no fitted weights.

## Metrics and decision

Report full-300 AP, P@20/50/100, R@50/100, semantic finding yield, API calls,
tokens, and the fraction of the dataset sent remotely.

Call the cascade useful only if:

1. semantic-gated AP improves by at least `+0.020`;
2. P@20 and P@50 do not decrease;
3. no model-based finding is automatically confirmed;
4. only 100/300 items are sent to the semantic pass.

If it fails, keep behavior ranking as triage only and use semantic output for
case explanation rather than automatic reranking.

