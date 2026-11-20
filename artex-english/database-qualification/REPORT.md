# Private PostgreSQL approval/history/archive qualification

## Outcome

**PASS for the bounded qualification:** 14 top-level tests and 25 subtests passed; zero failures or skips in the final successful run. This is **not** a whole-package pass or a frozen integrated-source attestation. No application source was modified.

PostgreSQL **16.15**, nonroot UID 1000, was initialized from scratch twice in new 0700 task-owned state/socket directories under the approved scratch directory. Only Unix sockets were enabled. Actual SQL readback confirmed `listen_addresses=''` and HBA `local:peer` / `host:reject`. No existing database, shared `.runtime`, global service, TCP listener, model, installation, download, or credential/config/profile change was used.

## Real database evidence

`qualification_v2_test.go` imports the candidate's actual `db` and `intercept` packages. It executes their real PostgreSQL schema, seeding, ORM entrypoints, history queries, schema backfill, archive snapshot/compaction/restore, Judge, Log, and HandleAsk. No simulated SQL driver is used in this new harness.

Seven committed approval records were checked through an independent `database/sql` connection after restoration:

| Case | ID | Restored source |
|---|---:|---|
| `[Model]` reason | 59 | model |
| Legacy `[模型]` reason | 60 | model |
| Rule plus English marker | 61 | rule |
| Rule plus legacy marker | 62 | rule |
| Unmarked multilingual evidence | 63 | unknown |
| Embedded, non-prefix marker | 64 | unknown |
| Explicit persisted override despite marker | 65 | unknown |

Checks assert exact original reason text, IDs, status, and microsecond-resolution created/decided timestamps. Production SQL fallback was exercised with empty persisted sources: filtered history returned **2 model, 2 rule, 3 unknown**. Reopening through `db.Open` exercised the actual schema backfill while preserving explicit source overrides and original reason text.

The archive manifest deliberately omitted historical `decision_source` fields, except the explicit override. Actual hot-store compaction left zero task approval rows. Actual restoration reconstructed the correct sources without laundering settled evidence. Pending row 66 restored as `timeout`, audit action `deny`, with the translated archive-timeout reason.

With a deterministic injected reviewer—not a model client—real-PG Judge emitted `[Model] Allowed`. HandleAsk emitted `Tool Read requests approval (#68)` and cancellation persisted status `denied`, audit decision reason `Work was cancelled`, action `deny`, execution status `not_executed`, **while preserving the original reason** `[Model] Requires human approval`.

See `sql-proof.json` and the assertions in `qualification_v2_test.go`. The proof file is written only after all SQL assertions pass.

## Commands and test scope

Executed from the candidate source directory, with the retained offline Go environment:

```text
GOROOT/bin/go test -p 1 -json ./db ./intercept -run '^(TestOpenSeed|TestInterceptApprovalFilters|TestInterceptExecutionNavigation|TestTaskArchiveDatabaseRoundTrip|TestInterceptSourceEnglishLegacy|TestApprovalSQLRecognizesEnglishLegacy|TestRestoreApprovalEnglishLegacyEvidence|TestTaskArchiveFormatCompatibility|TestEnglishJudgeGeneratedReason|TestEnglishHandleAskSummaryAndCancellation|TestEnglishVerdictCompatibility|TestEnglishGeneratedDefaultsPreserveSuppliedNames|TestEnglishVerdictStrictRejections)$' -count=1 -timeout=180s
GOROOT/bin/go test -p 1 -json /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/artex-english/database-qualification/qualification_v2_test.go -run '^TestPrivatePostgresApprovalHistoryArchive$' -count=1 -timeout=180s
```

The exact resolved executable/argv arrays, full Go JSON terminal events, required-name checks, and package-failure checks are retained in `report.json`, `test-results.json`, `existing.jsonl`, and `real-sql.jsonl`. Existing allowlist: 13 top-level / 25 subtest passes. New real-SQL harness: one top-level pass. No skip is accepted.

Launcher:

```text
python3 /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/artex-english/database-qualification/run.py
```

The launcher imports the reviewed `artex-local-pg/run_with_pg.py` and calls `run_session`, **not `main()`**, supplying new owned state/socket directories and the retained PG prefix. Its identity override delegates to the exact stable UID/startticks/executable helper in `artex-worker-runtime-v2/run_with_pg.py`; mutable PostgreSQL cmdline titles are not shutdown identity invariants. The wrapper retains its `Popen` and pidfd and shuts down through pidfd signaling.

