# Benchmark Audit Report

- Input: `source-f8422fab9b21d90c0ee5f0659842ab666d418cb8940842918f9f4b0df7ae0202.parquet`
- Items: `220`
- Violations: `16`
- Confirmed: `5`
- Review signals: `11`
- Unknown-tier findings: `0`
- Affected items: `13`
- Operationally affected items (finding records): `0`
- Coverage-unknown item×checker checks: `1`
- Item×checker checks incomplete due operational failure: `1`
- **Coverage warning:** `1` item×checker check was incomplete due operational failure; these are coverage unknowns, not clean results or unknown-tier findings.
- Methods run: `gdpval_objective, gdpval_workbook_replay, gdpval_dataset_objective, duplicate_conflict`
- Planned item×checker checks: `880`
- Eligible checks: `661`
- Completed checks: `660`
- Coverage-unknown item×checker checks: `1`
- Item×checker operational failures: `1`
- Elapsed seconds: `4.504578`
- Git commit: `a4d5faee7df83be73264904dfd8a1af2322a9cf1`

## Item × Checker Coverage Ledger

`completed_no_finding` means only that a checker returned normally without emitting a finding. It is not a clean-benchmark verdict.

- Planned: `880`
- Explicitly eligible: `661`
- Eligibility unknown: `0`
- Attempted: `661`
- Completed: `660`
- Completed without finding: `647`
- Finding: `13`
- Unknown/incomplete: `1`
- Operational failures: `1`
- Security blocked: `0`
- Unsupported: `0`
- Abstained: `0`
- Ineligible: `219`

### Coverage gaps

- `83d10b06-26d1-4636-a32c-23f92c57f30b` × `gdpval_workbook_replay`: `operational_failed` — check raised GDPvalArtifactNotCached: GDPval artifact is not cached; explicitly call fetch() or set allow_download=True: 'reference_files/cc781e4dc0985c8eb327a53ec03b5900/Population v2.xlsx'

## Artifact Distribution

- `evaluator`: 13
- `oracle_ground_truth`: 3

## Defect Distribution

- `duplicate_rubric_criterion`: 8
- `rubric_artifact_contract_mismatch`: 1
- `rubric_reference_contract_mismatch`: 1
- `task_artifact_contract_mismatch`: 3
- `task_rubric_mismatch`: 3

## Detection Method Distribution

- `gdpval_objective`: 16

## Defect Scope Distribution

- `substantive`: 16

## Field Mapping

- `item_id`: `task_id`
- `task`: `prompt`
- `context`: `['reference_files', 'reference_file_urls', 'reference_file_hf_uris']`
- `choices`: `None`
- `gold`: `deliverable_files`
- `aliases`: `None`
- `output_contract`: `None`
- `evaluator`: `rubric_json`
- `metadata`: `['sector', 'occupation']`
- `diagnostics`: `{'source': 'explicit', 'profile': 'gdpval_objective_v2'}`

## Cases

### `83d10b06-26d1-4636-a32c-23f92c57f30b` (row_uid=`source-row-00000000`)

- `task_rubric_mismatch` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.98)
  - Task and rubric column-role claims differ; workbook replay is required for adjudication.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Replay the claims against pinned reference and deliverable workbook headers.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_column_contract_candidate", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "f794ab320c4c6096b3efb1f5ed5c1de16d7dbfeeb6f32676eb83373a5c4ec6a2", "fact_signature": "3b6aae5c5d11ee8ab176b28512e9770c21adc96a02b1e837aadfefce1d6cad16", "atom": {"kind": "task_rubric_column_difference", "mismatches": [{"scope": "deliverable:...`

### `99ac6944-4ec6-4848-959c-a460ac705c6f` (row_uid=`source-row-00000010`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "4034cf6e8ec2ca55463c3cc49578e781128fdb315a0cf8a3f07ba9e7d376e292", "fact_signature": "a9cb6cfd0b3e4db02323e192547efeb34f5b800e04a77aa10e2d78d91f0f750b", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "6b44a33d162a81eae948c...`

