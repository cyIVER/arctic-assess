package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/intercept"
	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/harness"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/permission"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// Worker is an LLM work agent (docs §4.4): it claims ONE intent, completes it
// with real tools (Bash: kali tooling through the recording proxy), writes the
// FACTS it found back into the graph, and stops. It does NOT generate new
// directions (that is the planner's job) and does NOT keep exploring toward the
// goal on its own. Multiple workers run concurrently as goroutines.
// WebSearchOpts is the web-search backend selection the server pushes into each
// agent (planner/worker/main). Enabled=false leaves the web_search tool off.
// Backend is "ddgs" (no key), "brave-free" (BraveKey required), "tavily"
// (TavilyKey required), or "deepseek" (DeepSeek* required, filled from the
// active LLM profile). It maps directly onto agentcore.Options.
// Proxy is a dedicated egress proxy for the search request (http/https/socks5),
// independent of the traffic-recording MITM proxy — set it when the search endpoint
// is only reachable via a VPN/SOCKS proxy. Empty = direct.
//
// Unlike the other three backends, DeepSeek has no directly callable search API.
// Search exists only inside its Anthropic-compatible messages endpoint (web_search_20250305 server
// tool), so every search consumes a model call and its requests originate on DeepSeek servers,
// not via the local Proxy and not in local traffic records.
type WebSearchOpts struct {
	Enabled   bool
	Backend   string
	BraveKey  string
	TavilyKey string
	Proxy     string
	// DeepSeek* comes from the active LLM profile (official DeepSeek endpoint in anthropic format only),
	// not a separate configuration; it changes with the LLM profile.
	DeepSeekBaseURL string
	DeepSeekAPIKey  string
	DeepSeekModel   string
}

type Worker struct {
	nativeExecutor        nativeexec.Executor
	nativeExecutorFactory func(llm.Provider) (nativeexec.Executor, error)
	findingRecorder       FindingRecorder
	prov                  llm.Provider
	model                 string
	workDir               string
	proxyAddr             string
	proxyCACert           string            // recording proxy's CA cert path (for WebFetch HTTPS verify)
	webSearch             WebSearchOpts     // web_search tool backend selection (off by default)
	tx                    *transcript.Store // raw LLM conversation persistence (nil = off)
	window                int               // context window in tokens (for compaction)
	windowFn              func() int        // optional dynamic task-chain minimum
	maxTurns              int               // max agent turns per run (0 = unlimited)
	// runTimeout is the wall-clock budget for the main exploration of one intent
	// (0 = unlimited). When it fires, the run is cut and a settlement round is
	// forced so already-identified facts get written back instead of being lost.
	runTimeout time.Duration
	// extraTools are host-provided tools (e.g. traffic query, oast) appended to
	// the worker's graph write-back tools.
	extraTools []actool.CoreTool
	// injectConstraints resolves whether this task's operation constraints get
	// injected into the worker system prompt. Read per run so the settings toggle
	// takes effect without rebuilding the agent. nil = inject (default).
	injectConstraints func() bool
	// nonStreamingFn resolves whether this run uses the non-streaming (Complete)
	// path. Read per run so a profile/task toggle takes effect without rebuilding
	// the agent. nil = streaming (default).
	nonStreamingFn func() bool
	// noaEnabledFn resolves whether this run uses the experimental noa context-
	// compression mechanism. Read per run, like nonStreaming. nil = off (built-in
	// compaction).
	noaEnabledFn func() bool
	// maxTokensFn resolves the per-reply output cap in tokens, on the same
	// per-run basis. nil or 0 = send no cap and let the endpoint decide.
	maxTokensFn func() int
}

// WorkerSessionID returns the stable transcript key used by a worker intent.
// Worker slots are reusable, so the intent id (rather than work#N) is the
// session identity. Keep this helper public so the Worker message API and UI
// can refer to exactly the conversation that will be resumed.
func WorkerSessionID(explorationID, intentID int64) string {
	return fmt.Sprintf("exp%d-worker-i%d", explorationID, intentID)
}

const workerChatMarkerPrefix = "<!-- ARTEX_WORKER_CHAT:"

func workerChatMarker(requestID string) string {
	return workerChatMarkerPrefix + requestID + " -->"
}

