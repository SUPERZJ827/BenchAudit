# BenchAudit Verifier Topology Preflight Plan V2

> Status: **frozen preflight amendment; not a production verifier protocol**
>
> Date: 2026-08-02
>
> Parent: `docs/VERIFIER_TOPOLOGY_PREFLIGHT_PLAN_20260802.md`
>
> Parent SHA-256: `7363368ab55ff870b435d88b4598564edd5e83dd00b625851cdf8478917dbb38`

## 0. Preserved V1 result

V1 ran once and remains immutable:

```text
decision           = NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY
first_failing_gate = network_internal_flag
reason             = expected internal=True, got None
receipt SHA-256     = 6c0e25f53e87155e5e4ec38ebdda4a672dad595669651cdb63573845c451e542
```

No fetch, candidate execution, provenance receipt, attestation, or finding
occurred in V1. V2 does not rewrite or upgrade that result.

## 1. Why an amendment is required

The selected engine is `/usr/bin/podman`, version 3.4.4, rootless, using its
legacy CNI representation. For a network created with `podman network create
--internal`, `podman network inspect` does not emit a top-level `internal`
boolean. V1's parser treated the missing representation as a topology failure.

A diagnostic internal network showed this CNI structure:

```text
bridge.isGateway = false
bridge.ipMasq absent
dnsname plugin absent
```

A diagnostic ordinary egress network showed the contrasting structure:

```text
bridge.isGateway = true
bridge.ipMasq = true
dnsname plugin present
```

Both diagnostic networks were removed after inspection. These observations
identify a parser representation gap. They do not demonstrate that direct
egress is blocked; the full negative controls remain required.

## 2. V2 internal-network derivation

For Podman CNI only, V2 derives `internal=true` exactly when all are true:

1. the inspect document has a `plugins` list;
2. exactly one `bridge` plugin exists;
3. `bridge.isGateway is false`;
4. `bridge.ipMasq` is absent or false;
5. no plugin has type `dnsname`;
6. no plugin has type `masq`.

For Podman CNI, V2 derives `internal=false` for the egress control network only
when the bridge has `isGateway=true` and `ipMasq=true`.

For Docker or newer engine representations that expose a top-level
`Internal/internal` boolean, V2 continues to require that explicit field.
Unknown representations remain fail-closed. There is no "command accepted, so
assume internal" fallback.

## 3. No relaxed gate

V2 changes only inspect parsing. It does not change:

- the selected engine;
- the digest-pinned image;
- dual-network proxy topology;
- literal internal-IP proxy binding;
- DNS blocking configuration;
- direct canonical-IP and third-party-IP negative controls;
- independent live 403 session;
- authority and disposition gates;
- candidate `--network none` regression;
- stop rules or claim boundary.

V2 must rerun the entire preflight in new networks, containers, proxy processes,
logs, and output paths. It may not reuse a V1 subresult or omit a probe because
the corresponding code already passed a unit test.
