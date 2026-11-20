# ARTEX → Qwen integration: BLOCKED at admission/executor coupling

## Decision
No safe config-only or external-adapter route exists in the inspected frozen production build. Do **not** activate an ordinary OpenAI Qwen profile for the owned-fixture execution test: that selects the legacy worker tooling, not the reviewed native executor. Do **not** label Qwen requests as `gpt-6.1-sol`/`codex-native` to fit the native bridge. That would conceal the selected model and violate the admitted contract. No adapter was implemented because doing so requires changing the reviewed application/admission boundary, expressly out of scope.

This is a source-and-artifact inspection result, not live model qualification, UI qualification, or tool-roundtrip evidence. No inference, transport, processes/descendants, listeners, cloud operations, credentials, or approval records were used or created. The parent retains launch approval and final verification.

## Exact blocking seam (paths relative to artex-worker-admission/source)

1. `agent/provider.go:217–250,280–310` supports ordinary `openai` custom base URLs. It constructs a Norma OpenAI provider, not an admitted native provider. A base of `https://iverson-pc-1.tail8ccbd1.ts.net/v1` would target Chat Completions through that normal path; compatibility with the running Qwen server was not contacted/tested.
2. `server/task_llm.go:296–313` returns the ordinary task runtime for non-native selections. `agent/native_task_role.go:132–135` then returns no native scope unless the provider is the opaque private `*nativeRPC`.
3. `agent/worker.go:377–405` consequently selects `defaultToolsExcept(...)` for ordinary OpenAI, including SDK Bash/Read/Write/Edit/LS/Sleep rather than the native-role base. Merely calling `SetNativeExecutorFactory` does not change this branch: the loader is reached only inside the native-worker branch (`native_task_role.go:139–156`).
4. `agent/native_executor_config.go:16–30` requires an admitted `*nativeRPC`, live private phase and worker role before loading `executor.json` and the executor key. There is no public config hook to attach that executor to a normal OpenAI provider.
5. `agent/native_admission.go:49–50,90–115` rejects any model other than `gpt-6.1-sol`, any API key/proxy, streaming, output-token cap and unsupported settings **before** private key acquisition. The policy independently requires that exact model and protocol.
6. `agent/native_rpc.go:50–64,170` repeats the exact-model gate and hardcodes `gpt-6.1-sol`, `artex-native-v1`, `codex-native` onto the wire. `agent/native_preflight.go:15` and `server/task_llm.go:287–293` also fix the native identity. A transport-only substitution cannot honestly advertise Qwen to this artifact.

The reviewed host API does exist: `nativeexec.Executor.Execute(context.Context, Request) (tool.Result,error)` (`nativeexec/adapter.go:18–32`). `Request` carries trusted phase/generation/task/exploration/intent/role/session/executor/network-policy binding, tool name, raw input and tool-use ID. `Wrap.Call` validates post-hook input and trusted binding before calling the executor (`:51–75`); `NativeWorkerExecutor` loads a private Unix-socket client only after phase/config checks. This is **not** an unrestricted host Bash API. The six SDK tools can run in the separately admitted isolated helper; `nativeexec/adapter.go:91–94` explicitly says this is not a command allowlist. The necessary isolated broker/network-policy qualification is still a separate parent gate. Exposing this client to a new replacement loop would not establish the application's normal task/planner/worker/report path.

## Actual normal UI/auth interface (documentation, NOT a launch recipe)

- Real page: `/system/llm`; source `web/src/app/(main)/system/llm/page.tsx:421–455`. Save is separate from activation. `web/src/lib/api.ts:959–982` uses the real `/api/llm/profiles` endpoints.
- Auth status: `GET /api/auth/status` → `{initialized:boolean}`. Login: `POST /api/auth/login`, JSON `{username:"ARTEX",password:<private user entry>}` → `{token:<JWT>}` (`server/auth.go:261–298`). Protected API calls require a valid token; UI stores it under `artex_token`. No password/token was retrieved.
- `POST /api/llm/profiles` accepts a `db.LLMProfile` plus sibling `api_key` and optional `streaming` (`server/server_mgmt.go:1790–1835`). Relevant actual names: `name`, `format:"openai"`, `base_url`, `model`, `proxy`, `api_key`, `context_window_k`, `thinking_type`, `reasoning_effort`, `streaming`, `max_tokens`, `max_tokens_field`, `session_header_key`, rates, priority, pool exclusion and retry controls. Omitted streaming defaults **true**. `POST /api/llm/profiles/active` uses `{id:<number>}` and hot-applies it (`:1920–1938`). GET profile responses hide API-key bytes, but profile persistence is not the proposed in-memory credential bridge.
- These fields describe normal ARTEX support only. They do not grant confinement or fixed-Qwen admission. Do not enter the private Qwen key into the UI/profile DB as a workaround for the missing bridge. An LLM test button proves neither the executor path nor the real task lifecycle.

