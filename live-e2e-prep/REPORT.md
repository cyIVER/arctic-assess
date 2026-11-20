# Local preparation — NOT deployment-ready

Implemented and exercised real code-only staging and source bootstrap; no cloud/SSH/Docker/mount/UID/service/listener/model/credential operation was performed. All writes stay in this new lane. No v4 source or peer evidence changed.

## Actual results

`python3 -I -B <lane>/prepare.py <lane>/staged` returned:

```
{"files": 690, "host": 11, "runtime_proof": false, "source": 654, "status": "STAGED_NOT_APPROVED"}
```

`python3 -I -B <lane>/test_local.py` passed 3 tests. Positive calls the REAL reviewed `driver.run`, real `guest.validate`, real `admission_v3.require_current`, and real `guest.guard`, then deliberately stops at injected `verify_owner` before external inventory or first mutation. Only unit fixtures substitute root metadata/current context/status. This is not runtime evidence. Negative cases cover stale creation, .25 budget, .25 reserve, insufficient original STOP, missing context, and unreviewed extra pyc. Launch argv uses `python3 -I -B -c`, no PYTHONPATH; all staged byte hashes and exact file set are checked before driver import. No transport key is accepted or handled by these helpers.

The exact 17 runtime cases remain those in reviewed `driver.ALL_REQUIRED_CASES`; none ran here.

## Decisive blocker reproduced

**Reviewed v4 `canary/guest.py:68` requires `budget_ceiling_usd == 2` and `reserve_usd >= .50`. The newly authorized session is capped at $.25.** Passing `.25` fails before launch, as tested. Do NOT submit invented `$2` authority or spend/reserve values. Parent must decide and independently review an authorization-compatible code change or a justified truthful two-level budget contract before deployment. This lane does not alter frozen v4.

## Hash bases

- Actual v4 source identity raw file: `7b8b8ff769df40567bcf252f0747809be8a8d0e9edce6bcce0069e9a056de0b5`; every member in that identity was checked before staging.
- Independent v4 report raw file: `fbf73ccc6ea879b73b319744774d8692caa5776358ad48e7f196e057adee496d`, copied verbatim.
- Driver: `9dc6b99fdf9d99a3397164dec22a56e99d7c45d453b17bbf5973d0021e350e19`.
- Guardian: `ccb73e2759858887fa82f0354b7f7658e33ed1632e989072cbacb34ed2ac0e7b`.
- Bundle raw manifest `85aef1698ef86d928f4767efcf6754cde410eef959c1bb290340463600e25206`; canonical map `fe8a0c7e2df6e44b343cc2d77e5cce8df8fb64575c958f277ede1042feea279b`.
- Staged manifest: `68c1ff1a6c32905f0a38b0f146d1ea6320d03546244ac03f865680f845d83c71`.
- `staged/evidence/v4-source-identity.json` is a canonical reserialization of the verified identity MAP, not the original raw-byte identity file; never use its hash as the original identity hash.

## Parent-supplied inputs still required (not manufactured)

1. Fresh verified controller record: exact PID/starttime/UID/exe/cmd hash and source path/hash; unchanged original absolute STOP; whole-session <=30 minutes and $.25 ceiling.
2. Fresh post-boot nonmutating default Docker inventory and package/unit ownership, then parent-only stopping service+socket if truly empty and owned. Preserve private daemon 9/44/4 inventory and retained ext4 data. Fresh phase/context/checkpoint must be created AFTER preflight, within 120 seconds of validation; deadline <=600 seconds and STOP >=deadline+30.
3. Root-installed exact canary config; `/run/artex-parent/run-context.json` canonical config binding, typed lease, all seven scoped review records, source/helper/caller/fixture/orchestrator pins, both actual review objects, runtime ELF hashes, preflight path/hash. `guest.validate` requires scoped report equality: status/kind/object_sha256/vm/created/deadline/parent_scope_lease/code_review_handle. `admission_v3` additionally requires guardian/orchestrator report `verdict` PASS/SCOPED_PASS and exact object hash; guardian loader additionally requires `status: approved` and its own source hash. Existing independent v4 report directly binds guardian, NOT the newly serialized orchestrator manifest. Parent must derive source-scoped wrappers from genuine F1–F4 + v4 review evidence; do not invent verdicts.
4. Reviewed protected install routine is NOT assembled here. Install code root-owned/non-writable ancestors, no links/hardlinks/extras; config/context mode600. Intended guest code root `/opt/artex-canary-v4`, helper root `/opt/artex-live-prep`; canonical guardian `/opt/artex-live-guard/guard.py`, runtime scope `/run/artex-live-guard`.
5. Actual SDK code-only snapshot and map at fixed host root `/home/iveri/.hermes/cache/scratch/artex-live-guard-v2` (UID1000). Existing `stage_sdk.py` was read, NOT executed; parent must add/check <=500MB copy bound, preserve normal gcloud account context, copy no auth material. Guard expects digest MAP, not SDK stager's whole records document.
6. Existing parent-established IAP mux at fixed host `iap.sock`, existing approved UI transports, authenticated status server/reverse forwarding 18773 -> guest loopback18774; guard-before-VM-start belongs to parent. Previous familiarization controller/mux is not current evidence. Fresh32 transport key must travel stdin only, never argv/env/log; helper does not create/read one. Parent must separately install private600 host/guest key files consumed by existing guard.

After those gates, the practical source bootstrap argv is produced by `launch.bootstrap_argv('/opt/artex-canary-v4', STAGE_MANIFEST_SHA, '/run/artex-parent/canary.json')`; it imports checked source and invokes actual reviewed driver.main with `--live --config`. DO NOT execute now: budget gate and protected installation/provenance inputs above remain unresolved. `launch.py` CLI itself performs preflight ONLY and fails closed on missing protected input; it does not start the driver.

Files: prepare.py, launch.py, test_local.py, this report, staged code/bundle/manifests. No protected install/config/approval report is claimed complete.