`GOFLAGS=-mod=readonly`, `GOMAXPROCS=2`, `CGO_ENABLED=0`, `GOPROXY=off`, `GOSUMDB=off`, `GOENV=off`, `GOTOOLCHAIN=local`. No overlay or copied cache. Go version: **go1.26.10 linux/amd64**. Each Go command has a 180-second wall/test bound, fixture child 300 seconds, helper 20 seconds, shutdown 18+2 seconds. Both actual fixture sessions completed well within these limits.

## Review, pins, and moving-source caveat

Selected test bodies and production entrypoints were inspected before execution. The db/intercept/config source scan found no relevant init/listen/dial/external-command effects; schema external-effect search found inert transport strings rather than external SQL execution. Seeded MCP/model-profile records are SQL data only. No HTTP server or actual tool/model executor is invoked. Archive path/checksum strings are metadata only, not filesystem artifacts.

`build-inputs-go-list.jsonstream` contains the offline `go list -deps -test -json ./db ./intercept` manifest; `build-inputs-pins.json` hashes **2,780 resolved source/test/embed inputs** before the successful test commands. `existing-{before,after}-pins.json` and `real-sql-{before,after}-pins.json` contain byte and literal-preserving lexical noncomment fingerprints for db/intercept/config and module files. No byte or lexical drift was observed in those command windows. Lexical hashes are not a compiler AST proof. Other workers can still edit libraries or comments: this evidence does **not** pin a final integrated tree or claim future source identity.

Wrapper SHA-256: `ec8c7e3243dd44bea6b2bc85f8ac3b25c94a25e91466c0fd71e4d7803fcb7bdb`.

Stable identity adapter SHA-256: `8cecb341e200aba0dfebd951e9c56687bd6837ca0729d0a3b2839f750fd9d1ed`.

Postgres executable SHA-256: `201d8daff9a5bd9df70b820471b965c39f5a776d677f395232c477d051270722`.

## Preserved failed attempt

The first new harness failed only its last cancellation assertion: it incorrectly expected cancellation to replace the original `intercept_pending.reason`. Inspection of actual `ResolveIntercept` confirmed that cancellation belongs in `audit.decision_reason`, preserving original evidence. This was a **qualification harness expectation defect**, not an observed production defect.

The failed harness, raw Go events, pins, PostgreSQL log and closure receipt remain untouched in `attempt-1/`; the original `qualification_test.go` is also retained. A new `qualification_v2_test.go` checks **more fields**, including preserved original reason, audit reason, action, and execution status. It passed against another newly initialized cluster. No source repair, weakened assertion, hidden failure, or reused live cluster was involved.

## Process closure and disk

Both success and failure paths verified stable identity again immediately before shutdown:

- First postmaster: PID 96084, UID 1000, start ticks `289874291`, retained postgres executable.
- Final postmaster: PID 98642, UID 1000, start ticks `289886947`, same executable.
- Both exited with return code 0; wrapper receipts record `closed=true`, `pid_exited=true`, `socket_absent=true`.
- Both PID files were absent and postmaster `/proc` entries absent before fixture deletion.
- PostgreSQL logs confirm completed shutdown; every logged postmaster/worker PID was absent in the subsequent cross-check. No remaining process had either exact owned state path as an argv item. This cross-check sent no signals.
- Only the two exact closed, owned 0700 state and socket directories were deleted. Their absence was verified. No unrelated cache cleanup occurred.

Each measured fixture footprint was 52,488,135 bytes, below 150 MiB. Shared retained cache growth was 13,618,496 bytes in the first session and 512,796 bytes in the final session, below the 100 MiB allowance in total. The 512 MiB free-space floor was checked before fixture launch and polled during Go execution; final successful session had 1,029,865,472 bytes free before removing its fixture. After removal of both owned fixtures: 1,136,381,952 bytes free. These are measured session/cleanup values, not a claim that a shared cache is exclusively attributable to this task.

## Exclusions and handoff

The exact omitted-test lists are in `report.json`: **160 db tests and 17 intercept tests** were not selected. The earlier 139 DB skips are not all reclassified as passes. This task closes the specific approval/history/archive English/legacy SQL gap, not the entire DB suite. Existing synthetic-driver tests remain synthetic; the additional harness supplies the real PostgreSQL evidence.

No server/agent integration, HTTP/UI interaction, model inference, real tool execution, archive compression/checksum file lifecycle, production database, container/network confinement, or final integrated build was qualified.

Reusable lessons for the coordinator only: resolve cancellation assertions against `audit.decision_reason` separately from immutable initial evidence; test insertion classification, empty-source SQL fallback, schema backfill, and old archive manifests independently; retain stable UID/startticks/executable identity plus pidfd across both success and failure cleanup. No skill/profile edits were made.