func hasWorkerChatMessage(messages []llm.Message, requestID string) bool {
	marker := workerChatMarker(requestID)
	for _, message := range messages {
		if message.Role == llm.RoleUser && strings.Contains(message.Text(), marker) {
			return true
		}
	}
	return false
}

// SetNonStreaming wires a resolver deciding whether runs use the non-streaming
// model path (true = non-streaming). nil/unset = streaming (default). Read per
// run so a profile or task-chain toggle takes effect without rebuilding.
func (w *Worker) SetNonStreaming(fn func() bool) { w.nonStreamingFn = fn }

func (w *Worker) nonStreaming() bool { return w.nonStreamingFn != nil && w.nonStreamingFn() }

// SetNoaEnabled wires a resolver deciding whether runs use the experimental noa
// context-compression mechanism. nil/unset = off (built-in compaction). Read per
// run so the settings toggle takes effect without rebuilding the agent.
func (w *Worker) SetNoaEnabled(fn func() bool) { w.noaEnabledFn = fn }

// SetMaxTokens wires a resolver for the per-reply output cap. nil/unset or 0 =
// send no cap and let the endpoint decide. Read per run, like nonStreaming.
func (w *Worker) SetMaxTokens(fn func() int) { w.maxTokensFn = fn }

func (w *Worker) maxTokens() int {
	if w.maxTokensFn == nil {
		return 0
	}
	return w.maxTokensFn()
}

// SetConstraintInject wires a resolver deciding whether this task's operation
// constraints get injected into the worker system prompt. nil = inject (default).
func (w *Worker) SetConstraintInject(fn func() bool) { w.injectConstraints = fn }

// wantConstraints reports whether constraint injection is enabled (default yes).
func (w *Worker) wantConstraints() bool { return w.injectConstraints == nil || w.injectConstraints() }

// SetRunTimeout configures the per-intent wall-clock budget for the main
// exploration (0 = unlimited). When it fires, the SDK settlement phase still runs
// so facts are never lost to a timeout. Safe to call before Execute.
func (w *Worker) SetRunTimeout(run time.Duration) {
	w.runTimeout = run
}

// settleWrapUpPrompt is injected by the SDK settlement phase when a worker hits its
// turn/time budget: stop probing, write back what was found, then end with a
// plain-text one-liner (which becomes this run's displayed result).
const settleWrapUpPrompt = "You are about to be terminated because your budget is exhausted. Do not run any more commands or probes. In order: (1) Persist each identified but unsaved result: insert_assets for new assets, record_fact for exploration conclusions/facts, report_finding for confirmed vulnerabilities. (2) **End with a separate single plain-text sentence** summarizing what you did and the key conclusions (this sentence is displayed as the run result and must be output)."

func NewWorker(prov llm.Provider, model, workDir string, tx *transcript.Store, window, maxTurns int, extra ...actool.CoreTool) *Worker {
	return &Worker{nativeExecutorFactory: NativeWorkerExecutor, prov: prov, model: model, workDir: workDir, tx: tx, window: window, maxTurns: maxTurns, extraTools: extra}
}

// defaultToolsExcept returns actool.DefaultTools() minus the named tools (by
// CoreTool.Name()). Used to trim SDK default tools an agent shouldn't have.
func defaultToolsExcept(exclude ...string) []actool.CoreTool {
	drop := make(map[string]bool, len(exclude))
	for _, n := range exclude {
		drop[n] = true
	}
	all := actool.DefaultTools()
	out := make([]actool.CoreTool, 0, len(all))
	for _, t := range all {
		if !drop[t.Name()] {
			out = append(out, t)
		}
	}
	return out
}

// SetNativeExecutor is a trusted host-only integration point; nil keeps native workers unavailable.
func (w *Worker) SetNativeExecutor(e nativeexec.Executor) { w.nativeExecutor = e }

// SetNativeExecutorFactory is host-only; invoked only after native task admission.
func (w *Worker) SetNativeExecutorFactory(f func(llm.Provider) (nativeexec.Executor, error)) {
	w.nativeExecutorFactory = f
}

func (w *Worker) SetCompactionWindowResolver(fn func() int) { w.windowFn = fn }

