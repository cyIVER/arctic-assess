# Independent live-guard retry review

**Verdict: CHANGES REQUIRED for live-guard + canary-v3 integration; live admission remains BLOCKED.**
This is a source audit and safe local reproduction, not approval or privileged/runtime qualification. No approval object was minted. The historical partial review is not adopted as a verdict.

## Frozen objects and evidence

Paths below are relative to `/home/iveri/work/vindler-e2.SftLYa2R/continuation/`.

| Object (source-file bytes unless stated) | SHA256 |
|---|---|
| `artex-worker-live-guard/guard.py` | `4dbee74525efc94a4262d7e297c0922e5ffeeba5c5583b6466454898d6f8a0cd` |
| `artex-worker-live-guard/test_guard.py` | `1bffcaf8ba0f1f0e757e46b3406331da62e83b0ad2a7f99bf1c7a6ebc28d7492` |
| `artex-worker-live-guard/test_security.py` | `11e14db83463b54b50e40335914a0ba42a855541f9bd105385466ebfee49da33` |
| `artex-worker-guest-canary-v3/GUARD-INTERFACE.md` | `c4e506c883d592ec688e60cfcee42b3aaae1b2f7b8824d82bcf3a02c745a428a` |
| `artex-worker-guest-canary-v3/guest.py` | `c51d2f0bddef4fe38af25378b3589437fc018fd8ed0bc07fd0ae3a5b714b3326` |
| `artex-worker-guest-canary-v3/admission_v3.py` | `5aefde551ac5f900400c520162a2e582d5903a8cce2dac22ad6e9d8dc21a4387` |
| `artex-worker-guest-canary-v3/driver.py` | `9dc6b99fdf9d99a3397164dec22a56e99d7c45d453b17bbf5973d0021e350e19` |

`before.json` and `after.json` pin 58 non-cache files in the two component directories, including original receipts/manifests. This is preservation coverage, not a claim that all v3 code/tests received a complete security audit. Direct review covered guard source/tests/README/verifier/receipt/hash manifest, v3 interface, guest admission and guard call, admission_v3, driver guard call sites, and reviewed_imports. Original guard artifact hashes matched current file bytes; isolated copies matched their source. See `verification.json`.

### Actual commands and results

All runtime work occurred in this owned directory; Python bytecode disabled and TMPDIR set to this directory for suite subprocesses. Tests were inspected before execution. No original verification script was executed in its source directory because it writes receipts there.

1. `cd unit-copy && PYTHONDONTWRITEBYTECODE=1 TMPDIR=<owned-review-dir> /usr/bin/python3 -B verify.py` — exit0, **20 tests, 0 failures, 0 errors, 0 skips, 0 loader errors**; independently reproduced on Python3.12.3. `unit-tests.log` and `unit-copy/evidence.json` retain complete output.
2. `/usr/bin/python3 -B reproduce_contract.py` — exit0; actual guest_inventory rejects a v3-valid preflight before any runner invocation; actual AST-extracted v3 checkpoint equality rejects a guard READY checkpoint. `contract-reproduction.json` records the result.
3. `/usr/bin/python3 -B test_review_boundaries.py` — exit0; **3 additional independent local probes**, no failures/skips: actual readback response shape accepted by actual guest.guard, 12-second outer timeout/deadline reduction, and virtual-clock reproduction of the client's non-total10-second bound. `boundary-tests.log` records output.

The original 20 count excludes these three probes and the standalone contract reproduction. No v3 full suite, privileged test, cloud call, SSH invocation, Docker invocation, mount, UID change, service operation, TCP listener, model call, installation, credential/config access or spending was performed. Socketpair and inspected local fixture subprocess/pidfd tests were the only real IPC/process boundary exercises. Synthetic root metadata and process-parent projection are not real root or sibling-controller proof.

## Findings

### F1 — HIGH / integration blocker: mutually exclusive preflight formats

- `guard.py:79-82` binds `parent.json.preflight` exactly to the fixed parent run-context. v3 `admission_v3.py:43-44` binds that same context preflight to config. Both independently pin the referenced bytes.
- `admission_v3.py:61-63` requires the **exact** checkpoint object with `status:"verified"`, requirement, VM, created, canary deadline, parent lease handle and default-service-change owner. It permits no extra fields.
- `guard.py:200-204` requires that same pinned object to have `status:"READY"`, external_stop and empty `default_inventory`, with age at most120 seconds.
- Therefore no parent-installed preflight object can satisfy both contracts, even with honest root staging and perfect live provider/controller state. This is not a missing operator approval or runtime environment issue.
- Reproduction: `reproduce_contract.py` calls actual guard.guest_inventory with injected bytes and a runner that must not run; it gets `Blocked('preflight stale/scope')`. The actual v3 equality expression accepts those same v3 bytes but rejects READY bytes. Zero commands executed.
- Required correction: owners must agree one shared checkpoint schema, or explicitly separate and bind the two evidence objects to the same parent lease/VM/original STOP. Preserve the distinction between actual inventory evidence and authority. Add an integrated positive using the same preflight path/hash at both validators; do not simply loosen freshness or synthesize an approval. Freeze/re-review the changed source tuple.

### F2 — MEDIUM / timing-contract defect: client10 is not an end-to-end10 bound

