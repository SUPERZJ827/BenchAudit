# External-evidence Git verifier V2 result

Date: 2026-08-01

Decision: **`NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`**

## What was completed

Before any APPS result was observed, Phase 2A froze and committed:

- the V2 protocol and the policy-level bidirectional-ancestry defense;
- one code-allowlisted APPS manifest containing only the normative
  `README.md` binding;
- a standalone Git verifier that creates a new bare object database, fetches
  exact commits, checks both ancestry directions, rejects LFS pointers and
  object overrides, reads `git cat-file blob` bytes, and replays policy v1;
- a digest-pinned isolation runner and an exact-authority CONNECT proxy;
- a static non-activation test keeping the verifier outside all production
  checker and CLI paths.

The implementation was frozen in commit `e08c70b` before the real replay.
It was not changed after the replay result.

## Frozen hashes

| Artifact | SHA-256 |
|---|---|
| V2 protocol | `68c3a72835f7919c2c2df1a12f9a5e3fe0c25da91e986bfddb57ef7db6063461` |
| trusted manifest file | `70f6d2a81f7fbbd11576077b87fe6f2d58b2dd842110b647b580cf7c5c27304a` |
| verifier | `3e87880cac65d878dedf6f1452fb964e4e78135f9ce96a2afba28c6dde50e9e2` |
| allowlist proxy | `7be71ea1c255f6c4bd182cca83a4710e2ff0e76153dacf810b6571e96b1eae65` |
| isolation runner | `5bc85a48aa5306607432b9fa64f260597a899117ca088bb1f15bcf95146fd99d` |
| verifier tests | `62a30ef7ce220ec2cbddeed1c5609394585a31bd065dc0d763c8d31bb29f7d80` |
| original execution receipt | `a5c0edbfcc478edab8b6d8b5141e53f0ac382bc8fef97535cf53ada224c9a75e` |

The manifest's canonical payload hash is
`28a8501dce3194c767362db2bcdb1aeac3e977aa064c2cbba9521ddf481c9acc`;
the verifier separately pins that value in source code.

## Tests

- targeted external-evidence tests: **48 passed**;
- full repository tests before execution: **775 passed**;
- API and LLM calls: **0**.

The attacks cover manifest mutation and self-consistent substitution, URL and
host confusion, role/path/cutoff mismatch, content-byte hashing, LFS,
alternates, impossible bidirectional ancestry, and accidental production
activation.

## Why the real replay stopped

The verifier container had only an internal Docker network. Its sole outbound
path was a second digest-pinned container that accepted CONNECT only for
`huggingface.co:443`. The official fetch failed on replay 1 because that proxy
container could not reach the environment's egress path.

The host environment permits Internet access only through a loopback-bound
proxy. That loopback service is not reachable from the pinned container.
Changing to host networking, mounting the host proxy, or adding a less
restricted bridge path could make the command run, but would violate the
frozen execution contract. Therefore:

- replay 1 did not complete;
- replay 2 was not started;
- no stable-summary equality claim is made;
- no local fixture, V1 object database, or local clone substituted for the
  real replay;
- the result remains `NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`.

## Diagnostic boundary

A direct host diagnostic, explicitly excluded from evidence, fetched the
official APPS object and reproduced:

- blob ID `6053317a3ea13af4b2490691aff725e21a40268f`;
- content SHA-256
  `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846`;
- diagnostic stable-summary SHA-256
  `034ff5f501c4a1db2704a37dafce38e242029efe8fbecdd628be38c299322355`.

This shows that the official object and verifier logic were available; it
does **not** satisfy the digest-pinned network-boundary requirement and is not
counted as a pass. The separate diagnostic addendum records this distinction
mechanically.

## Claim boundary and next action

This result does not show that a production Git verifier is generally
impossible. It shows that V2's pre-registered execution boundary cannot be
completed in the current loopback-proxy environment.

Phase 2B remains forbidden. Any attempt to introduce a pinned upstream-proxy
relay or a different egress architecture requires a separately frozen V3
protocol and a new implementation commit. V2 will not be rewritten to obtain
a pass.
