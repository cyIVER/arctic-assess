# Agent / guard English translation review handoff

## Result

- Completed the remaining owned agent/tool generated descriptions, nested schema help, errors, summaries, terminal/cancellation explanations, provider diagnostics, and explanatory comments.
- All **25 domain-tool catalog entries** now pass English description/schema checks.
- Added English retester and graph-compression prompts, preserving their evidence thresholds, scope limits and protocol tokens. The eight previously translated role-prompt files retain **every original literal value**, verified against the handoff baseline.
- Only `source/agent/**` changed (28 files, including the new focused regression test). `source/guard/**` is unchanged. Prior evidence is untouched.

## Verification

| Receipt | Top-level pass / fail / skip | Subtest pass / fail / skip | Interpretation |
| --- | --- | --- | --- |
| `english-red.json` | 0 / 3 / 0 | 0 / 63 / 0 | Real missing-English assertion failures, before implementation |
| `english-green.json` | 3 / 0 / 0 | 63 / 0 / 0 | Same new catalog/error/cause tests passed |
| `focused.json` | 58 / 6 / 10 | 153 / 0 / 0 | Intermediate broad regression; retained failures/skips, not promoted to a pass |
| `final-safe.json` | 60 / 0 / 0 | 86 / 0 / 0 | Explicit listener-free offline regression allowlist passed |
| `side-safe.json` | 1 / 0 / 0 | 2 / 0 / 0 | Scripted streaming/non-streaming side-question denial and transcript isolation passed |
| `final-verified.json` | 61 / 0 / 0 | 88 / 0 / 0 | Final combined listener-free allowlist passed on the final source; required test names and final source hashes verified |

`structure.json` verifies production Go token structure unchanged after excluding comments and masking string/character values. It separately verifies every pre-existing non-Han literal unchanged except the two explicitly translated terminal-summary punctuation literals. This covers identifiers, operators, numeric budgets, control flow, machine tool names, JSON keys, SQL strings, enum values and other unchanged protocol literals. It is **not** independent natural-language semantic review or live security acceptance.

The six intermediate failures were five stale Chinese terminal-message expectations and the existing 40-rune cause-label limit. Expectations were translated without removing assertions; English labels were shortened to satisfy the unchanged limit. Unicode partial-output and rune-truncation tests remain intact.

## Exact residual classification

`remaining-nonenglish.json` contains **32 retained lines**, with no unresolved generated production prose or explanatory comments:

- 19 Unicode override/template/budget fixture lines.
- 4 Unicode model-output/rune-truncation fixture lines.
- 4 original user/task/evidence-isolation fixture lines.
- 2 actual referenced document paths, preserved as identifiers.
- 1 multilingual production quota-detection line.
- 1 multilingual quota-test line.
- 1 ICP registration-format fixture line.

`prior-classification-reconciliation.json` reconciles every line in the previous worker's inventory, including legacy assertions previously labeled functional exceptions. Do not erase meaningful Unicode fixtures or detector strings just to empty a scan.

## Behavior and identity warning

No changes were made to cancellation codes, scopes, admission logic, budgets, permissions, native security checks, handlers, JSON argument keys, required fields or enum values. Existing custom/persisted prompt/tool overrides are deliberately not migrated.

**Catalog descriptions and schema descriptions changed. Any catalog/binding digest or native phase permit derived from prior text is stale. Recompute/review identity and obtain fresh explicit approval before a model-enabled UI is used; do not reuse or silently remint previous approvals.** No UI, model, deployed profile, permit or database was activated/changed by this translation pass.

## Limits / issues requiring coordinator attention

1. Full application build and independent review remain pending. This is scoped source/regression evidence, not deployment or end-to-end acceptance.
2. Database-dependent insertion/approval cases in the intermediate run skipped; no PostgreSQL fixture was provisioned. No persistent database effects were verified.
3. **Execution-scope deviation:** the intermediate test regex was too broad. Existing `TestNativeRPCSyntheticNoTarget` and `TestCapturePropagatesThroughNormaProvider` started transient local `httptest` loopback listeners, contrary to the no-listeners constraint. Both tests returned; their source uses deferred `Close`, and the test process exited. No external provider/model endpoint was called. The final allowlist excludes these tests and all native prefixes. This deviation is retained explicitly rather than hidden by the later clean run.
4. The filesystem was near full (1.5G available initially, 1.2G at the last check); no disk failure or deletion occurred. Retained Go toolchain/cache used offline with readonly modules; task scratch is under `agent-final-evidence/scratch`. No installs/downloads or whole-app builds.
5. Server English `Task: #` context and intercept/database legacy compatibility for `[Model]` and `Tool ... requests approval` remain other owners' integration responsibilities.
6. `source/agent/side_questions_test.go` now expects the exact English denial already present in `source/sidequestion/service.go`; that producer was read only.

## Artifacts

- `report.json`: machine-readable findings, all commands/environments, test terminal counts, failures/skips and limits.
- `translation.diff`: exact baseline-to-current owned-source diff; no Git metadata is present in this candidate directory.
- `hashes.json`: baseline and final SHA-256 maps for every owned Go file.
- `baseline.json`: pre-edit owned-source snapshot.
- `structure.json`, `verify_structure.go`: reproducible structural/literal preservation check.
- `*.jsonl`, `*.json`: complete raw and parsed test receipts.
- Translation tables and inventory/reconciliation files retain the exact mapping and scope decisions.

## Reusable lessons (handoff only; no global skill/profile writes)

- Inspect test bodies before selecting broad prefixes: offline tests can still open local listeners, and skipped DB tests prove no persistence behavior.
- Pair translated-language checks with token/literal identity preservation; classify meaningful residual Unicode instead of deleting it.
- English expansion can violate existing rune limits; shorten labels rather than relaxing limits or weakening tests.