### `bbe0a93b-ebf0-40b0-98dc-8d9243099034` (row_uid=`source-row-00000022`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "31cf38b8bf2415f6902dd08c83821c171a919ece6b6c7655692d8917a4527e57", "fact_signature": "9ac4de3f87926ce6c8b90bf54983c6a5e976e7cc7e00031834340faa90a0f197", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "bbba274d62f00d7a852a7...`
- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "31cf38b8bf2415f6902dd08c83821c171a919ece6b6c7655692d8917a4527e57", "fact_signature": "e93d491f682ed9921042795df2ca2f809cba18c73d069705fa7a6cc6d1a9ddc3", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "d563f88f8cbeb43877d16...`

### `a95a5829-34bb-40f3-993b-558aed6dcdef` (row_uid=`source-row-00000083`)

- `task_artifact_contract_mismatch` / `oracle_ground_truth` / `gdpval_objective` / `major` / confirmed (confidence=1.00)
  - The published deliverable format conflicts with an explicit task output format.
  - Evidence: `deterministic_replay` — Finding passed its exact versioned deterministic/execution proof validator.
  - Repair: Align the task output format, rubric, and expert deliverable.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_task_deliverable_format_replay", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "a139fdbe32d0b52284988fb0057c039d51fcf320527ce44762aec39eafad6b57", "fact_signature": "1bd245246da4915411efc67625376f38fcee81ebab0031a0a65060708564831d", "atom": {"kind": "output_format_mismatch", "expected_extension": ".docx", "observed...`

### `40a99a31-42d6-4f23-b3ec-8f591afe25b6` (row_uid=`source-row-00000101`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "66e7ecd63e500ff14a89913ff8dea3e6d1a907a652cc14053ad1cd4730fca710", "fact_signature": "22748b79161ddceb9c72c91aa44db2899f87b08bdd3164d9d499420ab6fb453e", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "0ced29eececea6926399d...`

### `f1be6436-ffff-4fee-9e66-d550291a1735` (row_uid=`source-row-00000120`)

- `task_artifact_contract_mismatch` / `oracle_ground_truth` / `gdpval_objective` / `minor` / confirmed (confidence=1.00)
  - An explicit task filename is absent from the published artifact manifest.
  - Evidence: `deterministic_replay` — Finding passed its exact versioned deterministic/execution proof validator.
  - Repair: Align the task/rubric filename with the published artifact or replace the artifact.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_task_deliverable_filename_replay", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "cc706031f91f9c7a3843b553ce9cc81794459430231579101e2150c6cdce1781", "fact_signature": "d331c8d7326f56adb530b14d157d99197167631f53cf1697360780d5de9fbceb", "atom": {"kind": "exact_filename_absent", "artifact_role": "deliverable", "expect...`
- `task_rubric_mismatch` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.98)
  - A rubric person name is absent from an explicitly bounded task entity set and closely resembles a supported name.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Verify the intended person name and replace the apparent rubric typo consistently.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_closed_world_entity_candidate", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "cc706031f91f9c7a3843b553ce9cc81794459430231579101e2150c6cdce1781", "fact_signature": "dee4b5af4581abb6a014b08e0b57d4304fc170bcf4deede9a0ee32b7353a3b70", "atom": {"kind": "closed_world_entity_name_difference", "task_people": ["Doe. Screen...`

### `6d2c8e55-fe20-45c6-bdaf-93e676868503` (row_uid=`source-row-00000123`)

- `task_rubric_mismatch` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - Task and rubric name different recipients for the requested communication.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Confirm the intended recipient and update every affected rubric criterion.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_recipient_contract_candidate", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "3f3dbca6fd5b5f931d6c9292944ec6f001957a6f57ff7b4f65e71cf63acefcb8", "fact_signature": "5c24a7252c5623e29c6b11b61beb6a0e35348e6ebfeb094adcce13994f97533e", "atom": {"kind": "recipient_name_difference", "task_recipients": ["John Smith for"], ...`

### `feb5eefc-39f1-4451-9ef9-bffe011b71dd` (row_uid=`source-row-00000142`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "b7fbfd4a1db663af3519cc785053810acf5acc0e5438aafeb01bc79f26eb1971", "fact_signature": "4b3e8b00eb3451e9077c03b1e21ea73feb160b18e56a1b9ad9c4a8804f88e2fc", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "4f2929030428611454731...`

### `e14e32ba-d310-4d45-9b8a-6d73d0ece1ae` (row_uid=`source-row-00000151`)

