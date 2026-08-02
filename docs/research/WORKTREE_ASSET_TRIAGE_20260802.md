# Worktree asset triage (2026-08-02)

## Purpose

The all-refs Git bundle protects every committed ref, but Git bundles do not
contain modified or untracked working-tree bytes. This ledger records the
follow-up classification performed before creating a replacement bundle.

## Protected as versioned research assets

The following classes are source or decision-chain artifacts and are committed:

- the eight `docs/research/*.md` reviews, protocols, plans, and stability reports
  from 2026-07-31 through 2026-08-02;
- the previously untracked top-level BenchAudit research notes, experiment
  reports, annotation ledgers, learning guides, and handoff documents;
- the current `README.md` and `RESULTS.md` changes;
- the MMLU psychometric feasibility protocol and implementation;
- the WorkspaceBench evidence-first annotation and item-brief builders.

The older GDPVal statements are retained inside chronological instruction and
review documents as historical inputs. The current externally usable result is
the later correction: **5 confirmed + 2 coverage unknown**. Neither `README.md`
nor `RESULTS.md` in this worktree contains the superseded GDPVal headline.

## Already protected on another ref

Nine frozen `experiments/*.manifest.json` files and the corresponding ignore
exception are committed by `fff4477` (`chore: version frozen experiment
manifests`). That commit is reachable from the all-refs bundle and the pushed
`research/verifier-topology-preflight-20260802` branch. They are not duplicated
on this branch merely to change their ownership history.

## Intentionally excluded from Git

The following directories are local materializations, raw datasets, personal
working data, or source attachments. They are explicitly ignored rather than
silently left untracked:

| Path | Approximate size at triage | Reason |
|---|---:|---|
| `.benchaudit_workspace_a_prime_calibration_view_20260729/` | 72 MB | Re-materialized WorkspaceBench artifact view |
| `.benchaudit_workspace_a_double_prime_internal10_view_20260729/` | 64 MB | Re-materialized WorkspaceBench artifact view |
| `data/` | 2.6 MB | Local model-output/data working set |
| `dataagnet/` | 34 MB | Unrelated raw proposal documents and personal data |
| `图片和附件/` | 51 MB | Raw WorkspaceBench/source attachments |

Ignoring these directories does **not** back them up. Any irreplaceable source
bytes require a separate data backup. Git reproducibility claims must rely on a
committed manifest containing immutable source references, hashes, and sizes;
the local presence of an ignored directory is not evidence.

## Safety decisions

- No `git add -A` was used.
- No data, cache, archive, or attachment directory was committed.
- No file was deleted or rewritten during triage.
- A high-risk credential-pattern scan is required before the research-asset
  commit.
- The replacement all-refs bundle is created only after the commits above and
  verified by a fresh mirror restore plus `git fsck --full`.
