# Changelog

Notable changes to this project are recorded in this file, following the format of [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/).

## [Unreleased]

### Deployment and release maintenance (application version remains 0.3.15)

- Migrated to the independent `RuoJi6/ARTEX` repository, preserving the original commit history and branches.
- The page's online update source is `RuoJi6/ARTEX`; GitHub Actions builds application packages for five platforms and SHA256 checksum files.
- Build Docker Hub images on native AMD64 and ARM64 runners, and verify application startup, database connectivity, and the embedded frontend.
- After verification passes on both architectures, publish the `v0.3.15` and `latest` images and corresponding application packages.
- Compose and deployment instructions use this repository's images and now include migration instructions that preserve data in existing deployments.

## [0.3.15] - 2026-10-07

### Interception

#### Added

- **Added a built-in interception rule for deletion endpoint paths**: Previously, the built-in destructive HTTP rule recognized only the DELETE **method**, but many applications allow deletion through GET/POST: calls such as `curl 'http://t/api/user/delete?id=1'` can delete real target data. An additional `deny` rule now covers `/delete /del /remove /unlink /erase /destroy` (the verb must be followed by a separator, so `/delivery`, `/details`, and `/delta` are not falsely blocked). Existing instances receive it on upgrade; it can be disabled or deleted under System → Command Interception.
- **Model fallback approval now has separate token usage statistics**: Approval calls previously had no independent accounting, leaving their cost unclear. They are now metered separately. A usage card below the Model Fallback Approval switch under System → Command Interception shows cumulative calls, input, output, cache reads and cache writes, plus a miniature daily usage chart for the last 30 days.

### Vulnerability Notifications

#### Added

- **Push vulnerability discoveries to IM**: The new System → Notifications page can send scan discoveries through six channel types: **DingTalk, Feishu, WeCom, generic Webhook, Telegram, and email**. Each type supports any number of instances, with independent enablement, rate limits and filters.
- **Real-time and digest delivery modes**: Real-time mode sends each matching discovery immediately; digest mode combines discoveries into one message at a global interval (30 minutes by default), with new-discovery counts and severity distribution at the top. Configure two channels for high-severity real-time alerts and digests for everything else.
- **Four filtering dimensions**: Minimum severity, task/asset scope, vulnerability-type keyword inclusion and exclusion (exclusion takes precedence), and whether to receive disposition-status changes (off by default). Messages include a View Details button whose destination uses the global backlink address; leaving it empty omits the button.
- **Delivery history and manual resend**: Lists each delivery's status, attempt count, failure reason and channel, with channel/status filters. Failed entries can be resent with one click, resetting their retry count.
- **Masked channel credentials**: Webhook URLs, signing secrets, Bot Tokens and SMTP passwords are returned only as masks with a trailing-character hint. Returning the mask unchanged means no change; clearing the input deletes the field.

#### Fixed

> This section records a security audit after the initial implementation. Each issue was reproduced, fixed, and covered by a regression test.

- **Fixed bypassing masks by changing destinations while retaining credentials (critical)**: Configuration merging preserved database values for all omitted keys. Changing only the destination while omitting credentials could therefore silently send stored credentials to an arbitrary address. A destination change now requires an explicit choice for every credential field: provide a new value or explicitly leave it empty if no longer needed.
- **Fixed missing escaping of untrusted content in Markdown-based channels**: Vulnerability titles and summaries come from model output, and asset URLs from scan results. Crafted titles could render clickable external links in DingTalk, WeCom or Feishu, while image syntax could trigger client requests and reveal readers' IP addresses. Content is now flattened to one line and Markdown metacharacters escaped at each channel's rendering boundary, rather than in the shared title function.
- **Fixed SSRF exposure through delivery destinations**: Loopback, private-network and cloud metadata addresses were previously all reachable; the first 200 bytes of failure response bodies entered `last_error` and appeared in delivery history, creating a semi-blind read primitive. Protection now operates at the **dial stage**, covers DNS rebinding, and rejects cross-host redirects. Loopback and link-local destinations require explicit `ARTEX_NOTIFY_ALLOW_LOCAL=1`; RFC1918 private networks remain allowed because private SMTP relays are common.
- **Fixed notification credentials leaking through errors**: DingTalk's `access_token`, WeCom's `key` and Telegram's bot token appear in URLs. On delivery failure, complete URLs reached `last_error`, delivery history, server logs and frontend notices. Errors are now redacted consistently, retaining only `scheme://host` and the underlying cause.
- **Fixed silent loss when truncated digests marked the entire batch delivered**: Omitted vulnerabilities appeared neither in the message nor in the failure list, while history reported success. Digests now pack **whole entries**, mark only included entries delivered, and requeue the rest for the next message without consuming retries. The header also states how many entries remain.
- **Fixed misspelled minimum severity silently disabling filters**: A typo such as `hgih` in `min_severity` assigned the unknown level ordinal 0, making the predicate always true. Users expecting only high-severity alerts instead received every vulnerability. The write path now validates the value and lists valid choices.
- **Fixed unreachable `rate_per_min = 0` (unlimited)**: The database write layer silently replaced explicit 0 with the default, leaving rate limiting active when operators expected it disabled. Defaults now apply at the API layer only when the field is absent.
- **Fixed digest channels bypassing the token bucket entirely**: `rate_per_min` previously had no effect in digest mode. The number of claimed entries is now bounded by both the current allowance and an in-memory limit.
- **Fixed batch-wide failure decisions using the largest attempt count**: An old delivery with two retries could force brand-new deliveries in the same batch into failed status, permanently losing new alerts before they received any retry. Decisions are now per delivery.
- **Fixed unparseable snapshots in digest batches being silently marked successful**: Rendering skipped these entries but the whole batch was still counted successful. They now fail explicitly with a reason.
- **Fixed per-channel delivery batches potentially outlasting their leases**: In multi-instance deployments, expired rows could be reclaimed, sent twice and have attempts incremented twice. The per-round limit is now derived from lease duration divided by single-delivery timeout, with assertions pinning the relationships among these constants.
- **Fixed Telegram truncation splitting HTML entities**: Truncation avoided partial tags but not entity fragments such as `&amp`, which could cause the parser to reject the **entire** message. It now avoids both.
- **Fixed email channels treating temporary SMTP failures as permanent**: 4xx replies such as greylisting `450` are temporary refusals and should be retried, but were previously terminal, causing every alert on greylisting servers to fail on its first attempt. The first response-code digit now distinguishes retryable 4xx from permanent 5xx failures.
- **Fixed nested submissions storing mask literals in the database**: Object fields such as `webhook.headers` must be masked or submitted as a whole. A mask sentinel nested inside an object was stored as a real value, silently breaking authentication. Such submissions are now explicitly rejected.

#### Design Notes

- **Vulnerability writes perform only one blind INSERT in the transaction**: `notification_events` and vulnerabilities are written in the same transaction, ensuring atomic consistency on commit. This INSERT deliberately does not read channel tables or run user filters, and is wrapped in `SAVEPOINT`; otherwise a misconfigured filter could abort the transaction and prevent a high-severity vulnerability from being stored.
- **Deliveries use leased claims rather than long transactions**: After claiming with `FOR UPDATE SKIP LOCKED`, rows become `sending` and `next_attempt_at` moves into the future as a lease. No database locks are held during delivery. Rows left by a crashed process are reclaimed after lease expiry, recovering automatically without unlimited retries.
- **Rate limiting does not consume retry budgets**: Compute the current allowance from the token bucket before claiming that many entries. Reversing the order would count rate-limited deliveries as attempted, exhausting the three-attempt budget through waiting alone.

### Test Infrastructure

#### Fixed

- **Fixed permanent test-asset leaks caused by cleanup order in company ICP ownership tests**: `defer d.Close()` ran on function return before `t.Cleanup`, so cleanup statements used a closed connection and discarded their errors. Test companies and assets remained permanently and could break unrelated asset-count assertions. Connection closing now also uses `t.Cleanup`, registered first, and cleanup errors are surfaced.

### Traffic

#### Added

