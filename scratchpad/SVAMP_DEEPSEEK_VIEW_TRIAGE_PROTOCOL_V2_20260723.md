# SVAMP-Platinum DeepSeek-view triage protocol — V2 amendment

Frozen after the five-item smoke test and before any full-dataset collection on
2026-07-23.

This amendment inherits
`SVAMP_DEEPSEEK_VIEW_TRIAGE_PROTOCOL_20260723.md` except for the changes listed
below.  The original protocol SHA-256 is
`f89c0acb66c64d5de46a116f8421640b5de5232ea696cc94c2d47b27b2a800a9`.

## R0 smoke-test observation

Five items × eight views produced:

- non-thinking: 20/20 valid responses;
- thinking: 14/20 valid responses;
- six thinking responses ended with `finish_reason=length`, empty final
  content, and approximately 1,160–1,285 reasoning characters.

The failures are infrastructure truncations, not wrong answers.  Keeping a
300-token cap would make missingness depend on item reasoning length and would
violate the frozen ≥95% completeness gate.

## Only parameter amendment

- Non-thinking views retain `max_tokens=300`.
- Thinking views use `max_tokens=1200`.
- Already valid R0 responses are retained.  The six failed pairs are retried
  under the amended cap; all previously unattempted thinking pairs use 1200.
- The response schema, prompts, model, temperature, label split, metrics, and
  decision rule are unchanged.

## Persistent budget enforcement

The exact provider-attempt limit remains 1,300 attempts per mode.  Unlike the
R0 implementation, V2 carries API-attempt counters across resumed processes:

1. read cumulative attempts from `collection_metadata.json`;
2. set the new client's cap to `1300 - cumulative_attempts`;
3. add current-run counters back to the cumulative ledger.

Resolved failed pairs are removed from the active error file but remain
documented by this amendment and by the R0 metadata hash when available.

The full collection must stop rather than exceed either persistent cap.

