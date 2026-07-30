# SVAMP candidate false-positive regression replay — 2026-07-31

## Outcome

**NOT IDENTIFIABLE FROM THE 2026-07-30 CACHE.**

The exact cache replay on the code that generated the cache passed:

- 661 cache hits;
- 0 API attempts;
- cache bytes unchanged;
- candidate result reproduced exactly: 50 predictions, 33 TP, 17 FP,
  5 FN, precision 0.660, recall 0.868421, F1 0.750.

The frozen cache did **not** replay on `12a6e2c`, the requested current
historical endpoint, or on any earlier candidate commit. Each historical run
had 0 cache hits and 400 `llm_audit_failure` observations. API credentials
were removed from every replay process, so all runs made 0 provider attempts
and the cache remained byte-identical.

Per the preregistered stop rule, the commit-by-commit FP regression search
stopped. The fallback static-only metrics (3 TP / 0 FP / 35 FN) are invalid
for regression attribution and are not reported as model-audit performance.

## Frozen inputs

| Input | SHA-256 |
|---|---|
| `reports/svamp_mainline0730_cache.jsonl` | `117906a173198190d8360bfb360bc1e8afd4788a1c61dd3dde6035b88d96d32a` |
| `experiments/svamp_platinum_pilot100.manifest.json` | `c4ef5ddfb590b210243c0114d7d9eed7a15c2c0a1cf14a98f763cb7d4992d861` |
| `svamp_platinum_all.jsonl` | `f27f8ebf56b33fbeea4b6430f63f24c66adb37bd38a1a8b2bbe62960f588063e` |
| replay configuration | `f617394287a5eb848655196cb1cc2ce1a74d3d2a8e103b74da2e2ea94ff8b1f8` |

The dataset itself is not committed. Its digest is the data receipt.

## Replay table

Metrics are shown only when the full LLM response cache replay was valid.

| Commit | Date | Title | Status | Candidates | TP | FP | FN | F1 | Cache hits | API attempts |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `3b59ae1` on `b450d4e` | 2026-07-31 | generator replay with transport-only V4 compatibility fix | VALID_BASELINE | 50 | 33 | 17 | 5 | 0.750 | 661 | 0 |
| `a58bd5b` | 2026-07-08 | Add rubric strictness review signals | CACHE_KEY_INCOMPATIBLE | — | — | — | — | — | 0 | 0 |
| `6e189b8` | 2026-07-13 | Add artifact-aware automatic benchmark auditing | CACHE_KEY_INCOMPATIBLE | — | — | — | — | — | 0 | 0 |
| `ac99446` | 2026-07-16 | Add adaptive benchmark auditing and objective evidence replay | CACHE_KEY_INCOMPATIBLE | — | — | — | — | — | 0 | 0 |
| `12a6e2c` | 2026-07-23 | Add review-only historical response triage | CACHE_KEY_INCOMPATIBLE | — | — | — | — | — | 0 | 0 |

Only `6e189b8` and `ac99446` modified one of the four nominated post-processing
files inside `a58bd5b..12a6e2c`; the two endpoints were included to make the
failed compatibility boundary explicit.

## Why “same prompt” was insufficient

An exact response cache binds more than the visible prompt. The key schema
also binds request configuration and serialized request identity. In
particular, `ac99446` introduced the newer cache-key schema containing
`base_url`, `max_tokens`, `dry_run`, response format, and thinking mode. Even
where that schema is present, the historical endpoint did not reproduce any
of the 661 current keys. A prompt-equivalence claim therefore cannot be
substituted for an observed exact-key hit.

The current cache stores the key and response, not the original system/user
prompt alongside each response. It cannot be safely re-keyed after the fact
without a separately frozen translation protocol and independently verified
prompt pairing.

## Safety and boundaries

- No API key was available to any historical replay subprocess.
- API attempts were 0 for the valid baseline and all four historical runs.
- The cache SHA-256 was checked before and after every run and never changed.
- No source code was modified to make an old commit runnable.
- Historical runs exited normally but produced only operational model-audit
  failures; normal exit is not evidence of a valid replay.
- This experiment does not locate the FP jump from 6 to 17.

## What would make the regression identifiable

One of the following must be obtained and frozen before another bisect:

1. the original 2026-07-07 response cache and its exact client/config receipt;
2. prompt-bearing cache records that preserve system and user messages; or
3. a preregistered cache-translation experiment that reconstructs both old and
   new request payloads, proves prompt equality per request, and never consults
   target labels while pairing responses.

Until then, attributing the FP increase to `promotion.py`, `report.py`, or
`taxonomy.py` would be speculation.