func (w *Worker) compactionWindow() int {
	if w.windowFn != nil {
		return w.windowFn()
	}
	return w.window
}

// SetProxy configures the recording proxy address that workers route target
// traffic through, plus the CA cert path WebFetch trusts to verify HTTPS through
// that MITM proxy. Empty addr disables the hint.
func (w *Worker) SetProxy(addr, caCert string) { w.proxyAddr, w.proxyCACert = addr, caCert }

// SetWebSearch selects the web_search backend for this worker (off by default).
func (w *Worker) SetWebSearch(o WebSearchOpts) { w.webSearch = o }

// proxyEnv builds the Bash-subprocess env that routes child-command HTTP through
// the egress proxy (the recording MITM when capture is on, or the global proxy
// directly when it is off) and, only when a MITM CA is present, makes the common
// toolchain trust it — so tools need no manual -x/--proxy/-k. Each ecosystem reads
// a different CA var (verified empirically): SSL_CERT_FILE→curl/urllib/Go/openssl,
// REQUESTS_CA_BUNDLE→python requests (it ignores SSL_CERT_FILE), CURL_CA_BUNDLE→curl,
// GIT_SSL_CAINFO→git, NODE_EXTRA_CA_CERTS→node; NODE_USE_ENV_PROXY makes Node 24+
// honor the proxy vars. ALL_PROXY is set too so a socks5 egress proxy (which curl
// only reads from ALL_PROXY, not HTTP(S)_PROXY) works in the capture-off path.
// Empty proxyAddr → nil (direct, unchanged env).
func proxyEnv(proxyAddr, caCert string) []string {
	if proxyAddr == "" {
		return nil
	}
	env := []string{
		"HTTP_PROXY=" + proxyAddr, "HTTPS_PROXY=" + proxyAddr,
		"http_proxy=" + proxyAddr, "https_proxy=" + proxyAddr,
		"ALL_PROXY=" + proxyAddr, "all_proxy=" + proxyAddr, // socks5 egress: curl reads only this
		"NODE_USE_ENV_PROXY=1", // Node 24+: honor HTTP(S)_PROXY in built-in fetch/http
	}
	if caCert != "" {
		env = append(env,
			"SSL_CERT_FILE="+caCert,
			"CURL_CA_BUNDLE="+caCert,
			"REQUESTS_CA_BUNDLE="+caCert,
			"GIT_SSL_CAINFO="+caCert,
			"NODE_EXTRA_CA_CERTS="+caCert,
		)
	}
	return env
}

// workerDefaultTmpl is the built-in EDITABLE body (section [A]) of the worker system
// prompt, seeded into agent_prompts. The trafficTool block and the artifact output rules
// are NOT here — they are code-owned and appended by workerSystem after rendering
// (section [B]/[C]), so editing the DB body can never drop them.
const workerDefaultTmpl = `You are the executor (work agent) of an authorized penetration-testing system on a cybersecurity platform. You receive **one intent** (a one-sentence exploration direction). Your sole responsibility: **complete this intent, write discoveries back to the knowledge graph, then stop and return.**

**Boundaries (red lines)**:
1. **Do only the assigned intent**. If exploring it reveals valuable leads beyond its scope (an error-disclosed path, a possible connection to another asset, or another exploitation chain's entry point), **mention them briefly in the fact summary for the planner**.
2. An initial obstacle (filtered payload / 404 / injection without visible output) does not mean the intent is exhausted. Explore all bypass approaches within this intent before concluding.
3. Operate only within the authorized scope. **Operation constraints** at the top of the system prompt are the highest-priority boundaries: check every command/probe before execution and do not perform violations, even if they fall within the assigned intent.

**Write discoveries back as you work** (only graph records count, not memory or prose; record each result immediately so it is not lost when the turn budget runs out). Keep these three write-back destinations distinct:
- **New assets/resources → insert_assets (asset graph)**: subdomains / services / endpoints / fingerprints / credentials and other assets **themselves**. **Register only assets here; exploration conclusions/judgments belong in record_fact.**
- **Exploration conclusions/facts → record_fact (exploration graph; pass intent_id)**: use it for all such results. **Consolidate multiple observations into ONE fact** (a one-sentence summary plus elaboration in detail grounded in the actual execution trace). Do not create a fact per property; normally one fact per intent. Fragmentation makes the graph grow without bound: **default to one fact, merging details into detail**. Use the facts array for separate records only for genuinely independent conclusions that cannot be combined; this is rare, not routine. **Record only new information**: do not rephrase existing facts as new ones; confirmation without new information needs no record. **Record only actual observations**: provide evidence (one concise line with the command and the most probative one or two output lines; details go in detail), and confidence (observed=directly seen / inferred=deduced from behavior).
- **Confirmed vulnerabilities → report_finding (exploration graph, including PoC; pass intent_id)**: **only after actually triggering it in this run and obtaining reproducible evidence (requests/responses or command output)**. Never treat a version/fingerprint CVE match, apparently injectable parameters, or inference from external vulnerability databases/changelogs/code diffs as confirmation. Do not substitute CVE lookups or patch-version comparisons for actual triggering. If suspicious but not triggerable, record an inferred fact with record_fact (the suspicion and why it was not triggered) for the planner, not a finding.

After completing this intent, summarize in one sentence what you did and which facts you persisted.`

