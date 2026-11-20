package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/llm"
	acperm "github.com/Autumn-27/norma/permission"
	"github.com/Autumn-27/norma/transcript"
)

// goalsDefaultTmpl is the built-in EDITABLE body (section [A]) of the goals-decomposer
// prompt, seeded into agent_prompts. No template vars are used today.
const goalsDefaultTmpl = `You are the penetration-testing goal decomposer. Identify the **final outcomes to achieve** from user input, not attack steps.

**First (before decomposing goals): extract operation constraints**
Identify explicit operator rules about **permitted and prohibited operations** in the task objective/description and register them with set_constraints (skip extraction if neither text contains operation constraints):
- type=deny: prohibited operations (for example, no port scanning, no production writes/deletes, no brute force, or do not touch a particular subdomain).
- type=allow: explicitly permitted/limited operation scope (for example, passive reconnaissance only, or only a specified domain).
- Constraints are neither goals nor attack steps: they define operational boundaries.
- **Constraints must be self-contained and name concrete targets**: replace references such as current target/port/IP/domain/this site with **specific values** from the task objective/description. Constraints are injected separately into execution prompts, where contextual references are ambiguous.
  Example: for https://abc.example.net, write only test abc.example.net, not only test the current target; write only test target port 443, do not scan other ports, not only test the current port. If the text refers to the current target and its address is explicit, insert that address.
- **Register only constraints explicitly stated or emphasized in the objective/description; never invent them**. When uncertain about type, use deny (more conservative).
- If there are no operation constraints in the objective/description, **do not** call set_constraints.
After registering constraints (if any), decompose goals below.

**Goal = a final deliverable/verifiable outcome**

**Not goals (must not be listed as subgoals)**:
- Information gathering, reconnaissance, endpoint scanning
- Vulnerability analysis and verification processes
- Attack steps or exploitation techniques
- Result verification steps

**Decomposition principles**:
- One final user objective → one goal.
- Multiple **mutually independent** final deliverables → list them separately.
- Specify vulnclass when a clear vulnerability class applies; leave it empty for information-gathering/business-logic goals.
- Never invent goals the user did not mention.

Submit results with set_goals.`

// goalsScopeTail is the code-owned tail appended after the editable goals body
// WHEN an asset store + task context are available. It teaches the decomposer to
// also lift the explicit asset scope out of the goal/description and register it
// via add_task_scope. Kept in code (not the DB-editable body) so it always applies
// on released DBs and can't be edited away — same pattern as the trafficTool tail.
const goalsScopeTail = `

**Additional responsibility: register test asset scope**
Besides decomposing goals, identify the **explicit test asset scope** in the task objective/description and register it with add_task_scope (the task's authorization boundary and denominator for asset test coverage). **Minimum scope: register only the precise target explicitly named by the user; never expand it yourself.**
- URL or address containing a hostname (e.g. https://xxx.example.com/path, app.example.com) → use its **full hostname**, kind=subdomain, value=full hostname.
  Example: https://a1b2c3.lab.example.net/path → kind=subdomain, value=a1b2c3.lab.example.net (**not** example.net).
  **Never** shorten a subdomain hostname to its root domain: registering all of example.com for xxx.example.com exceeds the user's target and violates minimum scope.
- Only when the user gives a **bare root domain with no subdomain** (e.g. example.com), or explicitly says the entire site/all subdomains/whole domain, use kind=root_domain, value=example.com.
- Plain IP or network → kind=ip / cidr, value=IP or CIDR.
- **Do not** register company scope (company): the task is new and that company usually does not yet exist in the asset system. Leave company-level scope to later planning.
Other rules:
- Register only scope **explicitly stated** in the objective/description; never invent or infer unmentioned domains/IPs.
- Briefly cite the source statement in reason for auditing.
- If neither text specifies asset scope, **do not** call add_task_scope.
Register scope first with add_task_scope (if any), then submit goals with set_goals.`

// GoalSpec is one decomposed objective.
type GoalSpec struct {
	Text      string `json:"text"`
	VulnClass string `json:"vulnclass,omitempty"`
}

// DecomposeGoals asks the LLM to break a pentest task goal into discrete,
// independently-verifiable objectives (each becomes a goal node). Returns nil if
// no provider is configured or the call yields nothing — the caller then falls
// back to a rule-based split so goal nodes always exist.
//
// prov is supplied by the caller (rather than built here from a Config) so goal
// decomposition rides the SAME provider instance as the rest of the engine — it
// shares the rate limiter, gets recorded by llmrec, and participates in LLM
// failover instead of quietly bypassing all three.
//
// desc is the task's free-text description (background: target scope, flag count, rules of engagement, etc.).
// It is fed alongside the goal so the decomposer no longer splits blind — the
// prompt still forbids inventing anything the two texts don't state.
//
// emit, when non-nil, receives every LLM step (thinking/tool_use/result) with
// Worker="planner" so the round-0 goal-decomposition activity is visible in the UI.
//
// as + taskID, when non-nil/positive, wire the add_task_scope tool so the
// decomposer can register the explicit asset scope it extracts from the goal.
//
// ts is the task's exploration store: set_goals writes the decomposed goal nodes
// straight into it (the same managed tool the main agent uses to add goals at
// runtime). The returned specs are read back from the store so callers can emit
// per-goal activity and detect the "LLM produced nothing" case for their fallback.
func DecomposeGoals(ctx context.Context, prov llm.Provider, dataDir, goalText, desc string, as *db.AssetStore, ts *db.ExplorationStore, taskID int64, emit func(db.Activity)) []GoalSpec {
	if prov == nil {
		return nil
	}
	return DecomposeGoalsWithProvider(ctx, prov, dataDir, goalText, desc, as, ts, taskID, false, 0, emit)
}

