# DVWA target: local preparation receipt

## Status and scope

**Prepared; not deployed or runtime-qualified.** Public official GitHub/registry HTTPS metadata was retrieved with default TLS verification. No image layers downloaded; no Docker/SSH/cloud/mount/service/model execution, spending, credentials/profile changes, or changes outside this new directory. Tests use a mocked Docker driver only. Any `STOPPED` line in test output is from that mock, not an actual container operation.

## Verified acquisition metadata

Collected UTC: 2026-11-20T00:53:55.504088+00:00. See `pins.json` for complete manifest layer descriptors, configuration, image labels, and immutable references.

| Item | linux/amd64 manifest digest | Compressed layer bytes |
|---|---|---:|
| Official `ghcr.io/digininja/dvwa:latest` | `sha256:dac25485c8e1e4b730109398140671991417b7a4ea56d443e113aba6412586a1` | 212594371 |
| Official `docker.io/library/mariadb:10` | `sha256:135c49b72e97143b73cc273dcdc95d2b035e3ebfbd536c3d72c65b715a8e06b5` | 104479213 |

Deduplicated compressed layer transfer: **317073552 bytes (302.3849 MiB)**, below the conservative 1800000000-byte remaining transfer budget. Repeated empty layer descriptors account for the distinction between sum of descriptors and deduplicated size. Config blobs are 14273 and 8788 bytes; indexes/manifests and downloaded source are additional small metadata. This is **not** an unpacked disk estimate: Docker storage, archives, and duplicate copies need additional disk headroom. No layer contents were available for unpacked-size verification; parent must check real disk budget before acquisition/import.

Metadata collector verifies platform, manifest SHA-256, config SHA-256, and sums layer descriptors. Anonymous registry bearer tokens live in memory only and are not written or printed. `acquire_metadata.py` is a reproducible **tag-resolution tool**: rerunning can update pins, so do not rerun during the approved run without reviewing changes.

