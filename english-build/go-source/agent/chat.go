package agent

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/guard"
	"github.com/Autumn-27/artex/intercept"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/permission"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// ChatAgent is the generic, task-independent conversational runner behind the chat
// page. It generalizes MainAgent.Chat: any agent (built-in OR a custom one, by
// key) can be chatted with, multi-turn history resumed from the transcript. It is
// a PURE ASSISTANT — base tools are the SDK DefaultTools (Bash/Read/Write/Edit/
// LS/Glob/Grep) plus whatever skills/MCP the key is made visible; NO pentest
// graph/task context is injected (that stays exclusive to MainAgent).
type ChatAgent struct {
	prov                llm.Provider
	model               string
	workDir             string
	tx                  *transcript.Store
	window              int
	proxyAddr           string
	proxyCACert         string
	webSearch           WebSearchOpts
	guard               *guard.Guard // optional; nil disables intercept hooks for chat
	nonStreamingFn      func() bool  // resolver: use non-streaming (Complete) path? (nil = streaming)
	noaEnabledFn        func() bool  // resolver: use experimental noa compaction? (nil = off)
	maxTokensFn         func() int   // resolver: per-reply output cap (nil/0 = send no cap)
	nativeReporterTools []actool.CoreTool
	nativeLab           bool
}

func NewChatAgent(prov llm.Provider, model, workDir string, tx *transcript.Store, window int) *ChatAgent {
	return &ChatAgent{prov: prov, model: model, workDir: workDir, tx: tx, window: window}
}

// SetNonStreaming wires a resolver deciding whether chat runs use the
// non-streaming model path (true = non-streaming). nil/unset = streaming.
func (c *ChatAgent) SetNonStreaming(fn func() bool) { c.nonStreamingFn = fn }

func (c *ChatAgent) nonStreaming() bool { return c.nonStreamingFn != nil && c.nonStreamingFn() }

// SetNoaEnabled wires a resolver deciding whether chat runs use the experimental
// noa context-compression mechanism. nil/unset = off (built-in compaction). Read
// per run so the settings toggle takes effect without rebuilding the agent.
func (c *ChatAgent) SetNoaEnabled(fn func() bool) { c.noaEnabledFn = fn }

// SetMaxTokens wires a resolver for the per-reply output cap. nil/unset or 0 =
// send no cap and let the endpoint decide. Read per run, like nonStreaming.
func (c *ChatAgent) SetMaxTokens(fn func() int) { c.maxTokensFn = fn }

func (c *ChatAgent) maxTokens() int {
	if c.maxTokensFn == nil {
		return 0
	}
	return c.maxTokensFn()
}

// SetProxy points the chat agent's WebFetch/Bash at the recording proxy plus the
// CA cert it trusts (empty addr = direct). Kept for parity with the other agents.
func (c *ChatAgent) SetProxy(addr, caCert string) { c.proxyAddr, c.proxyCACert = addr, caCert }

// SetWebSearch selects the web_search backend for the chat agent (off by default).
func (c *ChatAgent) SetWebSearch(o WebSearchOpts) { c.webSearch = o }

// SetGuard attaches a guard (with user-configured intercept rules) to this chat
// agent. Must be called before Chat; safe to call multiple times.
func (c *ChatAgent) SetGuard(g *guard.Guard)   { c.guard = g }
func (c *ChatAgent) SetNativeLab(enabled bool) { c.nativeLab = enabled }

// SetNativeReporterTools is host-only and supplies explicit domain/evidence tools.
func (c *ChatAgent) SetNativeReporterTools(tools []actool.CoreTool) {
	c.nativeReporterTools = append([]actool.CoreTool(nil), tools...)
}

// chatWorkDirSpec returns a working-directory notice appended to every chat
// agent's system prompt. Mirrors artifactSpec but without pentest-specific
// wording ("payload", "capture response bodies") that would be odd in a general assistant.
func chatWorkDirSpec(workDir string) string {
	return "\n\n**File output policy**: When writing files, always use working directory " + workDir + " (the default CWD; relative paths resolve here, or use this absolute path). Do not write to /tmp or other absolute paths."
}