- `rubric_reference_contract_mismatch` / `evaluator` / `gdpval_objective` / `minor` / confirmed (confidence=1.00)
  - An explicit rubric filename is absent from the published artifact manifest.
  - Evidence: `deterministic_replay` — Finding passed its exact versioned deterministic/execution proof validator.
  - Repair: Align the task/rubric filename with the published artifact or replace the artifact.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_rubric_reference_filename_replay", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "1cc286aececf6b44ba5e5dac680a7a18f2d2a7663c9cc63ac8b9d0caadbf2f67", "fact_signature": "7f1af48c5d331d7130c3aadd37ed65ff24e0690fb9d1a62f9c726f8d616a8855", "atom": {"kind": "exact_filename_absent", "artifact_role": "reference", "expected...`

### `ffed32d8-d192-4e3f-8cd4-eda5a730aec3` (row_uid=`source-row-00000189`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "1839650c36d94225ccfee76e0dbe44199e768787d4d46130b0c588b6647dc442", "fact_signature": "607fcdfaf063f8152cd14b521de731638e878a067851f8b32001e54dccad7e17", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "3562f52f868d31d59eb47...`

### `15d37511-75c5-4c7f-81f1-16e00c0d95f3` (row_uid=`source-row-00000201`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "9a4b1880586a8305e1823dde332c818bd5f618e63f74fdcb6aed63b6b7c7ce05", "fact_signature": "d71de994c7e3f6bc63a13e716d9aaa7c8ff441f355efe5256fc201c1b8a7b507", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "16ffcd81a8c6713fd4adc...`

### `bb863dd9-31c2-4f64-911a-ce11f457143b` (row_uid=`source-row-00000202`)

- `task_artifact_contract_mismatch` / `oracle_ground_truth` / `gdpval_objective` / `minor` / confirmed (confidence=1.00)
  - An explicit task filename is absent from the published artifact manifest.
  - Evidence: `deterministic_replay` — Finding passed its exact versioned deterministic/execution proof validator.
  - Repair: Align the task/rubric filename with the published artifact or replace the artifact.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_task_deliverable_filename_replay", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "8275d2534b35531440733b76aa913f426d8c8f3f4e5d470434a35464703aa9df", "fact_signature": "1a509b08a734fd87906f49dc2cc4df814b83f5bcb209b0b73aa08506da9c555e", "atom": {"kind": "exact_filename_absent", "artifact_role": "deliverable", "expect...`
- `rubric_artifact_contract_mismatch` / `evaluator` / `gdpval_objective` / `minor` / confirmed (confidence=1.00)
  - An explicit rubric filename is absent from the published artifact manifest.
  - Evidence: `deterministic_replay` — Finding passed its exact versioned deterministic/execution proof validator.
  - Repair: Align the task/rubric filename with the published artifact or replace the artifact.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_rubric_deliverable_filename_replay", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "8275d2534b35531440733b76aa913f426d8c8f3f4e5d470434a35464703aa9df", "fact_signature": "c9315e4976c9f0a4280753772b993bf74e7ce1af32995b39fc4d5a4ddbe7d238", "atom": {"kind": "exact_filename_absent", "artifact_role": "deliverable", "expe...`

### `5349dd7b-bf0a-4544-9a17-75b7013767e6` (row_uid=`source-row-00000210`)

- `duplicate_rubric_criterion` / `evaluator` / `gdpval_objective` / `review` / review (confidence=0.99)
  - The rubric repeats the same normalized criterion.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Remove accidental duplicate scoring or document intentional repeated weighting.
  - Evidence: `{"proof_schema_version": "1.0", "evidence_level": "gdpval_duplicate_criterion_scan", "benchmark_family": "gdpval", "dataset_revision": "11e7900cdcac61bc4daf59e65feb238acda98fbf", "predicate_version": "benchcore-gdpval-objective/1.0", "replay_input_sha256": "7e9613f9a4ba52cdca244358da332813c75a5c1da2a08cdfeea4ac3cae3749c7", "fact_signature": "3cdb121708caae924a1e5dd685511634cc6b85422b7b8f79b69b99d0913eb68a", "atom": {"kind": "duplicate_rubric_criterion", "criterion_sha256": "c2277929fda07ab36519c...`
