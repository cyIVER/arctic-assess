# Independent canary-v3 retry review

**Verdict: CHANGES REQUIRED for integration; SCOPED_PASS for the original F1–F4 source corrections. Runtime admission remains BLOCKED.** This report does not grant authority, install approval, or qualify a real guest. The new integration finding below is fail-closed incompatibility, not an approval bypass.

## Finding C1 — incompatible shared preflight object (blocking, Medium)

`artex-worker-guest-canary-v3/admission_v3.py:61–63` requires the pinned checkpoint to equal an exact object with `status:"verified"`, `requirement:"already-private-default-quiescent"`, VM, created/deadline, lease handle and default-service owner. Extra keys are rejected by dictionary equality.

`artex-worker-live-guard-final/guard.py:236–240` reads the **same** context `preflight` reference and requires `status:"READY"`, `default_inventory`, and `external_stop`. Its context loader binds that reference to the shared run-context (`guard.py:123–127`). No single checkpoint JSON can satisfy both contracts; parent installation or fresh timestamps cannot reconcile contradictory status values. Adding inventory/STOP keys also violates canary's exact-object equality.

Reproduction: imported the inspected guardian source without invoking its CLI; called actual `guest_inventory` with the exact canary-required checkpoint returned by an injected reader and a forbidden external runner. Result: `Blocked: preflight stale/scope`, **zero runner calls**. See `supplemental_review.py` and `supplemental-results.json`. No cloud, SSH, service or Docker operation occurred.

**Required handoff:** agree on one typed immutable checkpoint schema, or explicitly bind separate authority and inventory checkpoint references and define which digest status returns. Preserve standing authority, exact source/review bindings and fail-closed readbacks. Freeze new identities and independently review/test the actual combined seam before using either component. No source repair was made in this review.

## Original findings

- **F1 — SCOPED_PASS, source only.** `guest.py:118–119,155–169` and `driver.py:150,163` provide separate root-controlled0711 UDS/0755 executable directories, root0555 pinned caller copy, socket1001:1002/0600, expected peer1001, and actual Popen `user=1001, group=1002, extra_groups=[], cwd='/', close_fds=True`. Key/request remain stdin-only; clean environment and private controller0700 are preserved. Frozen ControlServer checks Linux SO_PEERCRED before HMAC/request processing. `fixture_service.py:10–17,28–30` chdirs after UID/GID drop and closes every inherited descriptor except the startup pipe. Real owned fork/FD and Popen tests passed, but UID overrides/chown are substituted locally and DAC assertions are symbolic. No real root→1001 proof.
- **F2 — SCOPED_PASS for authority rejection mechanism, not authority issuance.** Concrete canonical654/host11 maps and exact helper/caller/fixture hashes match real objects. Fixed `/run/artex-parent/run-context.json` binds canonical config, scoped lease, reviews, guardian entrypoint, real report-object references and runtime executable hashes. Missing/writable context and nonpassing independent report objects are denied in local tests. Replaying the original fabricated old-manifest/arbitrary-helper/lease/review operation now rejects it. Root-owned trusted-parent installation and genuinely independent report provenance remain prerequisites; JSON `PASS`/`approved` fields do not create approval. C1 blocks the current combined guardian seam.
- **F3 — SCOPED_PASS within the documented trusted bootstrap/no-writer boundary.** `guest.py:33–56` checks every opened ancestor owner/mode with openat/O_NOFOLLOW; leaves must have trusted owner, regular type, nlink1, nonwritable mode, cap and exact hash. Executable/ELF checks apply to helper/caller/runtime executables. Config/context use protected JSON. Reviewed host/runtime dependencies compile verified bytes, not reopened pathname bytes or pycache. Other pathname consumption is safe only after the parent installs the exact immutable root-owned staging tree with clean trusted interpreter/import environment; the component cannot retrospectively authenticate its own bootstrap. Writable-ancestor and untrusted-owner negatives pass after same-entrypoint positives. Local original-input staging verifies hashes and no-follow ancestry; it is STAGED_NOT_APPROVED, not the authority installer.
- **F4 — SCOPED_PASS for the collision and settled-writer archive fixes.** Exact quota literal records cleanup ownership only after exclusive open and retains device/inode; replacement is refused; cleanup attempts all recorded names and preserves an active primary exception. Original collision replay yields FileExistsError and preserves the valuable file. Archive uses directory-relative no-follow/nonblocking regular single-link FD opens, identity and metadata checks, same-object read/hash/member insertion, and the same archive FD for fsync/readback/hash. Leaf swap negative passed. An additional actual archive-path substitution probe confirms returned hash consumes the original open archive FD, not substituted pathname bytes. Final pathname integrity still requires protected parent/no-live-writer settlement; this is not a claim of atomic inode-conditional unlink against arbitrary concurrent adversaries.