// workerTrafficBlock is section [B]: the traffic-tool note, code-injected only when
// traffic capture (recording) is on — i.e. the traffic_* tools actually exist.
// Gated on recording, NOT on the egress proxy: a global proxy with capture off
// routes traffic but records nothing, so the tools would not be there. Not stored,
// not editable.
func workerTrafficBlock(recording bool) string {
	if !recording {
		return ""
	}
	return "\n\n**Traffic tools**:\n- traffic_search / traffic_get / traffic_blob：Review responses and previously visited resources. **Check traffic first; do not curl the same URL again**. traffic_search **requires host** and returns only 3 lightweight index entries by default (id/method/url/status/resp_len, no response body); explicitly increase limit for more. Use body_contains to search request/response bodies (at least 3 characters; supports substrings and Chinese text, e.g. passwords/keys/errors/internal addresses). Read original content with traffic_get(id). Very large bodies appear as @blob sha256:<hash>; retrieve the full text in segments with traffic_blob(hash)."
}

// artifactSpec is section [C]: the code-owned, non-editable tail appended to every
// pentest agent's prompt — intermediate artifacts must land in the shared work
// dir, never /tmp. Guaranteed present regardless of how the DB body is edited.
func artifactSpec(dir string) string {
	return "\n\n**Artifact output rules**: write all intermediate artifacts (scripts, payloads, captured response bodies, temporary data, etc.) **only to this task working directory: " + dir + "** (relative paths resolve here; this absolute path is also allowed). **Do not write to /tmp or use other absolute paths**."
}

// workerArtifactSpec is the worker's section [C]: its per-intent run dir is pre-created
// by the engine (ensureRunDir), so it just writes relative paths there — no manual
// mkdir, no cross-worker name collisions.
func workerArtifactSpec(runDir string) string {
	return "\n\n**Artifact output rules**: write all intermediate artifacts (scripts, payloads, captured response bodies, temporary data, etc.) **only to this intent-specific working directory: " + runDir + "** (already created automatically; write directly using relative paths, without creating the directory yourself). **Do not write to /tmp or use other absolute paths**."
}

// ensureRunDir builds and creates an agent's working directory under base:
// <base>/tasks/<taskID> for planner/main; <base>/tasks/<taskID>/i<intentID> for a
// worker (intentID<=0 → task dir only). The "tasks/" segment groups per-task dirs
// symmetrically with the chat agent's "sessions/<sessionID>". Best-effort mkdir — on
// failure, writes fail the same way an unwritable CWD would.
func ensureRunDir(base string, taskID, intentID int64) string {
	dir := filepath.Join(base, "tasks", strconv.FormatInt(taskID, 10))
	if intentID > 0 {
		dir = filepath.Join(dir, "i"+strconv.FormatInt(intentID, 10))
	}
	_ = os.MkdirAll(dir, 0o755)
	return dir
}

// cmdOutDir is the SDK large-tool-output spill dir under an agent's run dir.
func cmdOutDir(dir string) string { return filepath.Join(dir, "cmd-output") }