- **Traffic lists now support content search, path/status/length filters and column sorting**: Filter by **response content** (full-text index), **path**, **status code** (exact or buckets such as `2xx`), and **response-length range**. Headers sort by time, status or response length, with preferences stored locally. Two new indexes apply automatically on upgrade; the Agent tool query contract is unchanged.
- **Added Clear All to traffic lists**: Deletes all traffic records regardless of filters and removes historical host directories no longer tracked by the index. It then runs full compaction and reports the actual space released. Traffic evidence attached to vulnerabilities is stored separately and is unaffected.

#### Fixed

- **Fixed deleting traffic not releasing disk space**: Index databases were created without `auto_vacuum`, so files never shrank. The full-text index used `contentless_delete`, where `DELETE` wrote tombstones without reclaiming original postings; deletion actually enlarged indexes (a measured 6MB body produced a 16MB index that remained 16MB after deletion). New index databases enable `auto_vacuum=incremental`, and each deletion schedules chunked full-text merging and incremental reclamation in the background, gradually returning space to the system (104KB in the same scenario). Write locks are released between chunks to avoid blocking recording.

> Upgrade note: `auto_vacuum` can only be set when creating a database, so **existing instances retain the old index mode**. Incremental reclamation is a no-op there, with a startup log notice. Upgrading stops tombstone growth; use Clear All once to reclaim existing space and convert the database to incremental mode. Subsequent routine deletions then reclaim space automatically.

### LLM

#### Fixed

- **Fixed custom session headers not applying to one-shot LLM calls**: Goal decomposition (round 0) and cold-node compaction are one-shot calls without a transcript store or session ID in context, so gateways could not read the header. Endpoints such as opencode zen that return 400 without it failed in round 0 while later planner rounds worked normally. Both paths now explicitly attach an exploration-stable session ID, also attributing token usage to the correct exploration instead of losing it entirely.

### Tools

#### Fixed

- **Fixed MCP and custom-tool truncation failing and flooding context with large results**: MCP outputs previously bypassed truncation, while HTTP custom tools received an empty tool context and used a hard-coded 6000-character cap rather than the session setting. Both now use `actool.Capture`, truncating to session `MaxOutputChars` (30000 by default). With `ToolOutputDir` configured, full output spills to disk and messages retain only a leading excerpt and file pointer.
- **Upgraded norma to v0.4.3**: The harness applies `CaptureOnce` centrally, preventing any tool, including future additions, from overflowing context because truncation was not wired in.

### Deployment

#### Fixed

- **Fixed activity streams failing behind reverse proxies**: SSE addresses previously always used `${hostname}:8787`. Pages loaded from `https://域名/` behind a proxy on 443 therefore targeted port 8787, which was not publicly exposed, causing repeated reconnections. Behavior now depends on `NODE_ENV`: production defaults to same-origin, while only `next dev` retains `:8787` to bypass Next.js SSE buffering. The `NEXT_PUBLIC_SSE_BASE` override remains available. README now documents reverse-proxy deployment.

### Findings

#### Fixed

- **Fixed missing scrolling when the By Asset discovery list overflowed**: The outer card had only `max-height`, not a definite height, so the scroll viewport could not resolve its percentage height. Large lists overflowed or were clipped without scrolling. The height limit now applies directly to the asset tree's native scroll container and adapts to the window height.

### Database

#### Fixed

- **Capped the connection pool**: `database/sql` defaults to unlimited application connections and opens another whenever none are idle, eventually reaching PostgreSQL's `max_connections` (100 by default) and receiving rejections. The pool is now capped at 32; excess queries wait for an idle connection, making the same load slower rather than erroneous. Lower this cap as well if `max_connections` has been reduced.
- **Improved connection reuse**: `MaxIdleConns` defaults to 2, so connections beyond two concurrent requests were closed after use, requiring fresh TCP and PostgreSQL authentication handshakes next time. The idle cap now matches the total cap, with a 30-minute connection lifetime and 5-minute idle expiry to replace long-lived bad connections naturally.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)

## [0.3.14] - 2026-09-24

### Task List

#### Added

- **Added a Vulnerabilities column to task lists**: Shows critical/high/medium/low counts, coloring nonzero buckets by severity so each task's vulnerability volume and distribution are visible at a glance.

#### Changed

- **Narrowed the Description / Goals columns**: Long text is ellipsized with full text on hover, reducing horizontal space consumed by lengthy content.

### Exploration Graph and Planning Overview

#### Changed

- **Simplified the planning overview (graph_overview) and capped its lists**: Recent facts, completed intents, pending intents, cold-area summaries and confirmed-vulnerability details now use a latest window plus total counts; omitted entries can be queried on demand. This substantially reduces per-round LLM context and long-task growth, including cold areas in related-task overviews.

#### Fixed

- **Removed reversed duplicate edges between digest and finding nodes after folding cold nodes in the exploration graph**.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)

## [0.3.13] - 2026-09-19

### Asset Interception

#### Added

- **Added global asset interception rules (blocklist)**: Supports exact and fuzzy domain/IP/URL matches and CIDR ranges, with CRUD and enable/disable controls under System → Asset Interception. Built-in fuzzy rules block government (`.gov` / `.gov.cn`) and education (`.edu` / `.edu.cn`) sites by default.
- **Integrated asset interception into execution**: Before dispatching intents (`add_intent`) or inserting assets (`insert_assets`), the Agent checks target assets. Matching intents are not dispatched and matching assets are not inserted; asset information and the rejection reason are returned to the Agent.
- **Added task-level block/allow (allowlist) rules**: Independent of global rules and limited to the current task. Evaluation blocks first, then allows: any block match rejects; otherwise, when enabled task allow rules exist but none match, testing is disallowed. Without allow rules, the allowlist is inactive. Rules can be entered when creating tasks or managed in task-detail Overview.
- **Task templates now include preset categories and task-level block/allow rules**: Saved categories and rules populate the new-task form when applying a template.

### Operation Review

#### Fixed

- **Tightened the model judge output protocol to reduce truncation-related false allowances**: Reduced the verdict comment limit from 500 to 120 Chinese characters and required JSON only, without preambles or code blocks. This avoids `MaxTokens` truncation causing parse failures followed by fail-open handling.

### Task Archiving

#### Fixed

- **Skip symbolic links during archiving instead of failing the entire archive**: The archive format supports only regular files and directories end to end. Previously any symlink in the work directory failed the whole task archive. Symlinks are now skipped and logged while other files are archived normally, without following links or escaping the directory tree.

### Accounts and Compliance

#### Added

- **Added a pre-login Usage Notice and Disclaimer dialog**: Agreement must be checked before login.

### License and Dependencies

#### Changed

- **Adopted the AGPL-3.0 open-source license**, and completed the README license and disclaimer documentation.
- **Upgraded norma to v0.4.1**.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)

## [0.3.12] - 2026-09-17

### Exploration Feed

#### Added

