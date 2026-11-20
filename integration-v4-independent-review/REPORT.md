# Independent V4 integration security review

**Verdict: SCOPED_PASS — pinned source repair only. Runtime qualification: false; live admission remains BLOCKED by external gates.** No operator approval, standing authority, installation permission or approval-status object is issued.

## Scope and identity

Reviewed frozen `coordination-20261119/integration-repair-v4/`, relative to `/home/iveri/work/vindler-e2.SftLYa2R/continuation/`. Read both prior retry REVIEW.md reports. Original F1–F4 remain source-scoped corrections, not runtime proof. This review closes the shared-checkpoint C1/F1 incompatibility and client total-deadline F2 within the source/test boundary below.

| Hashed object (SHA256 of actual file bytes) | Digest |
|---|---|
| source-identity.json | `7b8b8ff769df40567bcf252f0747809be8a8d0e9edce6bcce0069e9a056de0b5` |
| FREEZE.json | `052284ad2331b38f381369cff23f9f6a6c9abf7aae311bd855faf694ae9ba3e5` |
| canary/admission_v3.py | `3a9ed13a30cd81dd9598cd04c569ffa9b008d0cd7281c0a75ab82447712ed6a2` |
| canary/guest.py | `a10992d291e28dfa8bc5ffaee17611dd29889afaf1dff9ed402e9961390a4a86` |
| guardian/guard.py | `ccb73e2759858887fa82f0354b7f7658e33ed1632e989072cbacb34ed2ac0e7b` |
| baseline/final_guard.py | `b54b4b00627193105c3b23621b04b529f3c9ee422842597cd53ccb2901b295ef` |
| baseline/original_guard.py | `4dbee74525efc94a4262d7e297c0922e5ffeeba5c5583b6466454898d6f8a0cd` |

Verified schema/maps and all 40 source entries, 31 evidence entries, report pins and exact non-cache regular-file set. Raw source identity bytes, raw FREEZE bytes, source-file bytes and canonical manifest map are distinct domains. Independently verified raw bundle manifest `85aef1698ef86d928f4767efcf6754cde410eef959c1bb290340463600e25206`, canonical map `fe8a0c7e2df6e44b343cc2d77e5cce8df8fb64575c958f277ede1042feea279b`, all654 source/all11 host members, real helper and original fixture pins. Candidate fixture_service.py is the reviewed wrapper, not the separately pinned original fixture.py.

## Findings and source trace

**No blocking source defect found in this repair.** Exact independently generated `reviewed.diff` confirms only three production changes;28 other copied component members are byte-identical to their latest bases. Guardian retains the final host-role/private staging shield, full SDK manifest checks, isolated interpreter environment, task-path boundary and separate host key/mux paths; it does not revert to the original guard.

- **Shared checkpoint: SCOPED_PASS.** `admission_v3.py:28–40` and `guard.py:230–242` have identical validator ASTs. Exact schema1/verified/requirement/VM/created/deadline/lease handle/parent owner/original STOP/empty inventory object equality denies extras and wrong values. Explicit finite numeric predicates reject bool-as-int/nonfinite timestamps; schema is strict int. Typed lease keys and phase alignment,120-second freshness, unexpired phase and30-second STOP headroom remain. `guest.py:80` supplies actual admission time. `guard.py:251–255` protected pin + explicit returned-byte digest precede commands. Integrated tests pass identical serialized path/hash through actual guest.validate, actual guardian load_scope and guest_inventory, VPS readback/status and guest status consumer. Independent probe also verifies the actual guardian protected reader accepts the same file/hash under explicitly synthetic root metadata.
- **Authority/provenance preserved.** Existing exact canonical654/host11 maps, fixed protected parent context, config/source/report/runtime executable/lease bindings, root no-follow ancestry and immutable pinned reads are unchanged. Checkpoint is evidence, not authority. Existing independent report JSON fields are not treated by this review as real approval issuance. Provider/controller identity, original absolute STOP, network/SA/disk checks and cost ceilings remain unchanged.
- **Real-default evidence requirement preserved.** Guard still requires exact empty containers/images/volumes checkpoint plus fresh version/package integrity, package-owned protected service/socket units without drop-ins, inactive state/MainPID0, repeated inactivity and no default socket listener (`guard.py:256–271`). Local command/package seams are injected; actual emptiness and provenance of a parent-produced checkpoint are external gates, not established here.
- **Total deadline: SCOPED_PASS.** `guard.py:318–334` uses one monotonic10-second deadline beginning before request construction, passed to connect, send and read_frame and rechecked before acceptance. No new receive budget is started. Virtual9+0+9 and4+5+2 deny;2+1+5 succeeds. Existing9-second readback,1-second server frame and guest outer `min(12, remaining_phase)` are unchanged. Integrated assertions confirm outer12 and remaining2.
- **Fixture migration is explicitly unit-only.** `fixture_migration.py` updates serialized checkpoint fixtures/context pins and owned host scratch; it does not replace a production validator. It preserves negative assertions. Old stale-inventory negatives can now also reject timestamp/lease inconsistency; independent probes separately exercise actual freshness with unchanged, valid pinned checkpoint bytes and advancing time. Root/UID projections and injected external readbacks are not privileged qualification.