## Required integration change before a Qwen launch

A separately authorized and reviewed source change must decouple inference identity from trusted task/executor authority, while preserving the actual ARTEX planner/worker/Norma loop, phase membership checks, exact role catalogs, budgets, serialization, no-replay/fallback behavior, broker binding and reporting. Alternatively add an explicitly named Qwen private provider through **all** native admission/preflight/catalog seams; do not alias it to Codex. This is not a supported patch/config in the frozen artifact.

For the smallest future interface, choose a **fixed-purpose Qwen inference route**, not a general target gateway: trusted code fixes HTTPS origin `https://iverson-pc-1.tail8ccbd1.ts.net`, path `/v1/chat/completions`, selected Qwen model identity (delegation describes qwen3.5-9b / 65536 context; server model ID was not queried), method and credential header. Model request bodies cannot select URLs, hosts, proxies, headers, credentials or redirects. A caller-supplied header/URL selector is forbidden. Credentials belong only in the trusted model transport, supplied privately in memory after nonsecret destination/model/capability checks, never in worker tools or transcripts. Enforce absolute deadline/call/body/output limits and deny fallback to other providers. Do not confuse the inference endpoint with the owned-fixture origin: fixture effects remain exclusively behind the existing admitted executor and fixed fixture/network-policy binding. If a target gateway is later chosen instead, its administrator-owned origin/method/path policy needs separate review; it is not implied by the inference allowlist.

Before any new artifact qualifies: actual application-provider injected-transport tests must show tool schema → assistant tool call → reviewed wrapped executor → real tool result returned to the next provider request, alongside deny cases and all existing admission checks. Scripted transport is component evidence only, not live Qwen or isolation evidence. No such runnable application path exists unchanged here, so no substitute Python/Hermes loop or synthetic success artifact was manufactured.

## Frozen artifact selection and verification

Use `artex-ui-asset-final/bin/artex.gz` only as the **existing non-English-qualified** frozen production artifact reference; it is not Qwen launch-ready. Fresh offline gzip/ELF hashing matches the recorded build receipt:

- gzip SHA-256: `8cf8506d32b48d015a9ed85a4306a909b9c0b9339901bd984b6908db2fa26be3`
- decompressed ELF SHA-256: `77aa59f362abe0c286bdd3cbd90c05e334c5c0d1779936b17aa42221fb317835`
- inspected 13 routing/admission/executor/auth source files: all byte-identical to `artex-ui-asset-final/build-source` (see `inspection.json`). Nine static/byte assertions returned true; these are not runtime tests.
- Build receipt records frozen tree `c3de72f42c8b9e4246e98d84f452254cf812cc0a66bec1748a0665ac28e47f95`, 669 source files and 370 UI assets. This inspection did not revalidate that entire source-tree/catalog manifest.

English source work is not qualified by this binary or the old native catalog digests. Treat the English build/catalog as **not ready for this attempt** until rebuilt, re-pinned and re-reviewed. Do not claim the old ELF is English-qualified.

## Commands / operational disposition

**There is no safe launch command or profile JSON that enables Qwen plus the reviewed executor in this exact artifact.** Stop the Qwen execution lane before credential provisioning or model calls. Parent may independently continue already-approved non-execution UI/isolation gates, but those cannot be reported as the requested Qwen assessment. No config/admission flags were minted, and no peer files were modified.

Files produced here: `REPORT.md`, `report.json`, `inspection.json`. No runnable adapter, because its required integration seam is unsupported in frozen source.