func workerSystem(proxyAddr, caCert, dataDir string) string {
	body := renderSystem("worker", workerDefaultTmpl, WorkerVars{ProxyAddr: proxyAddr, DataDir: dataDir, Now: nowStr()})
	// caCert is present only when the recording MITM is on, which is exactly when
	// the traffic_* tools are registered — so it gates the traffic-tool note.
	// Optional finding guidance is added for every role after tool resolution.
	return body + workerTrafficBlock(caCert != "")
}

// renderIntentTask formats the claimed intent for the worker's launch USER message:
// the intent is the worker's whole job. It used to live in the system prompt; it now
// rides in the first user turn (together with the situational overview) so the system
// prompt stays static/role-only — same move as the planner's situational block.
// intentAssetIDs pulls the intent's target asset ids out of its payload
// (planner's add_intent stores them as a numeric asset_ids array). nil on absence
// or malformed payload.
func intentAssetIDs(intent *db.Node) []int64 {
	if intent == nil {
		return nil
	}
	var p struct {
		AssetIDs []int64 `json:"asset_ids"`
	}
	if err := json.Unmarshal(intent.Payload, &p); err != nil {
		return nil
	}
	return p.AssetIDs
}

func renderIntentTask(intent *db.Node) string {
	return fmt.Sprintf("\n\n[Assigned intent (your sole task this run: do only this intent, produce only facts, then stop)]:\n%s\nIntent id: %d (pass it to record_fact / report_finding)", string(intent.Payload), intent.ID)
}

// renderWorkerGraphOverview folds the global situational snapshot into the worker's
// launch USER message for AWARENESS ONLY. The framing is deliberately strong: the overview
// must NOT widen the worker's job — it still does only its assigned intent. Its sole
// purpose is letting the worker read context (existing facts/assets/hints)
// so it avoids redundant work and doesn't re-derive what others already found.
func renderWorkerGraphOverview(data map[string]any) string {
	// Coverage helps planners assess undertested types and scope expansion; this conflicts with the worker's
	// mandate to execute only its assigned intent, not pursue uncovered targets. Remove it from this view.
	// data is a new worker-specific map, so deleting keys does not affect the planner.
	delete(data, "coverage")
	b, err := json.Marshal(data)
	if err != nil {
		return "" // fall back silently: the worker just won't have the global context
	}
	return "\n\n[Global exploration situation (read-only context for your assigned intent)]:\n" +
		"Below is the current task-wide exploration overview. Use it to avoid duplicating others' discoveries and to understand how your assigned intent relates to the wider situation.\n" +
		"**Broad thinking is useful**: think deeply and connect clues while exploring this intent. The boundary is action: do not execute other intents (other workers handle them under the planner). **Record valuable leads as a fact for the planner**, including cross-asset connections, possible entry points to other exploitation chains, or task-wide suspicions. This is an important deliverable, not optional. Prefer sharing an extra lead for the planner to assess over withholding it.\n" +
		string(b)
}

// Execute runs one intent. hooks (the per-task Guard) gates every tool call; may
// be nil. emit, if non-nil, receives one ActivityRecord per execution step.
// notifyFinding, if non-nil, is called (intentID, summary) when this worker writes
// a finding (report_finding) so the task's planner wakes mid-flight — with context
// on which intent found what — instead of waiting for the worker to finish.
// Returns the terminal reason (so the engine can distinguish completed vs
// max_turns) and a per-kind breakdown of what was written back (so an intent that
// explored but persisted nothing isn't mistaken for done, and the engine can log
// facts/assets/findings separately instead of lumping them under "facts").
func (w *Worker) Execute(ctx context.Context, name string, taskID int64, as *db.AssetStore, ts *db.ExplorationStore, intent *db.Node, hooks harness.HookRunner, emit func(db.Activity), enr EnrichTrigger, notifyFinding func(int64, string)) (harness.TerminalReason, WriteCounts, error) {
	return w.execute(ctx, name, taskID, as, ts, intent, hooks, emit, enr, notifyFinding, "", "")
}

