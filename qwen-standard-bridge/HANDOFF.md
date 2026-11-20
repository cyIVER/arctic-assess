# Qwen standard-path bridge handoff

LOCAL OFFLINE COMPONENT QUALIFICATION ONLY. No sockets/listeners/cloud/key reads/inference/API writes performed. Parent must independently review before launching. This does not qualify native executor gates or application containment.

## Artifacts and launch contract

- `bridge.py`: stdlib only; explicit `--serve-loopback --task-key-file PRIVATE_FILE --deadline-utc ABSOLUTE_UTC_Z` launches only 127.0.0.1:18760. Parent supplies vendor credential through private stdin pipe, one ASCII line, not argv/env/file/log. Task credential is distinct, >=24 printable ASCII bytes, in owner-private regular no-follow file mode 0600; generate freshly in parent. Never use a production/vendor credential as task credential.
- `guest_gateway.py`: explicit `--serve-fixed-guest --task-key-file PRIVATE_FILE --deadline-utc SAME_ABSOLUTE_UTC_Z`; binds only 172.29.88.1:18761 and forwards only POST /v1/chat/completions to 127.0.0.1:18760 over parent's task-owned reverse tunnel. Receives ONLY task credential, never vendor key. Keep key away from DVWA. Existing native gateways/configuration remain untouched.
- No command here has been executed with serve flags. No daemon installation or host configuration changes.

Qwen upstream fixed in code to verified HTTPS iverson-pc-1.tail8ccbd1.ts.net:443 /v1/chat/completions and model qwen3.5-9b. No environment proxies, URL/header/model routing selector, redirects, fallback or retry. Caller headers are not forwarded; gateway and bridge construct fixed headers. GET models/readiness not implemented. Streaming false; max_tokens or max_completion_tokens <=4096, default max_tokens=4096, both together denied. Tools/messages/tool_call_id preserved. Tool-schema URL fields are data, not transport routing. Context size 65536 must be configured/verified on actual Qwen serving runtime and ARTEX profile; bridge does not pretend to tokenize input.

Each process: <=16 admitted logical upstream calls, request and successful entity response <=2MiB, aggregate response accounting <=8MiB. Conservative admission requires room for a full 2MiB response; failed transport consumes 2MiB accounting, never refunds a call. One inflight operation. Absolute UTC deadline must be within 30 minutes at startup; monotonic budget and UTC expiry checked. 60s request deadline includes incoming headers/body and upstream reads. DeadlineReader checks around every underlying recv; daemon operation provides caller-side deadline during blocking DNS, terminally fences the process on timeout. A stalled system DNS call can remain in that daemon until resolution/process exit: parent should terminate owned process at deadline. Budgets are process-local, not restart durable: parent must launch once, no auto-restart or second session. Credentials in memory only on bridge; secret echo rejection covers literal/JSON-escaped exact credential strings, not arbitrary encodings. Metrics contain status/count/bytes/timing only.

## Tests

`python -m unittest -v test_bridge` -> 16 passed. `python -m py_compile bridge.py guest_gateway.py test_bridge.py` -> passed. Socket creation monkeypatched to fail for every fixture. Actual HTTP handler is exercised with fake IO. HTTPSConnection and guest HTTPConnection replaced with in-process fakes to verify fixed routing/TLS context and one-request redirect denial. Structured assistant tool call followed by a real task-owned temporary-file read returned in second request is protocol fixture evidence, NOT live ARTEX tool execution. Covers wrong model/path/auth, budgets, expiry, malformed UTF-8/duplicate JSON, secret echo, slow reads, redirects/errors, tool-schema compatibility.

## Frozen source findings for parent (read-only)

Inspected `/home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/artex-english/source` (parent must confirm this is deployed frozen source).

- `server/dto.go:588-619`: profile JSON uses `format`, `base_url`, `proxy`, `model`, `context_window_k`, `streaming` (NOT `stream`), `max_tokens`, `max_tokens_field`, `pool_exclude`, nested `retry`.
- IMPORTANT: profile retry attempts `0` means INHERIT, not disabled; `-1` disables the layer. `db/config.go:74-78` lists `retry.connect`, `retry.empty`, `retry.stream`. Parent must verify RetryRule fields and global retry ladder before provisioning; do not set zero and claim no retry.
- `db/config.go:135-143`: failover pool includes active profile OR any other nonexcluded keyed profile. Setting pool_exclude only on this Qwen profile does NOT disable other fallback targets. Parent must verify exact task chain and global ladder; transport itself never falls back.
- `server/server.go:675-676,1448-1463`: POST /api/tasks accepts high-level description/goal, task profile binding, timeout_seconds, intercept_rules; seed_first_intent defaults false, maintaining ordinary planning path. This provides an interface for external Codex/JARVIS to submit bounded high-level DVWA-only work without embedding tool commands/catalogs or giving it arbitrary worker tools. No live authenticated API/UI exercise or authentication-boundary qualification was performed here. Prompt/intercept rules are not a substitute for external network/container authority.

## Dual-model boundary

Codex OAuth is exclusively parent planner/orchestrator/developer, outside target runtime. Bridge is Qwen-only. No Codex credentials or mixed-role in-app routing. ARTEX retains its standard internal planning/worker/reporter orchestration with the selected Qwen profile. External planner can supply a high-level goal via reviewed task API/UI; parent must review bounds and perform authenticated submission/readback, verify Qwen-only role bindings, no fallback, DVWA-only network confinement and actual findings/tool execution. No arbitrary worker-tool authority is granted by this bridge, and bridge authentication is not target authorization.

Reusable lessons for parent only: verify zero-vs-disable retry semantics in frozen schema; preserve tool-schema URL fields as data while fixing HTTP transport routing; terminally fence after timeout instead of admitting a replacement; keep component protocol tests distinct from live ordinary ARTEX qualification.
