# Final local app handoff — bytes reconciled; runtime HOLD

This **new** record reconciles existing source, build, UI and producer receipts. It does not repair or replace any producer file, take source ownership, grant approval, or establish production runtime success. Parent independent review remains required. All paths below are relative to the continuation root. Only `coordination-20261119/app-final-handoff/` was written; no build, artifact execution, PostgreSQL, model, service/listener, cloud, SSH, Docker, mounts, downloads or credential access occurred.

## Reconciled identities and evidence

`pins.json` binds the exact original evidence files; `verification.json` records actual fresh local verification. `verify_handoff.py` reads bytes only, imports no peer implementation, and uses the existing offline acceptance validator's confinement/duplicate-key pattern without duplicating its acceptance framework. Pinning is selected byte identity, **not provenance, approval or runtime attestation**. Inputs must stay frozen while replaying; this is not a hostile concurrent-filesystem validator.

- Admission: `artex-worker-admission/source-manifest.json` → `artex-worker-admission/source`: **669 exact files**, no extra files or symlinks. Canonical sorted compact JSON map SHA256: `c3de72f42c8b9e4246e98d84f452254cf812cc0a66bec1748a0665ac28e47f95`.
- Baseline: `artex-worker-admission/baseline-source-manifest.json` → `artex-worker-operational/source`: **665 exact files**. This is an older source identity, not the final build source.
- Runner: `artex-worker-assessment-runner/runner-source-manifest.json`: **13 listed files exact**. Its unconditional activation hold remains; its frozen665 claims of missing API/UI/build are historical and superseded by later669/assets/build, not silently patched here.
- UI: `artex-ui-asset-final/source-inventory.json` → `assets/`: **370 exact files**, no extras; map equals `artex-native-app-final-build/guest-static-assets.json`. These are actual retained UI bytes, not placeholder assets or a new UI generation.
- Generated build tree: `artex-ui-asset-final/build-source`: **1039 exact files = all669 unchanged source +370 generated `server/webui/dist/` assets**. The entire overlay equals `local-build-receipt.json:overlay_only_delta`; no source/overlay collisions. Source, generated tree and binary are separate identities.
- `artex-ui-asset-final/local-build-receipt.json` retains the real offline build commands, toolchain environment and exit0 receipts. Production command used `-tags embedui` for UI embedding, not an admission bypass. **No new build or production execution is claimed.** Receipt itself says `production_app_executed:false`.
- Durable production recovery artifact: `artex-ui-asset-final/bin/artex.gz`, SHA256 `8cf8506d32b48d015a9ed85a4306a909b9c0b9339901bd984b6908db2fa26be3`. Fresh streamed decompression (no extraction/copy) yields **40,312,994 bytes**, SHA256 `77aa59f362abe0c286bdd3cbd90c05e334c5c0d1779936b17aa42221fb317835`, matching the actual build receipt. The producer's `bin/production` points to volatile `/dev/shm`; do not rely on its survival or request another export/build because of it.
- Retained `bin/artex-native-preflight` independently matches `ce400360edd9ec78ae0af167cc2d329a76fff3c54a37a9f8582b4ae28619ef68`. A preflight binary/result is not opaque production-provider admission.

## Historical failure preserved, completed receipts separate

`artex-ui-asset-final/report.json` remains **invalid/truncated**, SHA256 `1ecdf4b85dca72acad6c0e9eb187b39a6293b1fe186301dec17db00b88eba223`; parsing still fails at line454, unterminated string. It is retained as a historical reporting failure, never treated as a complete machine handoff. This lane neither edits it nor synthesizes a repaired producer success report.

Completed evidence is separately bound: `session-result.json` records successful export of370 assets; `local-build-receipt.json` records actual build exits and artifacts; `final-instance-readback.json` / `final-disk-readback.json` are saved closure observations **only**, not present cloud state. The earlier readiness report is the historical independent audit, not a current runtime receipt. This new local handoff supersedes the *missing final reconciliation document* gap, not the malformed historical report itself.

Admission's effective source handoff is `artex-worker-admission/receipts/REPORT.md`. Its original generic P2 RED receipt was overwritten; the later retained reproduction is retrospective, not original TDD chronology. Producer package counts are cited from that complete receipt/readiness audit (52 server terminal PASS; 97 agent PASS +2 SKIP), **not invented or recomputed as a new aggregate pass here**. This verifier independently checks the exact skipped terminal names and retains their original output:

- `TestNativeNormaNonStreamingEmptyTools`: `native_admission_order_test.go:69: Python fixture required`.
- `TestNativeGoPythonSynthetic`: `native_crosslanguage_test.go:4: retained Python jsonschema unavailable; not cross-language proof`.

Both remain required qualification gaps, never accepted as passes. Historical 401/no-provider503 and UID1000 loader-positive fixtures do not establish UID1001 production200. The retained auth trace includes legacy initializer IPv6 DNS, PG and localhost activity; no whole-process no-network assertion is made.

## Deterministic local replay (safe now)

