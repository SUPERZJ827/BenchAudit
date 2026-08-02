# BenchAudit Verifier Topology Preflight Plan

> Status: **frozen preflight plan; not a production verifier protocol**
>
> Date: 2026-08-02
>
> Purpose: establish whether a digest-pinned Git-verifier network topology is
> satisfiable before freezing a production verifier protocol.

## 0. Claim boundary

This preflight may produce only one of:

```text
TOPOLOGY_SATISFIABLE
NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY
```

It does not produce a provenance receipt, attestation, finding, promotion
decision, or benchmark conclusion. It does not execute candidate code.

Any failed gate stops the preflight. The executor must not widen an authority
allowlist, enable host networking, use host-side Git fetch as a fallback, alter
the selected container engine, or reinterpret a failed probe.

## 1. Frozen benchmark inputs

These inputs predate this preflight and are not selected from its outcome:

| Field | Value |
|---|---|
| Canonical remote | `https://huggingface.co/datasets/codeparrot/apps` |
| Allowed CONNECT authority | `huggingface.co:443` |
| Exact revision | `21e74ddf8de1a21436da12e3e653065c5213e9d1` |
| Blob path | `README.md` |
| Expected Git blob OID | `6053317a3ea13af4b2490691aff725e21a40268f` |
| Expected raw-content SHA-256 | `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846` |
| Negative-control CONNECT authority | `example.com:443` |
| Negative-control direct IP | `1.1.1.1:443` |
| Preferred pinned verifier image | `alexgshaw/fix-git:20251031@sha256:61e431c00c58df652287aadce5457634d9f9330cfdd153ebdf2802df0d540119` |

## 2. Engine and image identity gate

The executor must call `benchcore.execution.find_container_engine()` exactly
once for authority. Its selected executable path, basename, client version,
server/runtime version when available, rootless state, and relevant network
backend must be recorded.

Podman is preferred over Docker by current code. The executor must not choose
Docker merely because a required image or topology is unavailable in Podman.
Such an availability failure is `NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY`.

The image must be addressed and inspected by immutable digest. The receipt
records configured reference, resolved image ID, repository digests, and
inspection output hash. A tag-only or mutable image is insufficient.

## 3. Network mechanism

The preflight uses two isolated container networks:

1. an **internal** network with no default external NAT, containing verifier
   and proxy;
2. an egress network containing only the proxy.

The verifier is attached only to the internal network. The proxy is dual-homed.
The proxy must bind only its literal internal-network IP. `0.0.0.0`, `::`,
host networking, and implicit wildcard binding are prohibited.

The receipt must record network IDs, inspect-derived network attachments,
proxy internal IP text and normalized IP, and the engine mechanism that makes
the verifier network internal. This mechanism—not negative probes—is the
claimed direct-egress control.

## 4. Proxy audit contract

Each accepted socket produces exactly one terminal connection record with one
closed disposition:

```text
allowed
forbidden
malformed
upstream_failed
client_aborted
handler_error
```

Raw JSONL contains session start/end, accept-time monotonic connection sequence,
time, raw request line, parsed/normalized authority, status, disposition,
reason, and upstream result. Writes and sequence allocation are lock protected.

Stable summary excludes time, PID, temporary paths, connection ordering, and
duration. It contains the parsed-authority set and disposition counts per
authority plus unparsed disposition counts, serialized with sorted keys.

Every preflight session starts a new proxy process and new log files. Fetch and
live rejection use separate proxy sessions.

## 5. Fetch-session gates

In one verifier container with one unchanged network configuration:

1. proxy CONNECT to `huggingface.co:443` succeeds;
2. after clearing all proxy variables, direct TCP to every host-resolved
   canonical IPv4/IPv6 address on port 443 fails;
3. after clearing all proxy variables, direct TCP to `1.1.1.1:443` fails;
4. container-local resolution of `huggingface.co` fails;
5. exact Git revision fetch succeeds through the proxy;
6. `git cat-file blob 21e74ddf...:README.md` yields the frozen blob OID and
   raw-content SHA-256.

The proxy stable-summary gate is:

```text
parsed_authorities == {"huggingface.co:443"}
allowed >= 1
forbidden == 0
malformed == 0
upstream_failed == 0
client_aborted == 0
handler_error == 0
all unparsed disposition counts == 0
```

Any second authority, redirect, LFS/CDN authority, or incomplete connection is
a stop. The allowlist must not be changed after observation.

## 6. Independent live-rejection gate

A second new proxy process and new log session receives exactly one verifier
CONNECT request for `example.com:443`. It must return HTTP 403 without opening
an upstream connection.

The rejection-session gate is:

```text
parsed_authorities == {"example.com:443"}
forbidden == 1
allowed == 0
malformed == 0
upstream_failed == 0
client_aborted == 0
handler_error == 0
all unparsed disposition counts == 0
```

Parsed-but-rejected authorities always appear in `parsed_authorities`. This
live control prevents a proxy that never rejects from satisfying the preflight.

## 7. Probe interpretation

The receipt must keep these fields separate:

```text
mechanism_blocking_direct_egress = <inspectable internal-network mechanism>
direct_canonical_ip_probe_result = corroboration_only
direct_third_party_ip_probe_result = corroboration_only
dns_probe_result = corroboration_only
```

IP and DNS probes support the mechanism check but do not prove universal
network isolation. Canonical IPs may change after the run.

## 8. Candidate-network regression gate

The existing candidate `ContainerRunner` must continue to emit exactly:

```text
--network none
```

Verifier topology code must not modify `benchcore.execution.ContainerRunner`,
its default execution policy, or candidate CLI wiring. A regression test and
receipt field must attest this separately from verifier topology.

## 9. Required delivery

The preflight receipt contains:

- selected engine identity and image identity;
- proxy script path and SHA-256;
- literal and normalized listen IP;
- network mechanism and inspect output hashes;
- all five probe outcomes;
- raw and stable hashes for fetch and rejection sessions;
- complete CONNECT authority sets and disposition counts;
- exact Git fetch/blob result when reachable;
- V1 §3.3 enforcement status item by item;
- candidate `--network none` regression status;
- final two-valued topology decision and first failing gate, if any.

No result may be upgraded by deleting an unexpected connection, rerunning only
a favorable subprobe, switching engines, or replacing a failed live run with a
fixture.
