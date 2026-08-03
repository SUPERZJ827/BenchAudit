# MMLU historical-cache binding availability preflight

- Outcome: **PASS_V2_FEASIBLE_WITH_RESIDUAL_UNATTESTED_PROMPT_SNAPSHOTS**
- Caches checked: **7**
- Upper-bound bindings complete: **7**
- Union of run-bound source items: **1087**
- Attested reverse bindings: **4**
- Empirical/unattested reverse bindings: **3**
- Candidate/holdout prompts reconstructed: **0**

All seven caches have a complete forward item-set bound and a live golden initial-key match. Three 2026-07-13 reports predate implementation manifests, so their historical prompt snapshots remain empirically matched but unattested. V2 is feasible only if this residual limitation is preserved and forward bounds remain authoritative for those runs.
