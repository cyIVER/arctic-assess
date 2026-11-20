# Integrated candidate V4 — LOCAL ONLY

**Ready for independent source review; runtime admission remains BLOCKED.** No authority or approval is issued by this report.

## Repair and base selection

Selected actual `artex-worker-live-guard-final/guard.py` SHA256 `b54b4b00627193105c3b23621b04b529f3c9ee422842597cd53ccb2901b295ef`, not original `4dbee74525efc94a4262d7e297c0922e5ffeeba5c5583b6466454898d6f8a0cd`. `evidence/original-final.diff` captures the entire inspected delta. Retained final's explicit host UID1000 role, private host staging shield, task-path restrictions, full official SDK manifest validation, pinned SDK Python, isolated interpreter environment, host mux path, and distinct host key location. The final base still had the per-stage timeout defect; actual pre-fix client accepted18 virtual seconds.

Only three production files change: `canary/admission_v3.py`, `canary/guest.py`, `guardian/guard.py`. Full exact diffs and source pins are separate from evidence pins. Caller, fixture privilege handling, archive/quota fixes, driver, probes, bounded transport, runtime/lifecycle, and all inherited test files retain original bytes. No source665 bundle was copied into the candidate: local links reference existing read-only inputs. Preserved suites themselves create private temporary staging snapshots through the unchanged production staging helper.

## One checkpoint contract

Both actual validators now accept exactly one schema1 object: verified status, already-private-default-quiescent requirement, VM, created, deadline, parent lease handle, parent default-service-change ownership, external STOP and exact empty containers/images/volumes inventory. Boolean/nonfinite timestamps and boolean schema are denied. Lease shape and scope, phase timestamps, freshness120s, phase expiry and STOP headroom remain checked. Additional keys and marker-only checkpoints deny. Identical validator function ASTs are checked in preservation evidence; duplication is deliberate so the standalone immutable guardian does not introduce an unpinned cross-component import. This is one schema, not separate authority/inventory objects, not a boolean proof.

Guest passes the actual admission time into the checkpoint validator. Guardian continues protected pinned reads, fresh package versions/integrity, service/socket inactivity/ownership/no-override/repeated inactivity and absent default listener checks; it also binds the returned bytes digest explicitly. Actual guest validator, guardian scope loader, guardian inventory, VPS status and guest status consumer are exercised locally with the same serialized checkpoint path/hash. OS/package/provider/controller boundaries are injected; no external commands or actual authority issuance are inferred.

Client now uses one monotonic10-second deadline shared across connect, send, receive and final acceptance. Existing frame cap16384, readback9s, server frame1s, guest outer min(12, remaining phase), guest inventory65536-byte output, phase aggregate131072-byte output, archive67108864-byte cap, and17 runtime case names are unchanged.

## Executed evidence

`evidence/baseline.json` records actual pre-implementation own-format positives and bidirectional checkpoint rejection, plus actual finalguard18-second acceptance. `red-admitted.log` records the merged contract rejected by actual canary equality and timeout assertions failing before implementation. The same focused tests subsequently pass in the combined run. The additional guard scope-loader integration is regression coverage added after the initial repairs, not separately credited as test-first.

Final combined run: **92 tests, zero failures/errors/skips/loader errors**:54 preserved canary behaviors (including37 inherited v2 tests),20 original guardian behaviors,12 final host behaviors and6 integrated tests. Synthetic negative subcases are retained inside these tests, not counted as extra top-level tests. Integrated positives include shared bytes through both real validators/context loader and returned digest through actual VPS/guest consumers; negatives cover schema/status/requirement/VM/lease/owner/timestamps/deadline/STOP/inventory/extra keys, changed bytes, active/default listeners/overrides/package integrity. Virtual connect9+receive9 and connect4+send5+receive2 deny; connect2+send1+receive5 succeeds within10. Outer12/remaining2 checks pass.

### Setup issues retained, not feature RED

Initial runs encountered task-local layout symlinks rejected by the original no-follow staging helper, group-writable pre-existing infrastructure ancestors, and imported TestCase double-collection. Fixed only the runner: resolve the input alias to its real original path before unchanged staging, project exact pre-existing infrastructure inodes under the established UNIT_ONLY owner seam, chmod owned source directories, and avoid importing a TestCase class into the integrated test module. A baseline reverse-negative fixture initially lacked deadline and reached timestamp rejection rather than equality; repaired that fixture before implementation and reran both own-format positives successfully. One first-green test used the wrong component's Blocked exception in its injected pin reader; corrected that reader without broadening expectations. A later diff collector encountered binary pycache while attempting UTF8; excluded generated caches, not source. All receipts remain. Original test bytes and expectations are unchanged. The explicit fixture migration upgrades checkpoint fixtures and pins/context, never replaces production validators or weakens test assertions.

## Rerun without overwriting frozen evidence

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/iveri/.hermes/cache/scratch/v4-local-1119 /usr/bin/python3 -B /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/integration-repair-v4/run_tests.py combined-independent
```

Use a new suffix for each review. This creates only new owned evidence receipts plus normal private test scratch; do not run peer verifier/evidence-generating scripts. `baseline-independent` replays owned exact baseline copies. Source freeze and evidence hash maps intentionally occupy different domains.

## Remaining mandatory gates

Genuine independent guardian/orchestrator source-bound reports and approval provenance; honest protected parent-installed context and scoped lease; trusted immutable root bootstrap; fresh real provider/controller/default-daemon inputs; real root→UID1001/GID1002 DAC/UDS peer proof; all17 guest runtime cases including Docker/mount/quota/H2/process settlement/inventory/archive/unmount evidence. No real guest cases executed; no runtime qualification. No VM/daemon/tunnel was touched. No cloud/SSH/Docker/mount/setuid/services/TCP listeners/models/credentials/install/config/global/profile/skill/cron action or spending occurred. Existing suites exercise only their own local IPC/process fixtures and substituted privileged/external seams.

Lesson handoff only: test identical serialized pinned inputs through both components, not independent component-green fixtures. Bound the whole client operation with one monotonic deadline and preserve outer supervision. Preserve latest coherent source improvements explicitly rather than silently reverting to an older reviewed base.