- **Added an Exploration Feed to task details** (#144): A chronological timeline of exploration nodes (origin/goal/intent/fact/finding/hint/digest), with type filters, keyword search, ascending/descending order, pagination and auto-refresh. The first page in newest-first order is the live position and refreshes each round; elsewhere, only unread counts accumulate without disturbing reading, with an N new updates · Back to latest shortcut. Entries are grouped by day for orientation when paging through long tasks.
- **Each feed row displays its node ID** (#145), making it easier to cross-reference the exploration graph and locate nodes.
- **Expanded feed details show upstream/downstream nodes and anchored assets** (#147): Expanding an entry reveals its relationships; hovering a related entry shows a node card with type, status, source, time, summary and payload excerpt. Anchored assets appear with type labels and recognizable text. Data accompanies the feed page, so expansion makes no additional requests.
- **Feed search now supports node IDs** (#150): Alongside content/source matching, entering digits or the displayed #41 form locates the corresponding node exactly.

### Intent Management

#### Added

- **Intent deletion supports soft and hard deletion** (#149): Pending, running and paused intents can be deleted with a required reason; choose the mode in the confirmation dialog.
  - **Soft deletion (default)**: Marks the intent deleted and stores the reason in a separate field, retaining the intent node and all its outputs and lineage.
  - **Hard deletion**: Physically removes the intent and exclusive descendants supported only by it, cascading along output/intent chains to leaves to avoid orphaned data. Token accounting is rolled up under original dates; shared nodes referenced by other intents, goals and task-root facts are retained. The confirmation dialog shows the expected cascade node count.

  Both modes notify the planner that the user deleted the intent, including the reason, so it can replan.

### Operation Review

#### Added

- **Approval records support status and decision-source filters** (#139), making target records easier to locate.

#### Fixed

- **Pending approvals load independently of history pagination** (#133): They remain fully visible while browsing historical records.

### Agent

#### Changed

- **Changed the Worker role description to general cybersecurity-platform wording** (#138).

#### Fixed

- **Fixed cold-node compaction never triggering**: Connected the task planner to the Compactor, restoring previously unwired cold-digest execution.

### Chat

#### Added

- **Chat supports @ references to multiple record types and scrolling pagination** (#135): Reference candidates load additional pages while scrolling.

#### Fixed

- **Constrained long message bubbles to the conversation panel** (#137), preventing overflow outside the conversation area.
- **Fixed uploads reporting Missing upload file before a new conversation existed**: Composer now snapshots `FileList` as an array before clearing the input and invoking the callback. Previously draft mode asynchronously created the conversation first; the live-bound `FileList` was empty when execution resumed, so the file field was missing and the backend returned 400.

### Traffic

#### Fixed

- **Traffic recording proxies now listen only on 127.0.0.1 by default** (#129, #130), avoiding exposure of an open proxy on other interfaces.

### Web

#### Fixed

- **Fixed the task-list page missing its global header in static exports**.
- **Completed associated-traffic mocks for demo vulnerability details, fixing a blank page**.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)
- [@RuoJi6](https://github.com/RuoJi6)
- [@dingpotian](https://github.com/dingpotian)

## [0.3.11] - 2026-09-15

### Operation Review

#### Added

- **Approval records now link to their originating execution** (#125): Clicking Source opens the original complete conversation, paginates to the exact tool execution, expands its command/results and centers a highlight while keeping surrounding messages readable. Manual scrolling stops automatic adjustment. Ordinary chat, task Worker, planner and segmented main-Agent conversations are located through persisted `tool_use_id` and task mappings, with a new scoped call-ID index. Missing, duplicate or ambiguous associations produce explicit notices instead of jumping to another execution. Deleted conversations, archived tasks and missing records also receive clear notices.
- **Approval records support pagination** (#115).

#### Changed

- **Simplified model-review input** (#124, #125): The LLM judge used when no rule matches now receives versioned JSON containing only the current complete tool call, explicitly selected brief background and the local work directory. Background uses only genuine current user messages from chat/task main Agent; Workers omit intent summaries and clear inherited parent background. Planner and automatic sessions do not invent user messages. Task descriptions, goals, operation constraints, global exploration state, historical calls and complete Worker intents no longer enter operation review, but remain available to Agent execution and independent session auditing. Verdicts require JSON `decision`/`comment`, explaining the actual operation, consequences of success and matched rule; instructions in arguments or background cannot change review policy. The actual model input snapshot and fingerprint are saved. Older snapshots remain versioned rather than being reconstructed from current data.

#### Fixed

- **Code-block-wrapped verdicts no longer silently allow execution** (#126): Previously, verdict JSON wrapped in ``` failed parsing and silently followed model-failure allowance. Code fences are now stripped before parsing; only a remaining parse failure uses the configured failure policy.

### Agent

#### Added

- **Added experimental noa context compaction** (norma upgraded to v0.4.0): Disabled by default and enabled in system settings. noa model-driven compaction replaces built-in compaction for main Agent, planner, Worker and chat. Original compacted text is archived centrally under `<workDir>/noa/<会话ID>/`, in globally unique session-ID directories rather than individual task directories. Integration failures fall back automatically without interrupting real tasks. The switch is read once per run and affects only subsequently started runs.

#### Fixed

- **Exploration-graph tools reject calls without task context instead of panicking on nil**: Such calls now return explicit errors rather than dereferencing an empty store.

### MCP

#### Added

- **Supported legacy SSE MCP services** (#117): Compatible with servers offering only the older SSE transport.

### Traffic

#### Fixed

- **Traffic searches match recorded hosts with port awareness** (#114): `traffic_search` includes ports in host matching to avoid mixing records from different ports on the same host.
- **A failed `traffic_search` description migration no longer stops later reporter migrations**: Individual migration failures are isolated.

### Web

#### Changed

- **Added separators between task vulnerability-retest options** (#122) for clearer visual grouping.

#### Fixed

- **Fixed demo task details crashing entirely**: In mock mode, the Conversations tab requested `GET /api/tasks/<id>/side-questions` (side-question history), but no mock handler existed. The read fallback treated paths ending in s as collections and returned `[]`; `data.items` became `undefined`, and the side-question hook's `merge()` threw `TypeError: t is not iterable`. Because this occurred in the `setItems` updater, React rethrew it during render, beyond the caller's `catch`, and the error boundary displayed This page couldn't load. The mock now returns explicit empty side-question history, and `sideAPI.history` normalizes non-array `items` to `[]` as defense in depth.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)
- [@RuoJi6](https://github.com/RuoJi6)

## [0.3.10] - 2026-09-13

### Network

#### Added

- **Added DeepSeek's official web-search source**: Reuses the active LLM configuration. Unlike the other three sources, DeepSeek has no directly callable search API; search exists only as the `web_search_20250305` server tool in its Anthropic-compatible API and runs on DeepSeek's server. It therefore **requires the official DeepSeek endpoint and anthropic protocol**; OpenAI-protocol endpoints reject server tools. Each search **consumes an additional model call**, **bypasses the search outbound proxy**, and **is not captured in traffic records**. Results contain **titles and links only**, without summaries; WebFetch retrieves full text when needed. Settings explain these limitations but **do not enforce validation**; users can verify with Test Search.

### Agent

#### Added

- **Workers can review traces across work items**: Added `search_all_worker_traces` to search matching steps across every work item in the task without first knowing intent_id, and `get_worker_trace` to list a selected work item's steps, search them or retrieve complete content by step_id. This reuses observations not recorded as facts and avoids duplicate work.
- **Made `node_detail` available to workers**: Together with the trace-review tools, workers can directly retrieve full details using intent_id/node ID.
- **Explicitly announce planning rounds triggered by `add_hint`**: Previously hints were merely included in the overview for planners to notice. Now each `add_hint` call records one trigger announcing N human-added strategic hints, even for batches, explicitly identifying the round's cause and showing the hint contents.

#### Changed

- **Relaxed the global situation prompt**: Encourages divergent exploration and timely reporting of cross-intent leads rather than premature convergence.
- **Simplified worker boundary wording**: An initial obstacle is not proof of exhaustive exploration; finish reasonable bypass methods within the intent before concluding.
- Removed each asset's `related` parameter from `insert_assets`: It only decided whether to include an asset in the task scope and was never persisted. Re-registering the asset discarded it, and the UI could not show which assets had been deemed unrelated, leaving the model to make an extra judgment that could not be retained.
- **Test scope (`task_scope`) no longer depends on the asset-coverage switch**: Automatic `insert_assets` scope writes (`source='auto'`) now always run, and `add_task_scope` is always available to planner, task main Agent and goal-decomposition Agent. Scope defines authorization and asset-query filtering; coverage controls only whether it is used as a metric denominator. Previously disabling coverage broke both `auto`/`agent` write paths, leaving only manual UI entries in `task_scope`. `list_untested_assets` remains hidden when coverage is disabled because it is purely a coverage view.

#### Fixed

- **Fixed assets leaking across tasks** (#59): `list_assets` hard-coded task ID 0 and queried the whole shared asset store, while models lacked a way to express scope filters. Assets from other tasks, especially IPs, were mistaken for current targets. Results now stay within `task_scope` for **this task and directly related tasks**, matching by **ownership**, not literal value: root domains include their subdomains/services/endpoints, and networks include contained hosts/services. Direct ID lookups also exclude out-of-scope assets. Non-task Auto/pentest contexts still fall back to the whole store. Also fixed the ownership gap where direct-IP hosts such as `http://1.2.3.4/api` failed network-scope matching. The UI Test Assets view, filtered by task producer, is unaffected.
- **Fixed worker cross-work review tools being unintentionally removed**: After adding `search_all_worker_traces` / `get_worker_trace` and `node_detail` to worker defaults, an older startup migration narrowing the tool surface unbound them again. They were removed from that list, with a one-time migration restoring bindings in previously migrated databases.
- **Fixed intermittent `/btw` side-question persistence failures**: Strip NUL (`\u0000`) escapes unsupported by JSONB before storing side_question checkpoints.

### Triggers

#### Fixed

- **Deduplicated task descriptions/goals in merged trigger sessions**: Multi-task merged triggers include each task's description/goals only once, preventing long goals from filling context repeatedly.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)

## [0.3.9] - 2026-09-11

### Agent

#### Added

- Task main Agents support **multiple conversations**, with creation, switching and independent context resets; every conversation is interactive.
- Added persistent `/btw` **side questions**: Follow up without interrupting the main thread; Q&A survives restarts.
- Added `source_task_ids` to `spawn_task`, allowing new tasks to **inherit read-only** assets and findings from source tasks.

#### Changed

- Disabled workers' cross-engagement memory and narrowed their default tools: Reading context and cross-work review are planning duties; workers execute and write back a single intent.
- Simplified default worker prompts; removed `terminated` and `worker_name` from `get_worker_output`; simplified `insert_assets` / `list_assets` descriptions.

#### Fixed

- Fixed work ending early after **idle turns**: Models sometimes spent an entire turn thinking, with neither body text nor tool calls. The harness saw a natural end (`end_turn` without `tool_use`) and returned `completed` with an empty summary, ending unfinished intents without any textual conclusion. None of the five LLM retry layers could intervene: this was not an error; same-provider safe-window retries require stream failure; circuit breakers treat `err == nil` as success; intent reruns require `model_error`; and SDK empty-response detection checks whether any event was yielded, including thinking deltas. The work Stop hook now detects these turns and injects a continuation instruction, preserving existing thinking for the next step. It deliberately avoids resending unchanged requests because these idle turns generally reflect stable prompt/context behavior, not random failures; resending would only repeat the thinking.
- Reused the LLM Retry and Backoff page's **empty-response retry count**: Both address completion without substantive output, using different detection and recovery methods. Default 2; `-1` disables continuation and restores the previous behavior. This is a **total per-intent** limit, not a consecutive-turn count: the harness allows only one push after consecutive idle turns and refreshes that allowance only after a real tool turn, so the setting bounds tool → idle → push → tool → idle loops that consume intent budgets. Triggers log `[work <worker> · #<意图>] 空转回合…注入续跑指令 (n/N)`. See `docs/LLM重试设计.md` §1.1.
- Fixed `/btw` context budgets and input layout in long conversations; use a fallback side-request ID generator in insecure non-HTTPS contexts.

### Traffic

#### Added

- Vulnerabilities support **multiple associated traffic-evidence records**, with ordering, notes and roles (request/response/corroboration).
- Report Agents **automatically associate** relevant traffic evidence before writing reports.
- Added an Agent **traffic-binding switch** and completed evidence handoffs between Agents.

### Tasks

#### Added

- Added **conversation-level vulnerability retesting**, running in an independent Agent conversation with status shown in lists and details.

### Interception

#### Added

- Approval records now include **details and execution audits**: View tool-request context, initial model/rule decisions, execution output and argument fingerprints.

### Assets

#### Added

- Task test assets support **DSL search**.

### LLM

#### Fixed

- Fixed connection tests omitting custom session headers and causing opencode zen to return 400.

### Network

#### Added

- MCP HTTP transport can **skip TLS certificate verification** for self-signed services.

### UI

#### Added

- Conversation lists group by Agent, with expand/collapse and independent pinning; conversations can be filtered by Agent.
- Attack-chain graphs render digest nodes and collapse their members.

#### Fixed

- Fixed blank pages caused by unsynchronized login credentials.
- Interception notices now explicitly identify platform controls, avoiding confusion with defenses on the target.

### Deployment and Updates

#### Added

- Added **one-click updates from the page**: A Version and Updates card appears in system settings, and the top bar signals new releases. The process downloads a release package → verifies `SHA256SUMS` → smoke-tests → stages → exits for the supervisor script to restart and replace the application; the page refreshes automatically.
- Added supervisor scripts `start.sh` / `start.bat` as official startup entry points, included in release packages and Docker images (`install.sh` unchanged). They choose whether to restart by exit code and forward SIGTERM to artex. Verification and replacement remain in Go, keeping scripts simple.
- Automatic fallback on failure: Failed verification or smoke tests discard the update and keep the current version. Three consecutive startup failures roll back to the previous version. Settings also offer manual rollback; database schemas are not rolled back.
- Updates require GitHub domains and HTTPS; the release source is not configurable. Development builds disable one-click updates. GitHub results are cached for 30 minutes to prevent top-bar checks exhausting API quotas.

#### Known Limitations

- Docker updates replace the application, not the image: Toolchains are not upgraded, and recreating a container restores its image's version. Use `docker compose pull artex` when needed.
- Release-package `skills/` are not synchronized, so newly added built-in skills do not take effect automatically.
- Updates restart the application and interrupt running tasks.

### Dependencies

#### Changed

- Upgraded norma to v0.3.7.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)
- [@RuoJi6](https://github.com/RuoJi6)

## [0.3.8] - 2026-09-09

### LLM

#### Added

- Added a Retry and Backoff tab to the LLM page, configuring **counts** and **intervals** for five retry layers. From inner to outer: SDK connection retries before streaming (resets/timeouts/429/5xx), SDK empty-response retries (normal completion without content, openai format only), same-provider safe-window retries (replay interrupted streams before any output reaches the caller), polling circuit breakers (cool down after consecutive failures), and intent reruns (rerun entire worker intents ending in model_error). Outer layers apply only after inner layers are exhausted. Each layer has two consistent controls: blank retains default counts/exponential backoff; a count overrides the count; an interval replaces exponential backoff with a fixed interval; -1 disables that retry layer. The first three are per-endpoint and can override global defaults field by field; specifying only an interval still inherits the global count. Circuit breakers and intent reruns are process-wide global settings. Saving applies immediately without restart. Leaving everything blank preserves current behavior byte for byte on upgraded databases (new columns default to 0 and absent settings keys mean defaults). Connection tests deliberately omit these settings because their hard 30s timeout would otherwise misclassify usable endpoints as failures. See `docs/LLM重试设计.md`.
- Each LLM configuration supports a custom **session header** (`session_header_key`): When nonempty, every LLM request includes this HTTP header with the current run's session ID, such as `conv-<id>` for chat and `exp<x>-worker-i<intent>` for workers. This supports gateways using session-ID headers for prompt caching or sticky routing. The ID comes from request context without modifying norma, allowing a shared provider to send different values per conversation. Includes migration for existing databases and an input in the frontend LLM configuration dialog.

#### Fixed

- Fixed saving LLM configurations failing with `23502` when the session header was empty: The column is `NOT NULL DEFAULT ''`, but `NULLIF($n,'')` incorrectly converted the empty value to NULL. It is now passed directly with empty-string semantics.

### Agent

#### Added

- Wall-clock timeouts now **wrap up in place**: With norma v0.3.6, `MaxDuration` interrupts the running tool at its deadline and continues on a live ctx for the configured wrap-up rounds, writing recognized results and a summary before ending as timeout. This replaces worker/planner external `maxDur+90s` hard contexts that killed stuck runs as `aborted_tools`. Chat receives the same behavior through the shared harness; mainagent has no `MaxDuration` and is unaffected.
- Stagnation fallback: When planner wakes on heartbeat/no-change and the graph has no open or running intents, its opening becomes a stagnation warning: no worker is running and no direction is queued, so this round must create one or more nonduplicate intents, not zero.

#### Changed

- Reworked worker prompts: Intent, launch instructions and raw anchored-asset JSON move into the system prompt, rebuilt each round and never removed by compaction; continuation no longer depends on retaining the first transcript message. The initial user message contains only the global overview, tolerating stale or unavailable data. Mixing per-intent data into system prompts loses cross-intent cache reuse, a deliberate tradeoff to retain intents.
- Simplified planner/worker default text and fixed operational issues: Planner treats `recent_done` by status, checking traces for blocked/exhausted intents before deciding, neither assuming dead ends nor blindly rerunning. Negative conclusions are observations or doubts rather than final verdicts, and require evidence before adoption. Unmet goals without open/running intents require new output; depth takes precedence over coverage. Workers write negative results as observations plus tentative interpretations, leaving decisions to the planner; cross-intent leads go into fact summaries rather than being pursued independently. Reseeding appends and selects a new default version, preserving custom/older versions for rollback.
- Narrowed work-agent default tools and asset-writeback prompts: Workers execute and write back one intent; context reading and cross-work review belong to planning. Removed `list_facts` / `node_detail` / `list_companies` and cross-work retrieval (`search_all_worker_traces` / `list_worker_traces` / `get_worker_trace`), retaining `list_findings` for duplicate checks plus `add_finding` / `record_fact` and `insert_assets` / `list_assets`. Removed stale field guidance (`type=tech`/`on_url`/`props`) conflicting with the `insert_assets` schema. A one-time migration removes these bindings from existing workers, leaving planner/main bindings unchanged.

### Exploration Graph

#### Added

- **Exploration-graph cold-node compaction (cold-digest)**: Older inactive intents/facts fold into digest nodes shown in `graph_overview`; original nodes remain permanently recoverable by ID. Storage is lossless, only presentation is compressed, and folding is reversible. Hot/cold classification uses reverse reachability and treats any active branch as hot, with R=6-round debounce and connected-component grouping. Background minor compaction folds uncovered cold areas; major compaction rereads originals and merges fragments. Activity rechecks, cooldowns and mutual exclusion keep it off the hot path and prevent overwriting revived nodes. Overviews expose `cold_digests` and asset-indexed `cold_index`; `expand_digest` / `expand_index` restore details. Related/inherited-task overviews reuse their own folded views, and `expand_digest` supports read-only cross-task expansion. `expand_digest` / `expand_index` are available to planner/main Agent, not workers. Includes migrations for existing databases.
- `graph_overview` outputs the complete `finding_list`: Findings are the highest-value task output and usually few, so overviews now include all of them rather than a recent window like facts. Planner/worker can see all confirmed vulnerabilities each round without `list_findings`. Entries use `{id, summary, evidence?, from_intent?, assets?}`, with readable affected assets (URL/domain/ip:port), not bare IDs.

#### Changed

- `graph_overview` no longer lists flat `hosts`: Coverage retains `host_count` but omits up to 500 host strings per round, which add little planning value; use `list_assets` on demand. Added top-level `done_intents_total` alongside the ≤15-entry `recent_done_intents`, letting planners know whether completed intents were truncated during duplicate checks.

### Tools

#### Changed

- Changed the default `add_company_scope` binding from worker to planner: Defining company scope belongs to planning/main control/Auto; workers execute exploration. New databases seed mainagent/planner/auto bindings; existing databases receive a one-time migration.
- Bound `list_assets` to planner by default: Planner now has both `list_assets` for whole-store DSL search and `list_untested_assets` for untested in-scope assets. One-time backfill preserves user unbindings.

### Tasks

#### Added

- Added Running Workers to task lists: Counts intent nodes with `state='running'`, using exactly the same definition as task-detail Overview. Displays 0 when no worker is running.

### Network

#### Added

- Added **global outbound proxy** configuration: All target traffic can use one global http/https/socks5 proxy, supporting `user:pass`. With capture enabled it is the MITM recording proxy's upstream: traffic is recorded before forwarding, both interception and passthrough use it, and the source IP is not exposed. Without capture it is injected directly into Agent bash environments and WebFetch (`proxyEnv` adds `ALL_PROXY` for socks5). Stored in settings KV without migration; the new Global Proxy card is independent of search and LLM proxies.

### UI

#### Fixed

- Corrected intent status-label semantics: `exhausted` now means Budget exhausted rather than Fully explored, because step/time limits can interrupt work after partial writeback. `blocked` now means Execution error rather than Intercepted, because model/API/network retries may fail before real exploration, not because a target/WAF blocked it. Added the missing `stopped` label for user-stopped work.

### Dependencies

#### Changed

- Upgraded norma to v0.3.4 for MCP output truncation and disk spill (see `651b961`); subsequent v0.3.6 supports in-place wall-clock wrap-up.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)

## [0.3.7] - 2026-08-31

### LLM

#### Added

- Added an output-token limit to model configurations and a selector for its request-field name. The limit caps tokens generated by one reply and is sent with every request; 0 (default) omits the field and uses server defaults. It differs from the context window, which is total model capacity used locally for compaction thresholds and is not sent. The field selector applies only to `openai` Chat Completions: blank uses `max_tokens`, accepted by most compatible gateways. Official OpenAI reasoning models (o series/GPT-5) instead require `max_completion_tokens` and reject `max_tokens` with `unsupported_parameter`, so users must select it manually. Other formats have fixed names (Anthropic `max_tokens`, Responses API `max_output_tokens`); their selector is disabled and cleared on save. Also wired a previously missing path: planner/worker/chat/main Agent/goal decomposition had never set output limits; openai omitted them and Anthropic used the SDK's 8192 fallback. Limits now resolve each round like streaming settings, applying on the next round after failover. Existing databases preserve behavior, with new columns defaulting to 0 and an empty field name.
- Clicking Test now logs each HTTP attempt's status code and raw gateway response body on the server, capped at 4K. This helps diagnose 401s, quota notices, empty frames and HTML responses rather than seeing only collapsed UI ok/err results. These logs do not depend on the LLM Recording switch.

#### Changed

- Task LLM configuration chains can now be edited in every state, not just running/paused/exhausted. Main Agent conversations still use the chain after done/failed/timeout, so broken models previously prevented both edits and further interaction. Removed terminal-state restrictions in HTTP and DB transactions; frontend editing/saving also opens for terminal tasks. Saving a terminal task no longer reopens quota-blocked intents, which otherwise became open without workers or rerun eligibility. Use rerun intents or add goals to resume the task.

### Agent

#### Changed

- Sending direction changes to running Workers now reuses pause/resume and transcript-resume mechanisms, matching main Agent conversations. The former custom intervention-persistence protocol affected scheduling barriers, recovery and over ten activity-query filters. Messages now enter the next input round; intents run in dedicated goroutines outside the three-slot worker pool and start immediately. The frontend retains the message box, restores Continue Directly, and sends through SSE. No DB schema change. Tradeoffs: messages stay in memory without crash recovery, and sending may briefly exceed task concurrency by one worker, accepted for this infrequent action.

### Tasks

#### Fixed

- Fixed OOM crashes when archiving large tasks: Snapshots are now streamed instead of loading the entire task into memory. Also closed three cold-archive recovery gaps: modern installations store traffic only in SQLite, so a crash between PostgreSQL and SQLite commits could strand archived traffic in hot storage. A staging journal is now written regardless of legacy directories, and missing `journal.json` is treated as discardable.
- Fixed sluggish systems with many tasks, including delayed conversation/UI loading. Optimized task-list, task-context and exploration-record queries, and reduced duplicate frontend requests on dashboards, conversations and task details.

### Assets

#### Changed

- Removed the 256-rule company asset-scope limit: Companies entering individual IPs/domains easily exceeded it and had to split into multiple companies, although rule count alone did not make scope slower. Removed limits in frontend, backend and demo mocks. Individual rules still cap at 1024 characters, and the 2 MiB request-body limit remains as a safeguard, roughly forty to fifty thousand rules.

### Skills

#### Fixed

- Fixed skill archive uploads failing with zip: unsupported compression: Go's standard library supports only Store/Deflate, so bzip2/Zstandard archives from nondefault compression settings could not unpack. Added pure-Go decompressors without new external dependencies. Truly unsupported Deflate64/LZMA/XZ/PPMd and encrypted archives now receive Chinese messages before extraction, naming the file, method and repacking guidance rather than exposing low-level English errors.
- Fixed skill-file validation rejecting Chinese filenames: The `[A-Za-z0-9-_./]` ASCII allowlist rejected entire archives containing names such as `参考/说明.md`. Replaced it with a Unicode denylist allowing multilingual filenames and spaces while rejecting control characters, invalid UTF-8, zero-width/bidirectional controls (RLO disguises), `\ % # ? * : " < > |`, and `..` / absolute paths / empty segments. Path-traversal protection is unchanged. Skill names also permit non-ASCII letters such as Chinese; ASCII remains restricted to lowercase letters, digits and hyphens per agentskills.io, and spaces, dots and separators remain disallowed.
- Fixed Chinese ZIP archives from Windows tools producing garbled names or being rejected: Such archives may omit the UTF-8 flag and encode names as GBK; fallback GBK decoding now precedes path validation. Quoted frontmatter such as `name: "中文技能"` also yields the correct skill name.

### UI

#### Added

- Added a flat All Findings view as the default, switchable with By Task tabs. Grouped views require expanding every task just to scan findings across tasks. The flat table uses 10/20/50/100 entries per page and supports the same actions: select/export, inline evidence/reports, name/type/severity edits, disposition changes, deeper investigation and deletion. Views share statistics and filters; switching preserves filters and stores both view and filter preferences locally. Only the active view polls; inline edits update both caches to avoid stale data on switching.
- Added a By Asset findings view: A left tree shows company → root domain/IP → subdomain → service → endpoint, with company levels only when ownership exists. The right table shows findings across the selected subtree, sharing the other views' table and filters. Only assets with findings enter the tree, with ancestors filled as needed; subtree counts deduplicate findings. Findings with deleted or unassociated assets go into Unassociated Assets. Unlike the other views, this navigation tree does not poll: queries run on entry, filter changes, in-page finding changes or explicit refresh, not every 5 seconds. Each level displays only its increment over the parent (subdomain without root suffix, service as `https :443`, endpoint path only), with full values in hover text/breadcrumbs. If nodes exceed limits, endpoint/service levels are omitted wholesale with a notice while counts remain aggregated above.

#### Fixed

- Fixed conversation history being squeezed and clipped on phones: Collapse the conversation list on narrow screens to give the history more width.

### Dependencies

#### Changed

- Upgraded norma v0.3.2 → v0.3.3: Added `Config.MaxTokensField` so OpenAI Chat Completions output limits can use `max_completion_tokens`, required by reasoning models. The two keys are mutually exclusive; default remains `max_tokens`.
- Upgraded `golang.org/x/mod` v0.37.0 → v0.40.0, fixing two dependency security alerts.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)
- [@neouks](https://github.com/neouks)
- [@begininvoke](https://github.com/begininvoke)

## [0.3.6] - 2026-08-27

### LLM

#### Fixed

- Fixed the Non-streaming switch reverting to Streaming when reopened after saving (#69): The configuration-list DTO omitted `streaming`; responses never included it, so frontend `undefined` always fell back to streaming. Writes and storage were correct, but reads were not. Restored the DTO field without `omitempty`, so `false` is returned too.
- Connection tests now require an actual model reply and use the configuration's real send/receive mode (#65). Previously any HTTP success passed even with no reply because thinking exhausted the budget, safety filters swallowed text or compatibility layers dropped `content`; tests also always streamed, testing a different path for non-streaming configurations. Empty replies now fail; successful notices display the model reply, and tests use the current streaming switch, aligning test success with working conversations.

### Agent

#### Changed

- `list_facts` now uses pagination and keyword filtering to avoid overflowing context when many facts exist (#74). Defaults to the latest 20, supports `limit` up to 100, `before` cursor and `q` summary keywords, and returns `{facts, total, has_more, next_before}`. Long summaries are character-truncated; `node_detail` retains full text. Worker/planner prompts reflect pagination. A one-time migration refreshes parameter schemas in the tool catalog because `SeedTool` only inserts initially; otherwise tool management would show no parameters.

### Tools

#### Added

- Added tool-call statistics to Tool Executions (#72): A Statistics toolbar button opens counts, shares and failures per tool, sorted by descending count. Uses task/keyword filters across the whole result set, not just the page, and loads only when opened.

### Dependencies

#### Changed

- Upgraded norma v0.3.1 → v0.3.2: Fixed silently discarded reasoning/refusal in OpenAI responses (added `reasoning_text` for Responses), deduplicated three reasoning-field names, bounded empty-response retries for zero content blocks, and fixed compaction splitting tool pairs and causing gateway 400s, including persisted transcript orphans.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)

## [0.3.5] - 2026-08-25

### LLM

#### Added

- Each LLM configuration supports streaming/non-streaming, default streaming: Enabled uses SSE; disabled uses genuine non-streaming (`stream:false`, one complete JSON response), bypassing faulty gateway SSE implementations such as empty frames or dropped thinking fields at the cost of live progress and token counts. Worker/planner/mainagent/chat/goals resolve it dynamically from the active configuration. `llmpool` / `llmrec` / task-runtime Provider wrappers all support non-streaming. Added `streaming` to `llm_profiles` with `ALTER` for old databases, defaulting to `true` without changing existing configurations.
- Added OpenAI Responses API LLM configurations: A third `openai-responses` format sends `POST /v1/responses`, alongside Chat Completions/Anthropic, with `BaseURL` normalization and default model `gpt-5`. Added `openai-responses` to the `llm_profiles` `format` constraint and idempotently migrated old databases. Frontend adds OpenAI (Responses API). Upgraded norma to v0.3.1, including `reasoning_content` propagation fixes.
- Record raw LLM request/response HTTP bodies at the transport layer, preserving tool schemas, `tool_use` blocks and raw SSE frames absent from normalized views. Each internal norma retry is retained separately. Added `raw_request` / `raw_response` to `llm_records` with `ALTER` for old databases. Recording details now offer a Raw view and request/response copy buttons, including an insecure-context `execCommand` fallback.

### Conversations

#### Changed

- Conversation multiselect is now an explicit mode: Default lists omit persistent row checkboxes, with a Total N + Multiselect header button. Entering the mode enables checkboxes, select-all and bulk deletion; Done exits and clears selection. Fully successful bulk deletions exit automatically, while failures retain the mode for retries. Individual rename/pin/delete remain in each row's ⋯ menu.

### UI

#### Changed

- Improved task management, conversation operations and traffic viewing (#57): Persist task-column sorting preferences, trigger inline renaming directly with icons rather than menus, and refine sheet interactions and traffic details.

#### Fixed

- Worker asset labels show only domains and IPs and correctly handle empty labels.

### Agent

#### Added

- Added quantitative acceptance checks before planner goal completion: When goals specify measurable conditions such as X% asset coverage, N flags or a permission, check measured `graph_overview` values (`coverage.pct`, finding counts, etc.) before `prove_goal`. If unmet, do not call `prove_goal`; dispatch intents to close the gap rather than claiming the main part is done. Fixes marking a 100%-coverage goal complete at only 40% measured coverage.

#### Changed

- Rewrote the planner's zero-intent criterion: Calling it the most common and important principle caused premature stopping with unmet goals and untested scope. Zero intents now applies only when all proposed directions are already covered by open/running/recent_done intents, or when the next step depends on outputs from currently running work that have not arrived (wait for completion, graph update and the next wake-up). Conversely, uncovered independent directions or unmet goals with untested surfaces must not be abandoned merely because zero-intent rounds are common.
- Strengthened evidence thresholds for worker negative conclusions: Claims such as not injectable, port closed or no login entry can cause planners to abandon whole directions, so workers must exhaust reasonable within-intent methods (encoding/parameter/path/method changes) first. Incomplete methods or weak evidence require `confidence=inferred`, avoiding careless `observed` negatives that close routes, especially early mistakes that are hard to recover from.
- These planner/worker default-prompt changes are appended and selected as new versions through one-time migrations (`reseedPlannerPrompt` / `reseedWorkerPrompt`, each guarded by a settings flag). Older versions remain in history, allowing users to restore customized prompts.

### Operations

#### Added

- Added `reset-password.sh` to reset the administrator password (fixed username `ARTEX`): Supports local/docker deployments, with explicit connection settings or discovery from `--dsn`/`$ARTEX_PG_DSN`/`config.json`. Uses database `pgcrypto` to generate a backend-compatible bcrypt hash and writes `settings.auth.password_hash`; no service restart required. Passwords enter through environment variables rather than process argv and are escaped against injection.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)
- [@neouks](https://github.com/neouks)

## [0.3.4] - 2026-08-24

### UI

#### Added

- Selected tasks can have their categories changed in bulk. Uncategorized removes tasks from a category; the batch writes in one transaction, and only tasks deleted since selection can fail.

#### Changed

- New-task categories now use searchable input rather than a dropdown: Typing filters existing categories; Enter or Create immediately creates/selects missing names. Selection appears as a removable tag; only one category is allowed.

### Conversations

#### Fixed

- Fixed messages being blocked as LLM not configured when a conversation had a selected configuration but none was globally active. Pre-send checks used only the global configuration, while execution preferred the conversation selection. Both now share resolution rules: conversation/Agent binding first, global fallback.
- Unavailable-chat notices distinguish no configuration (add one) from configurations present but inactive (activate or select one for this conversation), rather than always reporting unconfigured.

### Agent

#### Added

- For tasks with all goals met, Workers can directly claim and execute main-Agent intents from `add_intent`, then stop. Planner does not run without open goals, avoiding it reaffirming completion and cancelling newly dispatched intents. The task returns to completed after draining the frontier. Before dispatching, main Agent asks whether to register the intent as a formal goal; registration restores normal autonomous planning.

#### Changed

- When `step_ids` exceeds the five-step limit in `get_worker_trace` / `get_task_worker_trace`, return complete content for the first five rather than failing. `returned_step_ids` / `omitted_step_ids` / `notice` identify included/remaining steps and advise that further retrieval is unnecessary if sufficient. Duplicate and invalid IDs are removed before counting.

#### Fixed

- Task lists now sort by descending task ID rather than creation time. Tasks created simultaneously shared timestamps and unstable ordering; 10-second polling and random map iteration caused them to swap positions repeatedly.

### Assets

#### Fixed

- Fixed one dirty asset row breaking company ownership recalculation: Hostnames in `assets.ip` from Agent/API writes made `a.ip::inet` raise `22P02`, rolling back company-scope creation/edits and company deletion. Safe `try_inet()` casts skip invalid values instead of aborting the statement.
- Unparseable `ip` values are no longer silently skipped: Saving company scopes reports the count, IDs and values of assets with invalid `ip` values and warns they cannot match IP/CIDR ownership rules. The same notice is logged for paths without frontend responses, including company deletion, scopesentry sync and Agent writes.
- Task-scope IP/CIDR matching also uses `try_inet()` instead of the former character-set regex guard, which still admitted all-hex hostnames such as `abc.def` and raised the same error.

#### Changed

- `ip`, `service` and `endpoint` assets no longer accept hostnames in `ip`: `insert_assets` and asset APIs return per-item errors with `index` and correction guidance: use `type=subdomain` with `domain`, or resolve A/AAAA first. Agents can correct and reinsert; other items in the batch are stored normally.

### Contributors

- [@neouks](https://github.com/neouks)

## [0.3.3] - 2026-08-23

### Worker

#### Added

- Running Workers support individual pause, resume and cancellation. Pause preserves intents, facts and findings; cancellation transactionally removes the current intent and its direct products after execution exits.
- Added `paused` intent state, execution fences and named termination reasons to prevent late blackboard writes after pause, cancellation or task deletion.
- Added an optional task-concurrency cap; creation, resume, vulnerability investigation and queue refill all use persisted FIFO admission.

#### Changed

- Changed the default Worker wall-clock run duration from 600 to 1200 seconds; revived timed-out tasks restart their timer on the next real execution.
- Actual Worker, Planner and main-Agent execution states now drive task badges consistently, fixing Idle being displayed while Workers run.
- Worker conversations retain individual controls and current-conversation token totals; model names move to the right of the current conversation title.

#### Removed

- Removed Worker multiselect, select-all and bulk pause/continue UI, along with bulk-control APIs and Mock contracts.
- Removed Worker row token badges/tooltips while retaining complete token ledgers and task aggregation APIs.

### LLM

#### Added

- Tasks support ordered LLM configuration chains, switching automatically on explicit provider quota exhaustion and persisting current configuration, exhaustion status and error summaries.
- Running/paused tasks can edit whole chains, reorder configurations and manually switch the current configuration, effective from the next LLM call.
- Automatic/manual switches and whole-chain exhaustion produce structured system activity and deduplicated task-activity notifications.
- Added task-role model resolution APIs to consistently resolve configurations/models for the next Main Agent, Planner and Worker call.
- Added an optional global LLM Pool with call order, designated-model failure fallback, health status, cooldown recovery and manual reset.
- Added an always-on LLM usage ledger aggregating input, output and cache tokens by task, conversation, model and configuration.

#### Changed

- Goal decomposition, Planner, Worker and main Agent share a task-level LLM runtime (resolution priority below).
- Failover responds only to explicit quota, balance or billing errors, not ordinary rate limits, authentication, network, server or context errors.
- LLM configuration pages now use cards and a right-side editing drawer, with Pool order, priorities, exclusions, health and recovery controls.
- Chain-exhaustion messages wrap on narrow screens; current models move from list icons to text beside the current conversation title with complete tooltips.
- Task-role LLM resolution now follows Agent binding → task chain → global. Explicit model bindings always win; unbound roles use the task chain, then global configuration if the chain is empty.
- Empty outbound proxies now connect directly rather than falling back to `HTTP_PROXY`/`HTTPS_PROXY` (explicit `ARTEX_LLM_PROXY` unaffected). Proxy input supports authenticated `socks5://user:pass@host:port`.

#### Fixed

- Transient streaming failures before any output is delivered now retry safely with backoff on the same provider, reducing runs that stop after one or two tools without a summary and end as `model_error`. Quota exhaustion, oversized contexts and deterministic 4xx errors are not retried, remaining subject to failover and compaction recovery respectively.

#### Removed

- Removed conversation-list LLM icons to avoid confusion with Worker status icons.

### UI

#### Added

- Tasks support global category creation, renaming, deletion and filtering; new tasks can select categories directly.
- Added global task-template CRUD and a right-side management drawer; new tasks can load preset descriptions/goals or save current content as templates.
- New tasks can associate multiple source tasks and company asset scopes; one multiline input recognizes domains, URLs, IPs, CIDRs, ICP records and company keywords.
- Task test assets support live addition/deletion and record manual, company, inherited or Agent-discovered origins; Worker conversation titles show current test assets and source summaries.
- Findings group by task with independent pagination; vulnerability descriptions can create high-priority investigation intents.
- Conversations support rename, pin/unpin and deletion; task lists support current-page bulk pause/continue.
- Traffic and tool-execution details use right-side drawers; HTTP messages include `Host` and highlight request/status lines, headers, JSON and markup bodies.
- Task-list actions add Details and Pause/Continue. Conversation send shortcuts are configurable in system settings (`Enter` / `Cmd+Enter`, etc.); web search adds proxy input.
- Badges beside conversation titles show LLM configuration names, with model IDs in hover tooltips. Tasks support optional names and name-column search, falling back to descriptions when empty.
- Skill pages show usage counts, last-used time and missing dependencies to help identify inactive or uninstalled skills.

#### Changed

- Task titles are focusable detail links; task/company assets, finding task groups and grouped vulnerabilities use real server pagination, stable sorting and exact totals.
- Company creation uses a right-side drawer and a single multiline scope input with live recognition, validation and type previews.
- Main-Agent input grows automatically, sends with `Enter`, inserts newlines with `Shift+Enter`, and avoids accidental sends during Chinese IME composition.
- Agent previews, task reports and related details share Markdown rendering; deletion confirmations, long errors and mobile drawer widths are consistently fixed.
- Task-template selectors display/search names but submit IDs; restored original system font sizes and standardized application version display to `0.3.3`.
- Task totals and current-conversation tokens highlight only input, cache-read and output values; send buttons use a simpler upward arrow.
- Task-overview scopes display company names instead of IDs.

#### Fixed

- Ordinary dotted text is no longer misclassified as an ICP filing number.
- Fixed Agent-editor variable lists rendering duplicate keys when catalog names collided with global runtime variables such as `{{.Now}}`.

#### Removed

- Removed separate Enter buttons from task cards; task titles consistently open details.
- Removed dashboard New Task buttons, company Logo URL inputs, and vulnerability-count badges in finding headers/task groups.
- Reverted the global 10% font increase and removed Worker checkboxes, model icons and row-level token statistics from conversation lists.

### Agent

#### Added

- New tasks can associate multiple existing tasks and inherit direct sources' goals, facts, findings, completed intents, asset scopes and blackboard context live and read-only.
- Blackboard readers query source-task nodes, facts, findings and traces on demand; inherited nodes carry source markers and all write tools reject modifications.
- Company-scope tools support domains, URLs, IPs, CIDRs, ICP records and company keywords. Keywords guide Agent scope but do not affect automatic asset ownership.
- Vulnerability investigation creates high-priority human Worker intents in the original task, with asset anchors and `derived_from` edges.
- Overview adds Goal Management with manual view/add/edit/delete. Adding/editing notifies Planner and revives tasks; deletion hard-deletes goal nodes, cascading edges/anchors, without revival.
- Main Agent receives `steer_work` by default, injecting live course corrections into running Workers without interruption or lost progress, while still validating that the intent belongs to the task.

#### Changed

- Source-task intents do not enter new-task frontiers; new tasks keep independent explorations, execution queues, work directories and conversation histories.
- Deleting running intents no longer destroys data: Stop as `stopped`, require a reason, attach it as an intent fact and payload, and notify planner through a `cancelled` trigger, retaining intent contents and reasons.
- Main-Agent conversations use server activity streams; failed sends restore input. Opening conversations scrolls to the bottom and keeps the last reply visible after lazy details load.
- Task pause terminates current Main Agent, Planner and Worker calls but does not prevent users starting new main-Agent orchestration conversations while paused.
- Cancellation, closure and stream interruption consistently retain actual termination reasons, generated content, rounds, duration, tokens and unanswered tool calls.

#### Removed

- Removed main-Agent client optimistic message echoes to avoid duplicate messages and cross-conversation streams during pauses, failures or concurrent activity.

### Constraints

#### Added

- Goal decomposition extracts allow/deny operating constraints before goals; main Agent can add constraints at runtime. Constraints enter Planner/Worker system prompts at highest priority, and debiased diversity/breadth exploration explicitly obeys them.
- Overview adds Constraint Management and CRUD APIs; injection can be toggled separately for Planner/Worker, both on by default and reread every round. New `task_constraints` uses `CREATE TABLE IF NOT EXISTS`, automatically creating the table in old databases.

### Interception

#### Added

- Command interception adds model fallback approval after regex/string rules: When no rule matches, the model decides `ALLOW`/`ASK`/`DENY` semantically. Failure fallback and approval-timeout actions are configurable. The page separates Interception Rules and Model Configuration tabs; model decisions show the `[模型]` prefix and reason.

#### Fixed

- Hardened judge-output parsing to avoid misreading valid `DENY` decisions as allowances.

### Traffic

#### Changed

- Traffic recording stores whole exchanges in SQLite, spilling large bodies into hash-deduplicated blobs and indexing text with trigram full-text search for arbitrary substrings and Chinese. Deletion becomes one SQL transaction, reducing hours to milliseconds without stopping recording. Added streamed large-body downloads and full-text parameters to `traffic_search`; legacy file-tree data remains readable, searchable and deletable without migration.

### Tasks and Assets

#### Added

- Task creation adds an asset-coverage switch, on by default. When off, coverage is neither calculated nor displayed, situation graphs show assets only, `task_scope` does not accumulate automatically, and related tools are removed from Planner/main Agent. Company association is unaffected.
- Each `insert_assets` item adds `related`, default `true`, effective only when coverage is enabled. `false` stores assets globally without counting toward this task's coverage, such as incidental neighboring sites or unrelated assets.
- Company scopes and task test assets recognize domains, URLs, IPs, CIDRs, ICP records and keyword text consistently. Domains/IPs create or reuse global assets; CIDRs/ICP/keywords remain task-scope context.

### Build

- `build.sh --release` builds Linux amd64/arm64, macOS amd64/arm64 and Windows amd64 together, producing ZIP releases with `skills/`, configuration examples and README.
- Go linker strips debugging information for ZIP releases; UPX is explicitly optional because its self-extracting ELF can segfault at startup on some Linux environments.
- Release Workflow smoke-tests Linux amd64 binaries at startup and supplies `SHA256SUMS` with packages.

### Contributors

- [@neouks](https://github.com/neouks)

## [0.3.2] - 2026-08-20

### Added

- New tasks associate multiple existing tasks and inherit direct-source facts, findings, completed intents, asset scopes and blackboard context live and read-only, while keeping independent execution queues, work directories and conversation histories.
- Tasks support ordered LLM chains, switching automatically on explicit provider quota exhaustion and persisting current configuration, exhaustion status and structured audit activity.
- Running/paused tasks can edit LLM chains, reorder them and manually switch configurations; automatic/manual switches and full-chain exhaustion are shown in task details.
- Running Workers support pause, resume and cancellation. Pause preserves blackboard data; cancellation transactionally removes the intent and its directly produced facts, findings and execution records after Worker writes stop.
- Task deletion can also remove associated assets, traffic, vulnerabilities and task files, with deletion barriers, concurrency protection and auditable deletion statistics.
- Added an optional task-concurrency cap; new tasks queue FIFO at the cap and start automatically when slots become available.
- Added task/company asset pagination, task-category statistics and paginated-intent Mock contracts.
- Added a single-binary `build.sh` script supporting static frontend export, resource embedding, cross-platform targets and build-version injection.

### Changed

- Explicit task LLM chains coexist with global LLM Pools. Explicit chains retain strict quota-failover semantics; without one, Agent bindings and global rules continue to apply.
- Main-Agent input supports automatically growing multiline text, `Enter` to send and `Shift+Enter` for newlines, avoiding accidental sends during Chinese IME composition.
- Planner, Worker and main Agent share task-level LLM runtime; chains use the smallest candidate context window as a safe compaction threshold.
- Task details show running/idle/paused based on actual LLM calls; source facts, findings, intents, asset references and graph nodes are consistently source-marked and read-only.
- Agent previews, task reports and related details use a shared Markdown renderer.
- LLM configurations use cards and drawers, with independent model-list scrolling inside drawers.
- Task pause no longer blocks main-Agent chat: Orchestration conversations are independent, so new messages can still be sent while paused; pausing terminates only the current round.
- Default Worker run wall-clock duration changed from 600 to 1200 seconds.

### Fixed

- Removed optimistic main-Agent console echoes in favor of server-rendered data, fixing disordered or cross-conversation messages after pause/send failures.
- Opening main-Agent conversations scrolls to the bottom and shows the complete final reply; lazy expansion automatically restores bottom alignment instead of pushing it offscreen.
- Fixed main-Agent conversations continuing after task pause, and orchestration-Agent task pauses failing to stop main Agent simultaneously.
- Fixed task badges/action buttons disagreeing with completion or actual Planner/Worker/main-Agent execution.
- Fixed late blackboard writes or leftover files from races among Worker cancellation, task deletion and concurrent writes.
- Fixed broken Markdown previews, overflowing deletion-confirmation text, mobile widths and misaligned task-detail buttons.
- Added named termination reasons to every Agent cancellation path; activity details show cancelling party, final state, rounds, duration, token usage and unanswered tool calls.
- Fixed shutdown races where parent contexts overwrote named `shutdown` reasons, and garbled Chinese activity summaries caused by byte truncation.
- Fixed cancellation events with partial streaming output losing real termination reasons, while preserving content generated before cancellation.

### Contributors

- [@Autumn-27](https://github.com/Autumn-27)
- [@neouks](https://github.com/neouks)

[Unreleased]: https://github.com/Autumn-27/ARTEX/compare/v0.3.10...HEAD
[0.3.10]: https://github.com/Autumn-27/ARTEX/compare/v0.3.9...v0.3.10
[0.3.9]: https://github.com/Autumn-27/ARTEX/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/Autumn-27/ARTEX/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/Autumn-27/ARTEX/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/Autumn-27/ARTEX/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/Autumn-27/ARTEX/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/Autumn-27/ARTEX/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/Autumn-27/ARTEX/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/Autumn-27/ARTEX/compare/v0.3.1...v0.3.2