// chatSystem renders the DB-managed prompt body for agentKey. Custom agents have
// no per-key in-code default, so DefaultAssistantPrompt is the render fallback.
func chatSystem(agentKey, dataDir, workDir string) string {
	return renderSystem(agentKey, DefaultAssistantPrompt, chatVars{DataDir: dataDir, Now: nowStr()}) + chatWorkDirSpec(workDir)
}

// chatVars carries the runtime variables a custom agent's prompt may reference.
// DataDir (server data root) + Now (server wall-clock, refreshed each turn) are the
// universal ones; any other {{.X}} fails to render and falls back to
// DefaultAssistantPrompt.
type chatVars struct{ DataDir, Now string }

// Chat runs ONE turn of a conversation with the agent identified by agentKey,
// resuming prior history keyed by sessionID. maxTurns is the per-turn agent step
// budget (0 = unlimited). maxDuration is the wall-clock run budget per turn
// (0 = unlimited); the timer resets each time Chat is called, so a new user
// message always starts a fresh countdown. webSearch gates network search for
// THIS agent (the global backend/key still come from the chat agent's config,
// but each agent decides on/off). emit receives each execution step (thinking /
// tool_use / tool_result / text / result), tagged with the agent key as the
// worker lane.
func (c *ChatAgent) Chat(ctx context.Context, agentKey, sessionID, message string, maxTurns int, maxDuration time.Duration, webSearch bool, emit func(db.Activity)) (string, error) {
	if !HasNativeReporterFinding(ctx) && (len(c.nativeReporterTools) > 0 || (agentKey == "reporter" && c.nativeLab)) {
		return "", nativeErr
	}
	var native *nativeRPC
	if event, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority); ok {
		if agentKey != "reporter" || sessionID != fmt.Sprintf("conv-%d", event.conversation) || event.validate(ctx) != nil {
			return "", nativeErr
		}
		var err error
		ctx, native, err = prepareNativeTaskRun(ctx, c.prov, "reporter", RunInfo{TaskID: event.task, ExplorationID: event.exploration, IntentID: event.intent}, event.pg.Exploration(event.exploration), nil)
		if err != nil || native == nil {
			return "", nativeErr
		}
	} else if _, ok := c.prov.(*nativeRPC); ok && !c.nativeLab {
		return "", nativeErr
	}
	if c.nativeLab && native == nil {
		ctx = context.WithValue(ctx, nativeChatContextKey{}, true)
	}
	// gate the global web-search opts by this agent's own flag.
	ws := c.webSearch
	if !webSearch {
		ws.Enabled = false
	}

	// Per-session working directory: <workDir>/sessions/<sessionID>/
	// Isolates file writes across conversations, mirroring how workers use i<intentID>/.
	sessionWorkDir := filepath.Join(c.workDir, "sessions", sessionID)
	mode := os.FileMode(0o755)
	if c.nativeLab {
		mode = 0o700
	}
	if err := os.MkdirAll(sessionWorkDir, mode); err != nil {
		return "", err
	}
	ctx = intercept.WithReviewWorkingDirectory(ctx, sessionWorkDir)

	// Pure assistant: DefaultTools as the base; AugmentTools layers in the key's
	// visible skills/MCP and lets the DB tools table filter/override. DefaultTools
	// have no tools-table rows, so they always pass through.
	base := actool.DefaultTools()
	if native == nil {
		ctx = WithRunInfo(ctx, RunInfo{SessionID: sessionID})
	} else {
		base = c.nativeReporterTools
	}
	var tools []actool.CoreTool
	var def DeferredInfo
	cleanup := func() {}
	if c.nativeLab && native == nil {
		tools = nativeLabTools(sessionWorkDir)
	} else {
		tools, def, cleanup = AugmentTools(ctx, agentKey, base)
	}
	defer cleanup()

	system, boundary := deferredSystem(chatSystem(agentKey, c.workDir, sessionWorkDir), def)
	opts := agentcore.Options{
		Provider:        c.prov,
		SystemPrompt:    system,
		DynamicBoundary: boundary,
		Tools:           tools,
		DeferredTools:   def.Deferred,
		UnlockSet:       def.Unlock,
		PermissionMode:  permission.ModeBypass,
		EnableWebFetch:  true, // Use the recording proxy; load its CA to verify MITM-reissued HTTPS certificates.
		WebFetchProxy:   c.proxyAddr,
		WebFetchCACert:  c.proxyCACert,
		// Optional web search: ddgs needs no key; brave-free needs BraveKey; tavily needs TavilyKey.
		// WebSearchProxy is a separate egress proxy (http/https/socks5), unrelated to the traffic-recording MITM proxy; empty means direct.
		EnableWebSearch:       ws.Enabled,
		WebSearchBackend:      ws.Backend,
		BraveSearchAPIKey:     ws.BraveKey,
		TavilySearchAPIKey:    ws.TavilyKey,
		DeepSeekSearchBaseURL: ws.DeepSeekBaseURL,
		DeepSeekSearchAPIKey:  ws.DeepSeekAPIKey,
		DeepSeekSearchModel:   ws.DeepSeekModel,
		WebSearchProxy:        ws.Proxy,
		BashEnv:               proxyEnv(c.proxyAddr, c.proxyCACert), // Bash subprocesses use the proxy and trust its CA by default.
		WorkingDir:            sessionWorkDir,
		MaxTurns:              maxTurns,
		MaxDuration:           maxDuration,
		Compaction:            compactionConfig(c.window),
		Todos:                 actool.NewTodoStore(),
		// large tool output spills to cmd-output/ under the session dir.
		// Use the SDK truncation default (30000 characters in tool.Capture).
		ToolOutputDir: filepath.Join(sessionWorkDir, "cmd-output"),
		// At the step budget, SDK wrap-up emits a summary. Prompt and wrap-up turns are editable per agent key
		// (separate for custom agents; empty/0 uses the generic default of 10 turns).
		Settlement:   wrapupSettlement(agentKey, nil),
		NonStreaming: c.nonStreaming(), // Use Provider.Complete when the profile selects non-streaming.
		MaxTokens:    c.maxTokens(),    // 0 omits the cap and uses the server default.
	}
	if c.nativeLab {
		opts.EnableWebFetch = false
		opts.EnableWebSearch = false
		opts.DisableBackgroundTasks = true
		opts.Todos = nil
		opts.BashEnv = nil
		opts.Compaction = nil
		opts.Settlement = nil
		opts.NonStreaming = true
		if c.maxTokens() != 0 || !c.nonStreaming() {
			return "", nativeErr
		}
	}
	if c.guard != nil {
		opts.Hooks = c.guard.Hooks()
	}
	if c.tx != nil { // persist raw human↔AI conversation; one accumulating file per thread
		opts.Transcript = c.tx
		opts.SessionID = sessionID
	}
	// Experimental: noa takes over context compression when enabled; persistent archives live under <workDir>/noa/<SessionID>.
	if !c.nativeLab && native == nil {
		enableNoa(&opts, c.noaEnabledFn, c.workDir, "chat-"+sessionID, noaWarn("chat-"+sessionID))
	}
	if native != nil {
		var err error
		ctx, err = finishNativeTaskOptions(ctx, native, &opts)
		if err != nil {
			return "", err
		}
	} else {
		ctx = attachSideCapture(ctx, &opts)
	}
	s := agentcore.NewSession(opts)
	defer s.Close()
	// reload prior conversation so the agent has context across turns (each Chat is
	// a fresh session). First turn: no file yet → Resume loads nothing and proceeds.
	if c.tx != nil {
		_ = s.Resume(sessionID)
	}
	// re-unlock skill-gated MCPs from prior Skill() calls in the reloaded history so
	// revealed tools stay callable across the fresh session.
	seedUnlockFromHistory(s.Messages(), def.UnlockSkill)
	text, _, err := captureRunSession(ctx, s, message, func(r db.Activity) {
		if emit != nil {
			r.Worker = agentKey
			emit(r)
		}
	})
	return text, err
}