Official source commit: [`502ac150ce37c20ca6e04cab7c5ca959f315f2d0`](https://github.com/digininja/DVWA/tree/502ac150ce37c20ca6e04cab7c5ca959f315f2d0). Saved source files and `source-hashes.json` record exact bytes and hashes. Upstream compose confirms DB_SERVER=db and the two official image repositories. Upstream Dockerfile uses PHP Apache, installs mysqli/PDO, copies config, and installs API Composer dependencies. No VulnHub OVA or nested virtualization is needed.

**Provenance limit:** neither selected image advertises an immutable source revision in its config labels. The DVWA GitHub source commit above is independently observed current source, not proof of the image's exact build commit. MariaDB labels identify version 10.11.19. Do not claim a source-build attestation.

DVWA config: default root user (User unset); entrypoint `docker-php-entrypoint`; command `apache2-foreground`; no declared volumes; exposed 80/tcp. MariaDB config: default root user (User unset); entrypoint `docker-entrypoint.sh`; command `mariadbd`; inherited volume `/var/lib/mysql`; exposed 3306/tcp. Exposure metadata alone does not publish ports. Installer explicitly overrides users to www-data/mysql, covers the inherited DB volume with bounded tmpfs, and adds no capabilities.

## Guest deployment contract

`install.py` defaults to **plan only**, with a fixed private Docker socket:

`unix:///home/vindleradmin/artex-standalone-phase-a-standing/docker.sock`

- New exact names: `dvwa-target-20261119-web`, `dvwa-target-20261119-db`, `dvwa-target-20261119-backend`; owner label `lab.owner=dvwa-target-20261119`.
- Backend internal bridge candidate `172.29.89.0/24`; preflight rejects overlap with every existing Docker network. Existing names cause a block, never reuse or removal.
- Existing `artex-native-owned-internal` must be an internal bridge; **only web** attaches there with alias `dvwa-target`. DB is backend-only with alias `db`. No published/listening host ports, host networking/PID, privileged mode, bind/socket mounts, or restart policy. No internet target endpoint or new proxy is created.
- Both containers: read-only root, all capabilities dropped, no-new-privileges, 0.75 CPU, 160 PIDs, 16 MiB shm, bounded local logs. Web 384 MiB RAM; DB 768 MiB RAM; swap ceiling equals RAM.
- All writable mounts bounded tmpfs with nosuid/nodev/noexec. DB data 512 MiB, runtime 8 MiB, temporary 32 MiB. Web temporary/session/runtime/log/upload mounts bounded separately. DB root defaults from upstream are overridden with a dedicated lab-only root string; all displayed DB/password values are disposable lab defaults, not operator credentials.
- **Storage choice:** DB and uploads are deliberately ephemeral tmpfs; stopping loses those data. No persistent app volume is created, deleted, reused, or modified. Existing persisted ARTEX/app data remain untouched. Stopped containers and backend network remain for evidence; no prune/rm operations exist.
- Immutable images must already be acquired by parent. `--pull=never` always; missing image, identity/platform mismatch, unexpected inherited volumes, or unsafe inspect results block. **No pull, build, package install, elevated-user, capability, or writable-root fallback.**
- Explicit `--use-config-ids` supports offline Docker tar imports which lack RepoDigests. It uses the exact registry-config SHA-256 image IDs from `pins.json` and verifies them before launch. Parent must independently verify manifest/layer/archive provenance before import. This mode never accepts a mutable tag or silently falls back from manifest pinning.

### Parent commands (not executed here)

Copy this directory to the approved guest and retain `pins.json` unchanged. Parent must prestage both approved images in this private daemon, verify host disk/memory headroom and the existing private ARTEX UI path, and supply its existing absolute authorization deadline. This does not grant a fresh 30-minute window.

```sh
python3 install.py --action plan
python3 install.py --action install --deadline-epoch "$APPROVED_DEADLINE_EPOCH"
# Only if parent imported verified archives without RepoDigests:
python3 install.py --action install --use-config-ids --deadline-epoch "$APPROVED_DEADLINE_EPOCH"
# Exact owned containers only; never removes persisted data/resources:
python3 install.py --action stop
```

Deadline must have 180..1800 seconds remaining. Installer is a **foreground guard**, not a new guest service: keep its process alive until it stops the exact owned containers, verifies stopped state, and exits. Docker call timeouts reserve 60 seconds for shutdown. Setup errors, normal deadline completion, Ctrl-C, SIGTERM and SIGHUP use the stop path; stop attempts both owned containers even if the first fails. Like any in-process guard, SIGKILL/host failure cannot run cleanup. Parent must retain its independently supervised cloud/task deadline and issue/read back exact stop on abnormal process loss. No detached watchdog was installed.

## Real health/setup gates encoded, NOT executed

1. Actual MariaDB SELECT 1 readiness and actual HTTP GET `/setup.php`, using PHP HTTP client inside web (no helper image, no public port).
2. Obtain PHPSESSID from Set-Cookie; extract actual form user_token; POST create_db with same cookie/token **once**, only on the newly created isolated DB. Source confirms this operation resets DVWA DB; it is never run against existing resources.
3. Require actual HTTP `Setup successful`; query real seeded SQL counts (users=5, matching admin=1, guestbook=1).
4. GET login form, use fresh CSRF token and same cookies, POST disposable DVWA `admin/password`, and require authenticated HTTP homepage including Logout.
5. Container inspect rejects host exposure, unexpected mounts/networks, image mismatch, capabilities/restart/readonly/resource violations.

Intentionally no synthetic success receipt or runtime claim. Hardened non-root Apache/MariaDB startup and exact HTTP compatibility need parent guest execution. If startup fails, inspect exact owned logs and report block; do not relax confinement automatically. Read-only config means setup's optional `config.inc.php.bak` copy may fail silently; that directory-listing artifact is not qualified. External reCAPTCHA/callback/egress-dependent lab exercises are intentionally unavailable.

## Local verification actually executed

From `/home/iveri`:

```sh
python3 coordination-20261119/dvwa-target/acquire_metadata.py
python3 -m unittest discover -s coordination-20261119/dvwa-target -p 'test_*.py' -v
python3 coordination-20261119/dvwa-target/install.py --action plan
python3 coordination-20261119/dvwa-target/install.py --action plan --use-config-ids
python3 -m py_compile coordination-20261119/dvwa-target/acquire_metadata.py coordination-20261119/dvwa-target/install.py coordination-20261119/dvwa-target/test_install.py
```

Results: metadata resolution exit 0, **11 offline tests passed**, both plan modes exit 0, compilation exit 0. `tests-output.txt` retains the final 11-test run. `launch-plan.json` retains manifest-pinned argv. Tests cover immutable image/config IDs and metadata totals, fixed daemon/no shell, bounded tmpfs/resource/identity controls, unsafe argv mutations (privileged/host modes/ports/binds/socket/caps/restart/pull), deadline block, CSRF absence, real-client cookie parsing/status rejection, unsafe inspect rejection, and exact-owner stop/no-removal behavior. Mocked tests establish argument/control logic only, not runtime isolation or successful health setup.

## Files / handoff lessons

Artifacts: `REPORT.md`, `pins.json`, `install.py`, `test_install.py`, `acquire_metadata.py`, `tests-output.txt`, `launch-plan.json`, `source-hashes.json`, five `source-*` upstream snapshots, Python compile caches. All are under this new task directory.

Reusable lessons for parent only (no global skill edits authorized): resolve multiarch tags to platform manifest plus config digest before transport; distinguish compressed transfer from unpacked storage; imported Docker archives may lose RepoDigests, so use explicit verified config-ID mode rather than mutable tags; mask inherited image volumes with bounded owned storage; separate mocked argv tests from real HTTP/session/CSRF/SQL proof; keep a parent deadline independent of an in-process cleanup guard.