**Nonblocking documentation caveat N1:** candidate REPORT.md:29–35 recommends its own run_tests.py with a new suffix. That runner still writes into candidate evidence and creates candidate host-scratch. A new suffix does not preserve an immutable exact file set. Do not use that command for frozen review; use an output-redirected adapter. No frozen documentation was changed.

## Reproduced execution

Inspected every executed test module and fixture/runner side effects before execution. Actual local work: owned fixture files, UDS/socketpair, stdin-bounded caller self-tests, short-lived owned subprocesses/fork/pidfd, fake Docker/provider/package command seams. UID/chown/service/cloud paths are substituted, not executed.

Commands (absolute own directory prefix omitted below):

```
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B run_review.py combined-review-final
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B independent_probe.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B verify_preservation.py
```

- Final combined run: **92 tests,0 failures,0 errors,0 skips,0 loader errors**,92 unique IDs.54 canary (including37 inherited v2),20 original guardian,12 final host,6 integrated. Full logs and IDs: `evidence/combined-review-final.{log,json}`.
- Independent supplementary execution:31 assertion records, consisting of same-entrypoint positive,23 malformed checkpoint variants rejected by both actual validators before any inventory command,6 time-bound rejections and actual protected-file same-path/hash positive. Missing every checkpoint field, extra top/nested inventory field, wrong lease/owner/VM/status/nonempty inventory, bool schema/timestamps and NaN/Infinity all deny. `supplemental.json` records actual outcomes; these are not added to92 unittest cases.
- First reviewer run:92 collected,0 failures,4 errors caused solely by reviewer scratch path exceeding AF_UNIX pathname capacity. Preserved in `evidence/combined-review.{log,json}`. Corrected only owned adapter scratch to a short directory beneath `$TMPDIR` base, without editing frozen tests/source or suppressing assertions; final rerun is clean. No candidate defect inferred from this reviewer setup issue.

Test preservation is precise, not repository-wide: all copied inherited test bytes and37 v2 IDs are unchanged. The candidate intentionally does not copy every parent document/verifier/evidence/test file. `verification.json/not_copied_parent_members` enumerates exclusions, including final parent's `test_integrated.py` (an older two-proof/default_inventory_proof contract, not part of the declared92). That file was inspected but not executed or silently counted as preserved/executed coverage. The reviewed repair chooses a single shared checkpoint rather than that obsolete two-object fixture. Fresh per-nonce readback behavior is unchanged and original protocol tests run; no claim is made that every historical integration experiment ran.

## Preservation and boundaries

`before.json` and `verification.json` independently bind all78 candidate regular files (including pre-existing caches), sizes/modes and all three source-input link targets before/after. All are unchanged. All1487 parent-manifest file bytes match historical before/after maps and current bytes. Latest/original guard baseline copies match their respective real originals. No frozen artifacts or peer receipts were written. No deletion operation was performed by reviewer tooling; normal test TemporaryDirectory cleanup remains part of inspected suites. Disk/persistence verification succeeded; final verification reported1,719,300,096 free bytes. Own JSON evidence was read back and parsed successfully.

All17 required guest case names remain unchanged and **0 real guest cases executed**: aggregate-output-exhaustion, app-data, confinement, environment-proxy, fifo-create, fifo-read, fixture-http, fixture-ordinary-swap, fixture-symlink-swap, host-absence, inflight-cancellation, phase-restart, quota-enospc, setsid-success, timeout-setsid, work-ordinary-swap, work-symlink-swap.

Remaining mandatory external gates: exclusive VM ownership and standing approval/derived scoped lease/cost headroom; genuinely independent source-bound reports; honest protected parent-installed context and root immutable bootstrap; fresh real provider/original STOP/controller/default-empty evidence; distinct protected task key and approved existing private mux; actual root→UID1001/GID1002 DAC/UDS peer isolation; all17 real Docker/mount/quota/H2/cleanup/process/inventory/archive/unmount cases and persistence readbacks. No cloud, SSH, Docker, mount, UID change, service, TCP listener, model, credential/config/profile/global/skill/install/download/spend operation occurred. No authority or operator approval status was minted.

Lesson handoff only: test the same serialized pinned object through both components; carry one monotonic deadline across every transport stage; redirect both evidence and fixture scratch before rerunning frozen suites. Enumerate omitted historical tests instead of implying complete parent-tree preservation.
