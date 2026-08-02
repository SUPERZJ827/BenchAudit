# BenchAudit Verifier Topology Preflight Plan V3

> Status: **frozen CLI-compatibility amendment; not a production protocol**
>
> Parent V2 SHA-256: `1188621464c012be99779cd34aef17786b560aebb535c58dbc35920cbfa58b84`

V2 remains an immutable failure:

```text
decision           = NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY
first_failing_gate = command_failed
reason             = Podman 3.4.4 network connect does not support --ip
receipt SHA-256     = 45619ced7f98342f4b7d9077c31431bc41174be1d3498e71af28edd5b5e4d437
```

V3 removes only `--ip <egress-ip>` from the command that attaches the proxy to
the egress network. Podman assigns that egress-network IP. The security-relevant
proxy listener remains explicitly bound to the frozen literal internal-network
IP; verifier and proxy network-set inspection remains mandatory.

This change does not widen egress, add a network, change engines or images,
alter an authority, weaken a probe, or reuse a V2 subresult. V3 reruns the full
five-probe preflight in new networks, containers, proxy sessions, and files.