## Executed evidence

Inspected all test modules and both verifier scripts before execution. Did **not** run frozen `verify_v3.py`, because it overwrites frozen evidence. Used a reviewer-owned output-redirected runner against unchanged source; normal synthetic staging tests create their own temporary fixtures and fake Docker never invokes Docker.

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/iveri/.hermes/cache/scratch python -B /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/gate-canary-review-retry/run_local_review.py
# exit 0; 54 tests, 0 failures, 0 errors, 0 skips, no collection errors

PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/iveri/.hermes/cache/scratch python -B /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/gate-canary-review-retry/supplemental_review.py
# exit 0; original negative replay passes, archive FD binding passes,
# actual guardian checkpoint incompatibility reproduced before external runner,
# default CLI BLOCKED/2, 37 inherited test names retained, 54 total,
# 17 required guest cases enumerated, 0 guest cases executed
```

`local-tests.json` records every executed test ID; `local-tests.log` contains real unittest output. `review-replay.log` and `supplemental-results.json` preserve supplemental outcomes. No Go build/tests were run; caller/helper equality carries only byte identity to the previous independently reviewed objects, not new Go execution evidence.

## Identity and preservation

Source-file bytes, canonical manifest maps, raw manifest bytes, and review-report bytes are different hash domains. Full exact path/hash maps are in `hashes-before.json`, `hashes-after.json` and `concrete-objects.json`.

- v3 source identity bytes: SHA256 `e7fa39bf9c062d1c1a53269730b9afca7eed371dcbd87596cc358a22b8944023` (34 source/doc/test/binary members).
- v3 FREEZE bytes: see report.json `identity.canary_freeze_sha256` (computed, not inferred).
- v3 author report bytes: SHA256 `9e2df8edf601e199e3cba32e84341086f9671e698edf38dcafc39bd348b2af9d`.
- guardian integration source `artex-worker-live-guard-final/guard.py`: SHA256 `b54b4b00627193105c3b23621b04b529f3c9ee422842597cd53ccb2901b295ef`; inspected only, **not guardian security approval**.
- combined raw manifest: SHA256 `85aef1698ef86d928f4767efcf6754cde410eef959c1bb290340463600e25206`; canonical-map SHA256 `fe8a0c7e2df6e44b343cc2d77e5cce8df8fb64575c958f277ede1042feea279b`. All654 source and11 host members matched.
- helper bytes: SHA256 `ea54b361fed9d575eaadcd069b59382d853c241abee4821dbd7f02f4fac765ac`.
- caller bytes: SHA256 `7f9a360e2925e2bfaa257ce8975ac344e9e4f2ddfec879d5d0991821c22ba746`.
- actual fixture bytes: SHA256 `49e1f487b407ebff7bf0d79f5f2e6137b38d6955c4c1ca1e9a4becb15e20a08d`.

All v3 source and FREEZE-listed evidence hashes matched before tests; every tracked v3 object remained identical afterward. All23 v2 source members plus its source identity/FREEZE bytes remained identical. Delta:11 additions,7 changed paths,16 unchanged paths,0 removals; the7 changed paths and full diff are retained in `v2-v3.diff`. All inherited test file bytes are unchanged. Guardian source identity was also unchanged across seam inspection/probe.

## Issues, omissions and remaining gates

Initial reviewer hash script assumed v2 FREEZE had a `source` key and raised KeyError before persisting its snapshot. Corrected the **reviewer's schema handling**, reran successfully before any tests; this was not candidate drift or a candidate test failure. Neither executed local test run had setup failures/skips. Disk remained available (2,048,434,176 bytes at post-test check); reviewer hash receipts were read back successfully. No shortage/persistence failure and no cleanup operation was performed. Prior partial retry artifacts were not treated as completed reviews.

Remaining: C1 reconciliation; independent guardian security approval; actual source-bound approved report objects and protected parent-installed context/derived lease; immutable root-owned bootstrap; fresh real provider/controller/default-daemon readbacks under the original STOP/cost ceiling; actual root→UID1001/GID1002 caller DAC/UDS peer admission and target startup; all17 real guest cases plus Docker/mount/quota/H2/process cleanup/inventory/archive/unmount readbacks. Native/normal-model admission remains outside this literal lane.

Only new `coordination-20261119/gate-canary-review-retry/` review artifacts were written. Tests used owned ephemeral scratch; no frozen source/evidence, peer artifacts, profiles, global skills, credentials or config were changed. No cloud/SSH/Docker/mount/setuid/service/TCP listener/model/install/spend action was executed.

Lesson handoff only (no shared-skill edits permitted): paired components sharing a pinned reference must be tested with the identical serialized object, not two individually passing fixtures with incompatible schemas. Redirect immutable-snapshot test outputs instead of rerunning evidence-overwriting verifiers.