// DecomposeGoalsWithProvider is the task-runtime variant used when a task has an
// ordered provider chain. It preserves the same tools and write behavior while
// letting the caller own provider selection/failover. maxTokens is the profile's
// per-reply output cap (0 = send none).
func DecomposeGoalsWithProvider(ctx context.Context, prov llm.Provider, dataDir, goalText, desc string, as *db.AssetStore, ts *db.ExplorationStore, taskID int64, nonStreaming bool, maxTokens int, emit func(db.Activity)) []GoalSpec {
	specs, _ := DecomposeGoalsWithProviderChecked(ctx, prov, dataDir, goalText, desc, as, ts, taskID, nonStreaming, maxTokens, emit)
	return specs
}

// DecomposeGoalsWithProviderChecked preserves legacy best-effort decomposition,
// but propagates native admission/provider errors so the scheduler cannot replace
// a rejected native run with the rule-based fallback.
func DecomposeGoalsWithProviderChecked(ctx context.Context, prov llm.Provider, dataDir, goalText, desc string, as *db.AssetStore, ts *db.ExplorationStore, taskID int64, nonStreaming bool, maxTokens int, emit func(db.Activity)) ([]GoalSpec, error) {
	if prov == nil {
		return nil, nil
	}
	ctx, native, admissionErr := prepareNativeTaskRun(ctx, prov, "goals", RunInfo{TaskID: taskID, ExplorationID: explorationID(ts)}, ts, nil)
	if admissionErr != nil {
		return nil, admissionErr
	}
	// Goal decomposition is a one-shot call without a transcript store, so agentcore does not attach
	// a session id to ctx (only attached when a writer exists; see agentcore.Prompt). Gateways using
	// session-id headers for prompt caching/sticky routing (opencode zen returns 400 without x-opencode-session,
	// MissingSessionID) read that context value. Without it chat works but decomposition returns 400.
	// Attach a stable id explicitly: decomposition requests in the same exploration share it for caching,
	// without colliding with planner/worker names, allowing correct attribution by llmrec.parseSession.
	if ts != nil {
		ctx = transcript.WithSessionID(ctx, fmt.Sprintf("exp%d-goals", ts.ID()))
	}
	// worker="goals" tags the goal nodes' provenance; ts/taskID let set_goals link
	// each goal under the task root. This is the catalog's real set_goals tool, so a
	// web-edited description/schema on it applies here too.
	tsx := &ToolSet{as: as, ts: ts, taskID: taskID, worker: "goals"}
	// Description rides in the user message (same channel as the goal), NOT via the
	// {{.EngagementDescription}} template var — else a prompt that references the var
	// would inject the description twice. System prompt stays pure static instructions.
	sys := renderSystem("goals", goalsDefaultTmpl, GoalsVars{DataDir: dataDir, Now: nowStr()})
	// set_constraints is always available (independent of asset store). The body already instructs extraction
	// of operational constraints before goal decomposition (editable in agent UI); just wire the tool here.
	tools := tsx.NativeRoleBase("goals")
	// Wire add_task_scope only when we have a real asset store + task to write to.
	// The scope-extraction tail is appended in lockstep so the prompt never asks for
	// a tool that isn't present.
	if as != nil && taskID > 0 && native == nil {
		tools = append(tools, tsx.addTaskScope())
		sys += goalsScopeTail
	}
	userMsg := "Task objective:\n" + goalText
	if d := strings.TrimSpace(desc); d != "" {
		userMsg += "\n\nTask description (background that may include target scope/flag count/engagement instructions; reference only, do not invent unmentioned details):\n" + d
	}
	// Use captureRun so every LLM step is emitted as an activity record (visible in
	// the plan tab under the round-0 marker). Falls back gracefully when emit is nil.
	captureEmit := func(r db.Activity) {
		if emit != nil {
			r.Worker = "planner"
			emit(r)
		}
	}
	if native != nil {
		var cleanup func()
		tools, _, cleanup = AugmentTools(ctx, "goals", tools)
		defer cleanup()
	}
	opts := agentcore.Options{
		Provider:               prov,
		SystemPrompt:           []string{sys},
		Tools:                  tools,
		PermissionMode:         acperm.ModeBypass,
		DisableBackgroundTasks: true,
		// The three steps (extract constraints → register scope → decompose goals) each need a tool call; allow enough turns for set_goals before wrap-up.
		MaxTurns:     8,
		NonStreaming: nonStreaming, // Use Provider.Complete when the profile selects non-streaming.
		MaxTokens:    maxTokens,    // 0 omits the cap and uses the server default.
	}
	if native != nil {
		var err error
		ctx, err = finishNativeTaskOptions(ctx, native, &opts)
		if err != nil {
			return nil, err
		}
	}
	_, _, runErr := captureRun(ctx, opts, userMsg, captureEmit)
	if native != nil && runErr != nil {
		return nil, runErr
	}
	// set_goals persisted the goals directly; read them back so the caller sees what
	// was written (empty slice ⇒ the LLM produced nothing ⇒ caller falls back).
	if ts == nil {
		return nil, nil
	}
	nodes, readErr := ts.ListByKind(db.KindGoal, 10000)
	if native != nil && (readErr != nil || len(nodes) == 0) {
		return nil, nativeErr
	}
	var out []GoalSpec
	for _, n := range nodes {
		var p struct {
			Text      string `json:"text"`
			VulnClass string `json:"vulnclass"`
		}
		_ = json.Unmarshal(n.Payload, &p)
		if strings.TrimSpace(p.Text) != "" {
			out = append(out, GoalSpec{Text: p.Text, VulnClass: p.VulnClass})
		}
	}
	return out, nil
}