From `/home/iveri`:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/app-final-handoff -p 'test_verify_handoff.py' -v
PYTHONDONTWRITEBYTECODE=1 python /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/app-final-handoff/verify_handoff.py
```

Tests were authored before implementation: actual behavioral RED is in `red.txt` (10 tests,14 failed assertions/subtests, no import/collection error), GREEN in `green.txt` (10 tests,0 failures/errors/skips). Synthetic small fixtures exercise valid maps, missing/mismatched/malformed files, truncated/duplicate/nonobject JSON, symlinks and required skipped/missing/failed tests. Verification exit0 means **local byte reconciliation only**; output explicitly keeps runtime/assessment acceptance false and names gaps. Bad selected input exits1. Repeated actual output is byte-identical; see `report.json`.

## Exact observe-mode contract; no runnable activation shortcut

Source `artex-worker-admission/source/server/server.go` registers **GET `/api/tasks/{id}/native-admission`**; `server/native_observation.go` checks normal JWT authentication, forbids query/body selectors, pins the Manager startup DSN and installed opaque provider/config, rechecks task/exploration/running/unpaused/no-profile/global precedence and all five catalogs **before executor.key**, and re-observes after real executor config verification. It performs no executor dial/model call/intent creation/resume. A200 observes provider/config only; it is not a lease or permission to execute.

Future approved guest bootstrap contract (not run here): GET `/api/health`; GET `/api/auth/status`; POST `/api/auth/init` only for a fresh owned auth DB; authenticated GET `/api/stats` proves model-off; POST `/api/tasks` with actual owned base origin/high-level goal and `seed_first_intent:false`; GET `/api/tasks/{id}` reads actual task/exploration; then authenticated GET `/api/tasks/{id}/native-admission` with **no query or body**. No credentials belong in command lines or receipts. Existing runner hardcodes a design fixture origin, not a verified deployment identity, and needs its owner integration; this handoff does not provide a fake origin.

Observe-only collection routes: GET `/api/exploration/graph?task={id}`, `/api/exploration/nodes?task={id}&page={page}&size=100&order=asc`, `/api/exploration/activity?task={id}&since={cursor}&limit=300`, `/api/exploration/findings?task={id}`, `/api/report?task={id}`. Drain actual pagination/cursors; compare stable report versions/findings, not generated-at timestamp bytes. Control is POST `/api/tasks/{id}/control`, never guessed `/start`; **do not invoke resume** under this handoff.

The production CLI exposes `-addr`, `-data`, `-proxy` (see `source/cmd/artex/main.go`). There is **no verified complete future guest-start command** yet: exact guest paths/config/DSN/private fixed-runtime files and safe bootstrap lifecycle remain unqualified. Do not publish a plausible command as an executable recipe or use the endpoint as a startup-dispatch barrier. Minimal next commands are the two local verification commands above; guest execution must be completed by the existing owners only after the following gates.

## Remaining gates — explicit HOLD

1. **Actual UID1001 production positive:** normal default production entrypoint at fixed `/run/artex-native`, real private policy/phase/source and raw32 executor configuration, actual authenticated no-intent200, identity/catalog seals matching DB/config. UID1000 fixtures and CLI metadata cannot substitute.
2. **Same admitted entrypoint negatives:** unauthenticated, query/body selectors, keyed global, explicit/active profile, role-profile mismatch, disabled/missing binding/tool/source, expired/revoked/wrong task/exploration/changed policy/phase/catalog; prove denial before key/IO as appropriate and zero model/effect counter increments.
3. **Bootstrap/no-dispatch and fresh guest canary:** startup restores persisted nonterminal tasks; do not connect an inference-serving backend and observe afterward. `artex-worker-integration/BOOTSTRAP-ORDER-NOTE.md` is an unqualified bind-before-serve lifecycle candidate, not tested success. Freeze/review actual helper/image/fixture identities, origin and confinement; independently prove no legacy DNS leakage in intended boundary and no premature inference.
4. **Real assessment remains unexecuted:** separately approved autonomous inference → model-created intents → real owned-fixture observation/finding/versioned report → revoke/quiesce → model-off restart → persistence/SQL/graph/JWT/UI readback. No new authority is supplied here.
5. **Ledger settlement:** authoritative `artex-standing-cost-ledger.json` still last settles `artex-ui-asset-retry`. `artex-ui-asset-final/ledger-proposed.json` export charge **$0.015635998 remains UNSETTLED**, proposed cumulative **$0.4872497456682435999999999999**, proposed remaining download allowance **1,813,661,517 bytes**. Parent ledger owner must settle exactly once and read back; no shared ledger was edited. Retained-disk charges remain separate. Estimates are not invoices/provider limits. Later session accounting, if any, is outside these frozen original receipts and must also be reconciled by its owner.
6. **Any future guest/cloud session:** existing coordinator/operator owns scope, fresh exact VM/disk/status/deadline/controller/provider-stop/budget readbacks and exclusivity. Saved deadlines/consumed starts are not reusable approval. This lane neither contacts nor interferes with any active UI session.

Source/build/runner/ledger ownership stays with the existing other coordinator and respective owners. Parent independent review is still outstanding; no activation hold was removed.

## Reusable lessons (handoff only)

Publish small complete atomic receipts separately from large reports; preserve malformed history rather than laundering it. Distinguish source-map identity, generated UI overlay, durable binary recovery and actual runtime admission. Required skips stay gaps. Verify completed artifact bytes before asking for another export. Keep settlement proposals distinct from authoritative ledger changes. No skills, memory, profile or global configuration was modified.