// ExecuteWithMessage runs the next turn in the same intent conversation with a
// human-authored message. The HTTP handler does not edit the transcript;
// agentcore records the message as a normal user turn when this Worker starts.
// This keeps Worker continuation identical to the regular agent chat flow.
func (w *Worker) ExecuteWithMessage(ctx context.Context, name string, taskID int64, as *db.AssetStore, ts *db.ExplorationStore, intent *db.Node, hooks harness.HookRunner, emit func(db.Activity), enr EnrichTrigger, notifyFinding func(int64, string), requestID, message string) (harness.TerminalReason, WriteCounts, error) {
	return w.execute(ctx, name, taskID, as, ts, intent, hooks, emit, enr, notifyFinding, strings.TrimSpace(requestID), strings.TrimSpace(message))
}

func (w *Worker) execute(ctx context.Context, name string, taskID int64, as *db.AssetStore, ts *db.ExplorationStore, intent *db.Node, hooks harness.HookRunner, emit func(db.Activity), enr EnrichTrigger, notifyFinding func(int64, string), requestID, message string) (harness.TerminalReason, WriteCounts, error) {
	var runIntentID int64
	if intent != nil {
		runIntentID = intent.ID
	}
	ctx, native, admissionErr := prepareNativeTaskRun(ctx, w.prov, "worker", RunInfo{TaskID: taskID, ExplorationID: explorationID(ts), IntentID: runIntentID}, ts, w.nativeExecutor, w.nativeExecutorFactory)
	if admissionErr != nil {
		return "", WriteCounts{}, admissionErr
	}
	if native != nil {
		as = nil
	} // global asset access is outside this native phase
	tsx := NewToolSet(ts, name)
	tsx.SetFindingRecorder(w.findingRecorder)
	tsx.SetTaskID(taskID)
	coverageEnabled := as == nil || as.CoverageEnabled(taskID)
	tsx.SetCoverageEnabled(coverageEnabled)
	if as != nil {
		tsx.SetAssetStore(as, as.Companies())
	}
	tsx.SetOwnerNode(intent.ID)         // assets this worker discovers anchor to its intent → visible to the task
	tsx.SetEnrich(enr)                  // async DNS/HTTP auto-completion for assets this worker writes
	tsx.SetNotifyFinding(notifyFinding) // report_finding wakes the planner immediately after persistence, carrying intent + finding.
	// base = built-in worker tools ∪ host tools (traffic) ∪ default tools (incl. Bash);
	// then augment with the agent's visible skills/MCP. During the SDK settlement
	// phase, Bash is hidden via Settlement.DisabledTools (no local gating needed).
	base := append(tsx.WorkerTools(), w.extraTools...)
	// Workers deliberately omit MultiEdit/Glob/Grep: use Edit for precise edits and Bash(grep/find) for search,
	// reducing the tool surface and low-value calls. Other SDK defaults (Read/Write/Edit/LS/Bash/Sleep) remain.
	if native == nil {
		base = append(base, defaultToolsExcept("MultiEdit", "Glob", "Grep")...)
	} else {
		base = tsx.NativeRoleBase("worker")
	}
	ctx = WithRunInfo(ctx, RunInfo{TaskID: taskID, ExplorationID: explorationID(ts), IntentID: intent.ID})
	tools, def, cleanup := AugmentTools(ctx, "worker", base)
	defer cleanup()

	// The intent is the worker's SOLE responsibility and run-wide invariant. Put it, startup instructions and
	// raw anchored target assets in the system prompt: rebuilt every run and never removed by compaction.
	// The intent remains throughout long runs; resumption does not depend on retaining the initial transcript
	// message. Per-intent variability sacrifices cross-intent system caching deliberately: losing intent is worse.
	// This differs deliberately from the planner's situational user turn: a planner generates intents and has
	// no single mandate; a worker does. Only degradable, potentially stale global overview stays in startup user input.
	// The engine creates this intent's private working directory <workDir>/tasks/<taskID>/i<intentID> first.
	runDir := ensureRunDir(w.workDir, taskID, intent.ID)
	// The run-wide intent is not the current tool action. Do not forward it or
	// inherit a parent run's background into the action reviewer.
	ctx = intercept.WithReviewContext(ctx, runDir, intercept.ReviewBackground{})
	overview := renderWorkerGraphOverview(tsx.graphOverviewData())
	sysBody := workerSystem(w.proxyAddr, w.proxyCACert, w.workDir)
	if w.wantConstraints() {
		sysBody += constraintBlock(ts) // Inject operational constraints into the system prompt for strict worker compliance.
	}
	// Append intent → anchored assets → startup instructions to system, like constraintBlock.
	intentTail := workerArtifactSpec(runDir) + renderIntentTask(intent)
	if as != nil {
		if ids := intentAssetIDs(intent); len(ids) > 0 {
			if assets, err := as.GetByIDs(ids); err == nil && len(assets) > 0 {
				if b, err := json.Marshal(assets); err == nil {
					intentTail += "\n\nTarget assets corresponding to this intent's asset_ids:\n" + string(b)
				}
				// Assets explicitly targeted by this intent automatically enter task scope at the same conservative
				// granularity as insertAssets. upsertTaskScope's ON CONFLICT DO NOTHING and uq_task_scope
				// unique index prevent duplicates; reruns/retries are idempotent no-ops.
				// Do not accumulate test scope (denominator) when asset coverage is disabled.
				if coverageEnabled {
					for _, a := range assets {
						_ = as.AddAutoScope(taskID, a.Type, a.Domain, a.URL, a.IP)
					}
				}
			}
		}
	}
	intentTail += "\n\nExecute the intent above: do only this intent, produce only facts, assets, and findings, then stop."
	system, boundary := deferredSystemWithTail(sysBody, intentTail, def)
	// Task deadline from ctx clamps wall-clock budget and selects wrap-up text (see taskclock.go).
	tc := taskClockFrom(ctx)
	maxDur, clamped := clampMaxDuration(tc.DeadlineUnix, w.runTimeout)
	settle := wrapupSettlement("worker", []string{"Bash"})
	if tc.DeadlineUnix > 0 {
		settle = wrapupSettlementForTask("worker", []string{"Bash"}, clamped)
	}
	opts := agentcore.Options{
		Provider:        w.prov,
		SystemPrompt:    system,
		DynamicBoundary: boundary,
		Tools:           tools,
		DeferredTools:   def.Deferred,
		UnlockSet:       def.Unlock,
		PermissionMode:  permission.ModeBypass,
		// WebFetch uses the recording proxy; HTTP is recorded like curl. Load the proxy CA so MITM-reissued
		// HTTPS certificates VERIFY normally, rather than disabling verification. Empty proxy means direct.
		EnableWebFetch: true,
		WebFetchProxy:  w.proxyAddr,
		WebFetchCACert: w.proxyCACert,
		// Optional web search: ddgs needs no key; brave-free needs BraveKey; tavily needs TavilyKey.
		// WebSearchProxy is separate egress (http/https/socks5), unrelated to traffic-recording MITM proxy; empty means direct.
		EnableWebSearch:       w.webSearch.Enabled,
		WebSearchBackend:      w.webSearch.Backend,
		BraveSearchAPIKey:     w.webSearch.BraveKey,
		TavilySearchAPIKey:    w.webSearch.TavilyKey,
		DeepSeekSearchBaseURL: w.webSearch.DeepSeekBaseURL,
		DeepSeekSearchAPIKey:  w.webSearch.DeepSeekAPIKey,
		DeepSeekSearchModel:   w.webSearch.DeepSeekModel,
		WebSearchProxy:        w.webSearch.Proxy,
		// Bash subprocess HTTP uses recording proxy + trusted CA by default (no -x/-k needed).
		BashEnv:    proxyEnv(w.proxyAddr, w.proxyCACert),
		WorkingDir: runDir,
		MaxTurns:   w.maxTurns, // 0 = unlimited (configurable in agent management)
		// Wall-clock budget, checked at turn boundaries without mid-step interruption; 0 = unlimited. Task deadline
		// clamps to min(own budget, remaining time), entering wrap-up when the task expires (see taskclock.go).
		MaxDuration: maxDur,
		// Turn or duration budget → SDK wrap-up round (Bash hidden), persisting identified results.
		// When task-deadline-clamped, PromptByReason maps timeout to task-timeout wrap-up,
		// and turn exhaustion within the window to per-run wrap-up. Unclamped remains per-run only.
		Settlement: settle,
		// large tool output spills to cmd-output/ with a head + pointer (SDK tool.Capture);
		// Full output preserved on disk. Use SDK truncation default (30000 characters).
		ToolOutputDir: cmdOutDir(runDir),
		Compaction:    compactionConfig(w.compactionWindow()), // long tool-heavy runs stay within the window
		Todos:         actool.NewTodoStore(),                  // Session-local temporary planning todos (TodoWrite); discarded on exit.
		NonStreaming:  w.nonStreaming(),                       // Use Provider.Complete when the profile selects non-streaming.
		MaxTokens:     w.maxTokens(),                          // 0 omits the cap and uses the server default.
	}
	if hooks != nil { // typed-nil guard: only set when concrete (avoids harness panic)
		opts.Hooks = hooks
	}
	if w.tx != nil { // persist raw LLM conversation; one file per worked intent
		opts.Transcript = w.tx
		opts.SessionID = WorkerSessionID(ts.ID(), intent.ID)
	}
	intentID := intent.ID
	emitWrap := func(r db.Activity) {
		if emit != nil {
			r.NodeID, r.Worker = &intentID, name
			emit(r)
		}
	}
	// Intent / startup instructions / anchored assets are already in system (sysBody assembly above).
	// This startup user message carries only degradable global overview; compaction may safely remove it.
	// If overview marshaling unusually fails/returns empty, use a startup phrase rather than an empty first message.
	input := overview
	if strings.TrimSpace(input) == "" {
		input = "Execute the intent assigned in the system prompt: do only this intent, produce only facts, assets, and findings, then stop."
	}

	// Experimental: noa takes over context compression when enabled; persistent archives live under <workDir>/noa/<SessionID>.
	noaSession := WorkerSessionID(ts.ID(), intent.ID)
	if native == nil {
		enableNoa(&opts, w.noaEnabledFn, w.workDir, noaSession, noaWarn(noaSession))
		ctx = attachSideCapture(ctx, &opts)
	} else {
		var err error
		ctx, err = finishNativeTaskOptions(ctx, native, &opts)
		if err != nil {
			return "", WriteCounts{}, err
		}
	}
	s := agentcore.NewSession(opts)
	defer s.Close() // release the session's background-task manager (temp dir + processes)

	// Resume prior conversation if this intent was paused/blocked/exhausted and is
	// being re-run. The transcript ID is deterministic per intent, so if a prior
	// session exists the worker continues from where it left off instead of
	// restarting from scratch.
	alreadyRecorded := false
	if w.tx != nil {
		_ = s.Resume(opts.SessionID)
		alreadyRecorded = requestID != "" && hasWorkerChatMessage(s.Messages(), requestID)
		if len(s.Messages()) > 0 && message == "" {
			seedUnlockFromHistory(s.Messages(), def.UnlockSkill)
			input = "Continue execution."
		} else if len(s.Messages()) > 0 {
			seedUnlockFromHistory(s.Messages(), def.UnlockSkill)
		}
	}
	if message != "" {
		if alreadyRecorded {
			input = "Continue executing the new intent from the previous human chat input. Do not repeat completed actions."
		} else if len(s.Messages()) > 0 {
			input = workerChatMarker(requestID) + "\n[New intent from human chat input]\n" + message +
				"\n\nExecute this human input immediately; afterward, use the context to decide whether the original task should continue."
		} else {
			input += "\n\n" + workerChatMarker(requestID) + "\n[New intent from human chat input]\n" + message +
				"\n\nPrioritize this human input."
		}
	}

	// Budgets + settlement are owned by the SDK (MaxTurns/MaxDuration + Settlement):
	// on hit it runs a wrap-up turn and finishes with ReasonMaxTurns/ReasonTimeout.
	// MaxDuration now interrupts an in-flight tool at the wall-clock deadline and
	// enters the wrap-up phase on the live ctx, so a run whose tool overran the budget
	// still settles (no external hard-timeout backstop needed). ctx itself carries only
	// pause / planner kill / shutdown, which the engine distinguishes and re-queues/stops.
	_, reason, err := captureRunSession(ctx, s, input, emitWrap)
	return reason, tsx.Writes(), err
}
