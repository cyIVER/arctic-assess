# Concrete live guard — LOCAL ONLY / NOT LIVE-ADMITTED

Only this directory was authored. No cloud/SSH/server/service commands were executed. `guard.py` implements the complete read-only path; ordinary invocation without protected parent input prints **BLOCKED** to stderr, no stdout, exit **2**. Synthetic tests are UNIT_ONLY, not cloud/controller/guest operational evidence.

## Actual future path

Guest root executes `/opt/artex-live-guard/guard.py --status` (executable0555, fixed shebang). It authenticates a nonce/timestamp status-only frame to guest loopback18774. An **existing** private IAP SSH ControlMaster reverse-forward carries that frame to VPS loopback18773. VPS verifies HMAC, exact request fields, freshness and replay exclusion, then calls `VPSGuardReadback.status()`:

1. Retain pidfd; check external controller UID, `/proc` start ticks, canonical executable, public command SHA and script argument; reject dead/zombie/current RPC/direct RPC child.
2. Fresh normal-context `gcloud compute instances describe` for the one fixed VM; require exact ID, RUNNING, one original NIC/IP, no external IPv4/IPv6 or service accounts, retained original boot disk, automaticRestart=false, STOP at **the original absolute deadline**.
3. Fresh `gcloud compute disks describe` for fixed retained disk ID.
4. Existing-mux-only SSH executes **one fixed** guest root inventory command. Missing mux cannot fall back to a new connection (`ProxyCommand=/usr/bin/false`). Guest checks protected pinned READY preflight, age<=120 seconds, exact VM/deadline and prior empty default inventory; actual package versions/integrity, original package-owned root-protected units/no drop-ins, inactive docker.service/docker.socket/MainPID0, second fresh inactive checks, and absence of default listening Docker socket. It never opens the default Docker API (socket activation would mutate state).
5. Recheck controller identity/pidfd and lease; return only the exact eight-field v3 dictionary, HMAC-bound to request nonce. No cached cloud proof, raw API result, raw argv, vendor credential or key is returned/logged.

Readback command budget is9 seconds total; request frame has an absolute1 second bound; guest client is bounded10 seconds. **Integration gate:** current peer `guest.py:169` has timeout2; its owner/parent must independently change/review the bounded guard timeout to accommodate10 seconds (e.g.11 seconds including scheduling margin) without extending the canary phase. This directory does not modify peer files.

## Root authority / required input contracts

Parent root and kernel are trusted; UID1001/helpers, arbitrary user JSON, RPC callers, and model-bridge clients are not. Root can forge records and is explicitly outside this threat model. No report-file string is independently operator approval. Parent installs an allowlist only AFTER real independent review of frozen source/controller/SDK. Missing any live input is a named external gate, not an inferred approval.

All staging ancestry must be root-owned/non-group-or-other-writable/no-symlinks. `/opt/artex-live-guard/guard.py` must match the root-installed `/opt/artex-live-guard/allowlist.json` `guard_sha256` and fixed v3 `/run/artex-parent/run-context.json` `guardian_implementation`. Parent/transport files have root-only0700 parents and0600 files. Runtime mux sockets are not code artifacts. The guest does not need SDK, provider account, controller source, or metadata credentials.

`allowlist.json` fields:
- `guard_sha256`: actual frozen guard.py hash (see artifact-hashes.json).
- `guardian_review`: `{path,sha256}` for the real independent root-installed report, also EXACTLY `run-context.guardian_review`; report must contain `status:"approved"`, `object_sha256:<guard SHA>` (additional report evidence may be present).
- VPS-only `controller_sha256`, `controller_exe_sha256`: actually reviewed controller script and resolved interpreter hashes.
- VPS-only `gcloud_manifest:{path,sha256}`: root-installed JSON mapping EVERY relative regular SDK file to byte SHA256. Entire SDK is protected and exactly matches this map; symlinks/extras/missing files deny. Stage reviewed official cached SDK under `/opt/artex-live-guard/google-cloud-sdk`; do NOT stage or copy auth files. Script uses normal existing account context via HOME=/home/iveri, never opens/copies/logs credential files itself. Parent must establish this root-run normal-context CLI works; otherwise BLOCKED. This protected SDK staging gate is intentionally not bypassed by the currently user-owned local gcloud wrapper.

`/run/artex-live-guard/parent.json` contains fixture shape in `test_guard.fixture()` PLUS `parent_scope_lease` copied EXACTLY from the real parent context. Fixture itself is NOT usable authority. Required exact shared context fields: vm, lane, guard_created, external_stop, controller_id, preflight, parent_scope_lease. VM is the exact five-field VM constant. network contains exact project-relative network/subnetwork and original private networkIP from the real prestart readback, not a caller-provided acceptable network. controller binds actual pid, uid, start_ticks, resolved exe, SHA256 of NUL-delimited public `/proc/PID/cmdline`, and `{path,sha256}` script/checkpoint references. Script must be approved source, not arbitrary title bytes; its checkpoint must be its adjacent `approval-checkpoint.json` and contain the same original deadline. Parent launches/owns the independent stop controller BEFORE VM start; this guard NEVER starts one or extends a lease. Approved maximum external_stop-guard_created is5400 seconds; prefer3600. Actual process identity is checked on EVERY request, not taken from a mutable status file.

