package agent

import (
	"context"
	"fmt"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/intercept"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/permission"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// MainAgent is the thin human-interface orchestrator (docs §4.2 / §7). The human
// chats with it; it observes (read tools), and steers by injecting hints
// (→planner) or direct high-priority intents (→frontier). It does NOT run the
// autonomous intent-generation loop (that is the planner's job).
type MainAgent struct {
	findingRecorder FindingRecorder
	prov            llm.Provider
	model           string
	tx              *transcript.Store                      // raw LLM conversation persistence (nil = off)
	window          int                                    // context window in tokens (for compaction)
	windowFn        func() int                             // optional dynamic task-chain minimum
	maxTurns        int                                    // max agent turns per run (0 = unlimited)
	proxyAddr       string                                 // recording proxy for WebFetch (empty = direct)
	proxyCACert     string                                 // recording proxy's CA cert path (HTTPS verify)
	webSearch       WebSearchOpts                          // web_search tool backend selection (off by default)
	workDir         string                                 // shared work dir (surfaced in prompt as artifact-output target)
	steerWork       func(intentID int64, msg string) error // engine callback: steer a running work (nil = off)
	nonStreamingFn  func() bool                            // resolver: use non-streaming (Complete) path? (nil = streaming)
	noaEnabledFn    func() bool                            // resolver: use experimental noa compaction? (nil = off)
	maxTokensFn     func() int                             // resolver: per-reply output cap (nil/0 = send no cap)
}

// SetNoaEnabled wires a resolver deciding whether runs use the experimental noa
// context-compression mechanism. nil/unset = off (built-in compaction). Read per
// run so the settings toggle takes effect without rebuilding the agent.
func (m *MainAgent) SetNoaEnabled(fn func() bool) { m.noaEnabledFn = fn }

// SetNonStreaming wires a resolver deciding whether runs use the non-streaming
// model path (true = non-streaming). nil/unset = streaming (default).
func (m *MainAgent) SetNonStreaming(fn func() bool) { m.nonStreamingFn = fn }

func (m *MainAgent) nonStreaming() bool { return m.nonStreamingFn != nil && m.nonStreamingFn() }

// SetMaxTokens wires a resolver for the per-reply output cap. nil/unset or 0 =
// send no cap and let the endpoint decide. Read per run, like nonStreaming.
func (m *MainAgent) SetMaxTokens(fn func() int) { m.maxTokensFn = fn }

func (m *MainAgent) maxTokens() int {
	if m.maxTokensFn == nil {
		return 0
	}
	return m.maxTokensFn()
}

func NewMainAgent(prov llm.Provider, model, workDir string, tx *transcript.Store, window, maxTurns int) *MainAgent {
	return &MainAgent{prov: prov, model: model, workDir: workDir, tx: tx, window: window, maxTurns: maxTurns}
}

func (m *MainAgent) SetCompactionWindowResolver(fn func() int) { m.windowFn = fn }

func (m *MainAgent) compactionWindow() int {
	if m.windowFn != nil {
		return m.windowFn()
	}
	return m.window
}

// SetProxy points the main agent's WebFetch at the recording proxy plus the CA
// cert it trusts to verify HTTPS through it (empty addr = direct).
func (m *MainAgent) SetProxy(addr, caCert string) { m.proxyAddr, m.proxyCACert = addr, caCert }

// SetWebSearch selects the web_search backend for the main agent (off by default).
func (m *MainAgent) SetWebSearch(o WebSearchOpts) { m.webSearch = o }

// SetSteerWork wires the engine callback that lets the main agent's steer_work
// tool inject a mid-run course-correction into a running work (nil = tool off).
func (m *MainAgent) SetSteerWork(fn func(intentID int64, msg string) error) { m.steerWork = fn }

// mainAgentDefaultTmpl is the built-in EDITABLE body (section [A]) of the main agent
// prompt, seeded into agent_prompts. Goal is a {{.Goal}} template var; the artifact
// output policy tail is code-owned (artifactSpec), appended after rendering.
const mainAgentDefaultTmpl = `You are the main agent of an authorized penetration-testing system, serving as the human operator's interface. Do not explore targets yourself or autonomously generate a continuous stream of intents (that is the planner's job). Your responsibilities:

1. Observe: use graph_overview / list_findings / list_facts / list_assets / get_worker_output to answer questions about current progress.
2. Steer (translate human intent into system actions):
   - Change direction/emphasize a vulnerability class/focus an area → add_hint (read by the planner on its next round).
   - Test a specific target immediately → add_intent with high priority (priority 8-10). The system automatically revives completed tasks for a worker to execute this intent, then returns to completed.
     **If all task goals are already achieved** (all goals in graph_overview are met), first assess whether the intent implies a new final outcome. If so, restate the inferred goal in one sentence and **ask whether to register it as a formal goal**. If yes, register with set_goals (normal autonomous planning resumes). If no/only a temporary probe is wanted, submit only this intent with add_intent: after worker execution, the task returns to completed without autonomous continuation. For an obviously one-off check without a new goal, add_intent directly without asking every time.
   - Correct a running work in real time (stop X, focus Y) → steer_work, preserving progress without interruption and taking effect before the worker's next action; first inspect get_worker_output. If the entire direction is wrong, issue a new intent with add_intent instead.
   - Add a new final objective → set_goals. The system records it in the task graph and **automatically revives completed/paused tasks to running** so the planner can reassess achievement; no manual resume is needed.
   - Add/change test constraints (allow/prohibit operations such as only this port, no brute force, passive reconnaissance only) → set_constraints (type=allow / type=deny). Constraints are injected into planner/worker prompts on the next planning round to bound exploration; they can also be managed in the overview's constraint management.
3. Reply concisely in plain language, explaining what you did.

Current task objective: {{.Goal}}

Do not fabricate findings. Answer only from actual tool-returned data.`

func mainAgentSystem(goal, dataDir, workDir string) string {
	body := renderSystem("mainagent", mainAgentDefaultTmpl, MainVars{Goal: goal, DataDir: dataDir, Now: nowStr()})
	return body + artifactSpec(workDir)
}

// Chat handles one human message and returns the assistant reply. emit, if
// non-nil, receives each execution step (thinking / tool_use / tool_result /
// text / result) so the main-agent session shows its work — exactly like the
// worker/planner sessions — not just the final answer.
func (m *MainAgent) Chat(ctx context.Context, taskID int64, mainSeg int, as *db.AssetStore, ts *db.ExplorationStore, goal, message string, emit func(db.Activity), notify, resume func(), notifyGoal, notifyHint func([]string)) (string, error) {
	ctx, native, admissionErr := prepareNativeTaskRun(ctx, m.prov, "mainagent", RunInfo{TaskID: taskID, ExplorationID: explorationID(ts)}, ts, nil)
	if admissionErr != nil {
		return "", admissionErr
	}
	if native != nil && mainSeg != 0 {
		return "", nativeErr
	} // segmented native main sessions require a separate explicit permit
	if native != nil {
		as = nil
	} // global asset access is outside this native phase
	tsx := NewToolSet(ts, "human")
	tsx.SetFindingRecorder(m.findingRecorder)
	if as != nil {
		tsx.SetAssetStore(as, as.Companies())
	}
	tsx.SetTaskID(taskID)
	tsx.SetCoverageEnabled(as == nil || as.CoverageEnabled(taskID))
	tsx.SetNotify(notify)         // Generic debounced wake-up for writes without a dedicated callback.
	tsx.SetResumeTask(resume)     // set_goals adds goals → return completed/paused tasks to running.
	tsx.SetNotifyGoal(notifyGoal) // set_goals adds goals → record one human-added-goals planner trigger.
	tsx.SetNotifyHint(notifyHint) // add_hint adds hints → record one human-added-N-strategic-hints planner trigger.
	tsx.steerWork = m.steerWork   // enable steer_work tool (nil = unavailable)
	// Domain tools + SDK defaults (Read/Write/Edit/MultiEdit/LS/Glob/Grep/Bash).
	// When asset coverage is disabled, remove add_task_scope/list_untested_assets from the prompt.
	base := append(tsx.DropCoverageTools(tsx.MainAgentTools()), actool.DefaultTools()...)
	if nativeRoleContext(ctx) {
		base = tsx.NativeRoleBase("mainagent")
	}
	ctx = WithRunInfo(ctx, RunInfo{TaskID: taskID, ExplorationID: explorationID(ts)})
	tools, def, cleanup := AugmentTools(ctx, "mainagent", base)
	defer cleanup()
	// Create this task's working directory <workDir>/tasks/<taskID> first.
	mainDir := ensureRunDir(m.workDir, taskID, 0)
	ctx = intercept.WithReviewWorkingDirectory(ctx, mainDir)
	system, boundary := deferredSystem(mainAgentSystem(goal, m.workDir, mainDir), def)
	opts := agentcore.Options{
		Provider:        m.prov,
		SystemPrompt:    system,
		DynamicBoundary: boundary,
		Tools:           tools,
		DeferredTools:   def.Deferred,
		UnlockSet:       def.Unlock,
		PermissionMode:  permission.ModeBypass,
		EnableWebFetch:  true, // Use recording proxy; load its CA to verify MITM-reissued HTTPS certificates.
		WebFetchProxy:   m.proxyAddr,
		WebFetchCACert:  m.proxyCACert,
		// Optional web search: ddgs needs no key; brave-free needs BraveKey; tavily needs TavilyKey.
		// WebSearchProxy is separate egress (http/https/socks5), unrelated to traffic-recording MITM proxy; empty means direct.
		EnableWebSearch:       m.webSearch.Enabled,
		WebSearchBackend:      m.webSearch.Backend,
		BraveSearchAPIKey:     m.webSearch.BraveKey,
		TavilySearchAPIKey:    m.webSearch.TavilyKey,
		DeepSeekSearchBaseURL: m.webSearch.DeepSeekBaseURL,
		DeepSeekSearchAPIKey:  m.webSearch.DeepSeekAPIKey,
		DeepSeekSearchModel:   m.webSearch.DeepSeekModel,
		WebSearchProxy:        m.webSearch.Proxy,
		BashEnv:               proxyEnv(m.proxyAddr, m.proxyCACert), // Bash subprocesses use the proxy and trust its CA by default.
		WorkingDir:            mainDir,                              // Task working directory <workDir>/tasks/<taskID>.
		ToolOutputDir:         cmdOutDir(mainDir),
		MaxTurns:              m.maxTurns,                             // 0 = unlimited (configurable in agent management)
		Compaction:            compactionConfig(m.compactionWindow()), // long chats stay within the window
		Todos:                 actool.NewTodoStore(),                  // Session-local temporary planning todos (TodoWrite); discarded on exit.
		// Step budget → SDK wrap-up emits a user-facing progress summary. Prompt/turns are editable (default 10 turns).
		Settlement:   wrapupSettlement("mainagent", nil),
		NonStreaming: m.nonStreaming(), // Use Provider.Complete when the profile selects non-streaming.
		MaxTokens:    m.maxTokens(),    // 0 omits the cap and uses the server default.
	}
	if m.tx != nil { // persist raw human↔AI conversation; one accumulating file per segment
		opts.Transcript = m.tx
		// Segment 0 keeps the legacy "exp%d-main" name so existing transcripts still
		// load; each new session (seg>=1) gets its own file for a clean context.
		opts.SessionID = fmt.Sprintf("exp%d-main", ts.ID())
		if mainSeg > 0 {
			opts.SessionID = fmt.Sprintf("exp%d-main-s%d", ts.ID(), mainSeg)
		}
	}
	// Experimental: noa takes over context compression when enabled; persistent archives live under <workDir>/noa/<SessionID>.
	// Session ids follow the same segment-aware rules as transcripts, aligning archival and recovery.
	noaSession := fmt.Sprintf("exp%d-main", ts.ID())
	if mainSeg > 0 {
		noaSession = fmt.Sprintf("exp%d-main-s%d", ts.ID(), mainSeg)
	}
	if native == nil {
		enableNoa(&opts, m.noaEnabledFn, m.workDir, noaSession, noaWarn(noaSession))
		ctx = attachSideCapture(ctx, &opts)
	} else {
		var err error
		ctx, err = finishNativeTaskOptions(ctx, native, &opts)
		if err != nil {
			return "", err
		}
	}
	s := agentcore.NewSession(opts)
	defer s.Close()
	// reload the prior conversation from the transcript so the agent has context
	// across turns (each Chat is a fresh session; without this it can't see earlier
	// messages). First turn: no file yet → Resume loads nothing and proceeds.
	if m.tx != nil {
		_ = s.Resume(opts.SessionID)
	}
	// C2: this session is fresh each turn; re-unlock skill-gated MCPs from prior
	// Skill() calls in the reloaded history so revealed tools stay callable.
	seedUnlockFromHistory(s.Messages(), def.UnlockSkill)
	text, _, err := captureRunSession(ctx, s, message, func(r db.Activity) {
		if emit != nil {
			r.Worker = "mainagent"
			emit(r)
		}
	})
	return text, err
}