- `guard.py:269-270` allows up to10 seconds for connection, sets a new10-second send timeout, then `read_frame()` starts another absolute10-second receive budget. There is no single client-call deadline.
- `test_review_boundaries.py` demonstrates an otherwise valid request/response accepted after **18 virtual seconds**: connect9, readback/receive9. It uses a fake socket/virtual clock, no network and no real wait. Request age at arrival is9; response timestamp is fresh.
- Actual canary `guest.py:173` separately bounds the subprocess by `min(12, remaining_phase_time)`, so this is **not a bypass of the canary outer bound**. It can instead reject a valid slow response; standalone client callers do not have the claimed total10-second guarantee.
- Required correction before relying on a 9/10/12 timing contract: enforce one monotonic client budget across connect/send/receive or accurately specify per-stage bounds and retain outer supervision. No new signing framework is needed.

### N1 — documentation drift, not an outstanding timeout2 implementation defect

Guard README:15 says peer guest.py has timeout2 and needs a change. Actual frozen v3 `guest.py:173` already uses12 seconds, reduced to remaining phase time, matching GUARD-INTERFACE:5. Local probes verify this. Do not send the peer through an unnecessary timeout2 repair loop; update documentation only under owner control.

## Security and integration trace

- **Provider/controller:** `VPSGuardReadback` uses fixed account/project/VM describe and disk describe argument vectors, never a caller command. It retains a pidfd across readback; checks non-self/direct-child, non-zombie/dead process, UID, start ticks, resolved exe, command-byte SHA and script argument; checks identity again before returning and closes retained descriptors. VPS loader pins reviewed script/interpreter and adjacent checkpoint deadline. Provider checks exact VM/disk IDs, RUNNING, single exact original network/subnetwork/privateIP, no SA, external IPv4/IPv6 absent, retained boot disk, automaticRestart false and original absolute terminationTime with STOP. Clock/lease bounds are checked before and after. This is implemented source behavior plus injected negative tests, not a live controller qualification. No concrete new controller PID/script/checkpoint/SDK installation was supplied or endorsed by this review.
- **Default daemon:** pinned fresh inventory, exact versions/dpkg verification, package-owned protected unit paths/no drop-ins, inactive service/socket/MainPID0, repeated inactivity checks and absence of listening default socket. Guard never contacts Docker API or starts/stops a unit. Preflight producer accuracy and actual quiescence remain parent runtime gates. Its120-second age means it cannot support an arbitrary full600-second phase from one old checkpoint; schedule within freshness or obtain genuinely fresh approved evidence, never touch the timestamp.
- **Protocol:** exact route/envelope/request keys, 32-byte key, canonical HMAC-SHA256 and constant-time comparison, 64-hex nonce, ±10-second timestamp checks, bounded frame length, replay cache/cap, nonce-bound authenticated response and exact expected status. Request payload cannot select scope, PID, VM, deadline or commands. Replay protection is per server process; use a fresh task key on restarts as documented. No model/control bridge key reuse.
- **Trust/bootstrap:** fixed protected allowlist, source self-pin, root parent/context bindings, root-installed pinned review object bound to source hash, canonical entrypoint, root ownership/non-writable ancestry and no symlinks. VPS additionally validates full SDK file set and source hashes. These establish provenance only when trusted parent stages honestly reviewed immutable bytes; `status:approved` strings alone are not independent approval. v3 additionally requires actual pinned guardian/orchestrator reports and exact source/config/runtime tuple. This report deliberately supplies no approval status.
- **Key handling:** protected32-byte root0600 leaf under0700 parent; no key argv/env/log output in source. Existing-mux stdin staging templates remain unexecuted. Helper namespace must lack key/mux/root-path access and host loopback reachability; actual root-to1001 isolation is not proven locally.
- **Budgets:** readback monotonic9-second shared command budget; server request frame1 second; client per-stage10-second bounds (F2); actual v3 outer12-second/deadline-limited subprocess and clean environment. No change to canary phase or original STOP is authorized.

## Remaining external gates (not replaceable by these local tests)

1. Resolve F1 and F2, freeze/review actual changed objects and re-run integrated local tests with a shared checkpoint. Parent must independently assess real report provenance; this review cannot be installed as an approved guardian object.
2. Fresh exclusive VM ownership and independently authorized parent lease/cost headroom; original absolute provider STOP/retained disk/no-public-IP/no-SA/original network readback; independent live stop controller created before start and proven by real stable identity. No old PID/deadline/key reuse or lease extension.
3. Trusted root immutable staging of reviewed guard/controller/interpreter/full official SDK, canonical allowlist and real independent reports; honest fixed run-context and actual validated preflight evidence. Establish the root-run existing normal gcloud account context without copying or logging auth material.
4. Existing approved private IAP mux only, loopback-only status forwarding on separate ports, fresh distinct32-byte task key transferred stdin-only and protected both sides, bounded owned process supervision and owned-forward cleanup. No SSH fallback or new/public tunnel.
5. Actual guest package/unit/socket state and fresh empty-default evidence; no default activation by guard. Separate parent authority owns any preflight service changes.
6. Actual v3 guest-root→UID1001/GID1002 caller/control/namespace/mount/runtime canary, helper inability to access guardian key/mux/loopback/root files, true Docker/runtime confinement, cleanup/cgroup/process settlement, and real persistence proof under approved bounds. Local source/tests do not satisfy those gates.

## Handoff lesson (not saved globally)

Contract-review the same pinned preflight bytes through both guardian and orchestrator before requesting privileged qualification. Component-green tests and matching response dictionaries miss mutually exclusive input schemas. Verify current integration timeout in source rather than repeating stale README claims. No profile, global skill, peer source or peer evidence was modified.