Preflight pinned object: `{vm:VM,status:"READY",created:<fresh real UTC seconds>,external_stop:<original epoch>,default_inventory:{containers:[],images:[],volumes:[]}}`. Parent must derive this from the actually approved empty-default preflight, not invent/refresh its timestamp. It is bounded data evidence of prior empty inventory, NOT authority; live inactive/package/socket readback is independently required. It expires after120 seconds; a later canary requires a genuinely fresh approved checkpoint and new correctly pinned parent context, never a touched file. Guard does not pause/restart any unit. Root-trusted preflight producer/review and actual default daemon quiescence remain external gates.

`/run/artex-live-guard/transport.key`: fresh **32 binary bytes**, root0600 within0700, distinct from ALL model/control bridge keys. Same task-only bytes installed on VPS and guest by trusted parent over the existing mux, stdin-only, never argv/env/log/chat. Helper namespace must have NO mount/access to these paths, host loopback bridge or SSH mux. Root-only files prevent helper authentication even where network isolation fails; namespace/loopback denial still requires the parent's actual guest isolation test.

## Future parent-only command templates — NOT EXECUTED HERE

Preconditions: separately approved fresh lease/budget/controller and provider STOP already verified, exporter relinquished exclusive VM ownership, root-protected reviewed staging/context installed on BOTH sides, existing IAP mux available at VPS `/run/artex-live-guard/iap.sock`. No new IAP login/session, public port, service account, IAM or VPC changes. Controller/script/checkpoint cannot be worker-writable. Do not reuse old PID/deadline/key.

Generate transport bytes on VPS as root, without output, after exclusive fresh0700 task directory exists:

```sh
sudo /usr/bin/python3 -I -c 'import os,secrets; p="/run/artex-live-guard/transport.key"; f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,secrets.token_bytes(32)); os.close(f)'
```

Install the bytes over existing mux stdin only (no token in argv/environment; guest task directory already root0700):

```sh
sudo /usr/bin/python3 -I -c 'import sys;sys.stdout.buffer.write(open("/run/artex-live-guard/transport.key","rb").read())' | ssh -S /run/artex-live-guard/iap.sock -o ControlMaster=no -o ProxyCommand=/usr/bin/false -o BatchMode=yes vindleradmin@vindler-lab-01 'sudo -n /usr/bin/python3 -I -c '\''import os,sys; b=sys.stdin.buffer.read(33); assert len(b)==32; f=os.open("/run/artex-live-guard/transport.key",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(f,b);os.close(f)'\'''
```

Source copy template (parent installs same reviewed allowlist/context through its existing trusted staging procedure; do not treat SFTP ownership as root protection):

```sh
/usr/bin/python3 -I -c 'import sys;sys.stdout.buffer.write(open("/home/iveri/work/vindler-e2.SftLYa2R/continuation/artex-worker-live-guard/guard.py","rb").read())' | ssh -S /run/artex-live-guard/iap.sock -o ControlMaster=no -o ProxyCommand=/usr/bin/false -o BatchMode=yes vindleradmin@vindler-lab-01 'sudo -n /usr/bin/python3 -I -c '\''import os,sys;b=sys.stdin.buffer.read(1048577);assert len(b)<=1048576;f=os.open("/opt/artex-live-guard/guard.py",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o555);os.write(f,b);os.close(f)'\'''
```

Foreground root VPS server, within parent-owned bounded process supervision (not a daemon/cron; no service registration):

```sh
sudo /usr/bin/python3 -I -B /opt/artex-live-guard/guard.py --serve
```

Existing-mux reverse forwarding, loopback BOTH ends, distinct from model bridge:

```sh
ssh -S /run/artex-live-guard/iap.sock -O forward -o ExitOnForwardFailure=yes -R 127.0.0.1:18774:127.0.0.1:18773 vindleradmin@vindler-lab-01
```

Actual future readback:

```sh
ssh -S /run/artex-live-guard/iap.sock -o ControlMaster=no -o ProxyCommand=/usr/bin/false -o BatchMode=yes vindleradmin@vindler-lab-01 'sudo -n /opt/artex-live-guard/guard.py --status'
```

After phase, parent closes **only this owned forwarding** using `-O cancel -R 127.0.0.1:18774:127.0.0.1:18773` on the same mux and reaps its own guard process through stable identity. This code has no process-kill/start/stop/cloud mutation route. Parent retains independent absolute STOP ownership regardless of guard failure.

## Verification limits

`python3 -m unittest discover -v` exercises the actual implementation with injected provider/SSH command runners; private socketpair framing and real local pidfds are exercised without opening TCP or external services. Root-file positive fixtures use explicitly synthetic UID/directory-mode projection (not a real privileged install); the local fixture PID positive projects the caller identity to model an independent sibling, while real direct-child denial is also asserted. This does NOT establish guest root-to1001 isolation or provider behavior. Main default BLOCKED is exercised as a real isolated Python subprocess. Initial implementation tracer was observed RED before implementation; later tests are regression additions, not claimed test-first history for every branch. A synthetic transport fixture length error was repaired before GREEN. No live result is claimed.
