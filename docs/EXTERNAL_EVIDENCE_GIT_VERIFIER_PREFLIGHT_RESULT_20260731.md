# Production Git verifier: APPS strict-ancestor preflight

Date: 2026-07-31

Decision: `NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`

Verifier implementation started: no

## Result

The official APPS cutoff commit was fetched into a new empty bare repository
from the pinned Hugging Face dataset remote. The cutoff is itself the commit
that changes `README.md`.

Its direct parent is a genuine strict ancestor, but the normative README bytes
differ:

| | Strict ancestor | Cutoff |
|---|---|---|
| Commit | `370e6cb6919462bcabf8f00718b4099c8096e719` | `21e74ddf8de1a21436da12e3e653065c5213e9d1` |
| README blob | `c75ca05bfca04a68edb8d9f229d69aafcdd452b2` | `6053317a3ea13af4b2490691aff725e21a40268f` |
| Content SHA-256 | `3e80910ad5a35b5a3c9f2e21d296905ed41d03726937d7746ea59e127731fe7a` | `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846` |

All 30 strict ancestors of the cutoff were scanned. None contains the cutoff
README blob. Therefore no strict-ancestor receipt for the frozen normative path
can satisfy policy v1's requirement that the receipt content match both source
and cutoff trees.

## Stop-rule application

The reviewed protocol explicitly forbids:

- substituting `source_commit == cutoff_commit`;
- changing the normative path after inspecting the result;
- treating the offline positive fixture as a real remote replay;
- widening host or content policy to obtain a pass.

Accordingly, Phase 2A stops before verifier implementation. The result does
not show that a production verifier is impossible in general. It shows that
the pre-registered APPS strict-ancestor README positive case is unavailable
under policy v1.

## Controls

- official remote was the frozen HTTPS Hugging Face dataset URL;
- one exact cutoff fetch was performed;
- no existing clone, checkout, shallow history, alternate object store,
  replacement ref, graft, credential, API, or LLM was used;
- forward ancestry succeeded and reverse ancestry failed;
- SHA-256 used raw `git cat-file blob` content bytes without Git object header.

The structured receipt records the complete source-selection result.
