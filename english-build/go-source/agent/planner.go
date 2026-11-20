package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/intercept"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/permission"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// Planner is the event-driven LLM planner (docs §4.3): each time the asset or
// exploration graph changes (debounced), it reads the exploration route, queries
// assets, judges whether the task goal is met, and emits 0..N exploration intents
// into the frontier. It is the sole intent generator.
type Planner struct {
	findingRecorder   FindingRecorder
	prov              llm.Provider
	model             string
	tx                *transcript.Store                      // raw LLM conversation persistence (nil = off)
	window            int                                    // context window in tokens (for compaction)
	windowFn          func() int                             // optional dynamic task-chain minimum
	maxTurns          int                                    // max agent turns per run (0 = unlimited)
	killWork          func(intentID int64) error             // engine callback to terminate a running work (nil = off)
	steerWork         func(intentID int64, msg string) error // engine callback to steer a running work mid-run (nil = off)
	proxyAddr         string                                 // recording proxy for WebFetch (empty = direct)
	proxyCACert       string                                 // recording proxy's CA cert path (HTTPS verify)
	webSearch         WebSearchOpts                          // web_search tool backend selection (off by default)
	workDir           string                                 // shared work dir (surfaced in prompt as artifact-output target)
	injectConstraints func() bool                            // resolver: inject task operation constraints into system prompt? (nil = yes)
	nonStreamingFn    func() bool                            // resolver: use non-streaming (Complete) path? (nil = streaming)
	noaEnabledFn      func() bool                            // resolver: use experimental noa compaction? (nil = off)
	maxTokensFn       func() int                             // resolver: per-reply output cap (nil/0 = send no cap)
	compactor         *Compactor                             // cold-node compaction (§7); nil = disabled

	// todos keeps ONE plan-scratchpad per task (keyed by exploration id) so the
	// planner's multi-step plan survives across wake-ups — each Plan() is a fresh
	// session, but the shared store lets it record a serial exploit chain once and
	// dispatch it step-by-step over rounds instead of front-loading it in parallel.
	todoMu sync.Mutex
	todos  map[int64]*actool.TodoStore
}

func NewPlanner(prov llm.Provider, model, workDir string, tx *transcript.Store, window, maxTurns int) *Planner {
	return &Planner{prov: prov, model: model, workDir: workDir, tx: tx, window: window, maxTurns: maxTurns, todos: map[int64]*actool.TodoStore{}}
}

func (p *Planner) SetCompactionWindowResolver(fn func() int) { p.windowFn = fn }

// SetCompactor wires the cold-node compactor (cold-digest §7). Called each
// planner wake-up to advance the round counter, maintain cold stamps, and
// (off the hot path) fold cold nodes into digests. nil = feature disabled.
func (p *Planner) SetCompactor(c *Compactor) { p.compactor = c }

// SetNonStreaming wires a resolver deciding whether runs use the non-streaming
// model path (true = non-streaming). nil/unset = streaming (default).
func (p *Planner) SetNonStreaming(fn func() bool) { p.nonStreamingFn = fn }

func (p *Planner) nonStreaming() bool { return p.nonStreamingFn != nil && p.nonStreamingFn() }

// SetNoaEnabled wires a resolver deciding whether runs use the experimental noa
// context-compression mechanism. nil/unset = off (built-in compaction). Read per
// run so the settings toggle takes effect without rebuilding the agent.
func (p *Planner) SetNoaEnabled(fn func() bool) { p.noaEnabledFn = fn }

// SetMaxTokens wires a resolver for the per-reply output cap. nil/unset or 0 =
// send no cap and let the endpoint decide. Read per run, like nonStreaming.
func (p *Planner) SetMaxTokens(fn func() int) { p.maxTokensFn = fn }

func (p *Planner) maxTokens() int {
	if p.maxTokensFn == nil {
		return 0
	}
	return p.maxTokensFn()
}

func (p *Planner) compactionWindow() int {
	if p.windowFn != nil {
		return p.windowFn()
	}
	return p.window
}

// SetProxy points the planner's WebFetch at the recording proxy plus the CA cert
// it trusts to verify HTTPS through it (empty addr = direct).
func (p *Planner) SetProxy(addr, caCert string) { p.proxyAddr, p.proxyCACert = addr, caCert }

// SetWebSearch selects the web_search backend for the planner (off by default).
func (p *Planner) SetWebSearch(o WebSearchOpts) { p.webSearch = o }

// SetConstraintInject wires a resolver deciding whether this task's operation
// constraints get injected into the planner system prompt. Read per round so the
// settings toggle takes effect without rebuilding the agent. nil = inject (default).
func (p *Planner) SetConstraintInject(fn func() bool) { p.injectConstraints = fn }

// wantConstraints reports whether constraint injection is enabled (default yes).
func (p *Planner) wantConstraints() bool { return p.injectConstraints == nil || p.injectConstraints() }

// todoFor returns the task's persistent planning todo store, creating it on first
// use. Shared across all of this task's planner wake-ups.
func (p *Planner) todoFor(expID int64) *actool.TodoStore {
	p.todoMu.Lock()
	defer p.todoMu.Unlock()
	s := p.todos[expID]
	if s == nil {
		s = actool.NewTodoStore()
		p.todos[expID] = s
	}
	return s
}

// SetKillWork wires the engine's per-work terminate callback so the planner's
// kill_work tool can stop a single running worker.
func (p *Planner) SetKillWork(fn func(intentID int64) error) { p.killWork = fn }

// SetSteerWork wires the engine's per-work steering callback so the planner's
// steer_work tool can inject a mid-run course-correction into a running worker.
func (p *Planner) SetSteerWork(fn func(intentID int64, msg string) error) { p.steerWork = fn }

// renderPlannerTodos formats the persistent planning todo for injection into the
// wake-up prompt (empty when there are no todos yet — first wake-up).
func plannerTodoPrompt(store *actool.TodoStore) string {
	if store == nil {
		return ""
	}
	return renderPlannerTodos(store.List())
}
func renderPlannerTodos(items []actool.Todo) string {
	if len(items) == 0 {
		return ""
	}
	var b strings.Builder
	b.WriteString("\n\n[Your planning todos (retained across wake-ups, written last round)]:\n")
	for _, it := range items {
		mark := map[actool.TodoStatus]string{actool.TodoPending: "☐", actool.TodoInProgress: "▶", actool.TodoCompleted: "✔"}[it.Status]
		if mark == "" {
			mark = "☐"
		}
		b.WriteString(fmt.Sprintf("  %s %s\n", mark, it.Content))
	}
	b.WriteString("Proceed from this list: dispatch only the next steps whose prerequisites are completed or whose required facts already exist. Update the list with TodoWrite, marking fact-satisfied steps completed. Do not redispatch steps already pending/in_progress.")
	return b.String()
}

// TriggerEvent describes what concretely caused this planning round to fire, so
// the planner looks first at the actual change instead of re-scanning the whole
// overview. Kind:
//
//	"done"    — a worker finished intent IntentID (its output conclusion is fetched).
// "finding" — worker reported a finding on IntentID (Detail = summary).
// "goal" — human (via main agent set_goals) added one OR MORE goals in a
// single call (Goals = newly added goal text, 1+ items; set_goals supports batches).
// "goal_deleted" — human deleted a goal in overview goal management (Detail = deleted text).
// "goal_edited" — human edited a goal in overview goal management (OldGoal→NewGoal text).
// "cancelled" — human deleted intent IntentID (Detail = deletion reason). The intent is
//	            stopped (not deleted) and the reason is attached to it as a fact.
type TriggerEvent struct {
	Kind     string
	IntentID int64
	Detail   string
	Summary  string   // Kind=="cancelled": summary captured before deletion (hard-deleted nodes cannot be queried).
	Goals    []string // Kind=="goal": goal texts added by this set_goals call (one or more).
	OldGoal  string   // Kind=="goal_edited": previous goal text.
	NewGoal  string   // Kind=="goal_edited": updated goal text.
	Hints    []string // Kind=="hint": hint texts added by this add_hint call (one or more).
}

// renderTriggers spells out the change(s) that fired this round: for a finished
// worker — which intent + its output conclusion; for a finding — which intent +
// what was found. Empty for time/heartbeat wakes. Reads the store (best-effort;
// a blank field never blocks the round).
func renderTriggers(ts *db.ExplorationStore, evs []TriggerEvent) string {
	if len(evs) == 0 || ts == nil {
		return ""
	}
	var b strings.Builder
	b.WriteString("\n\n[Actual changes triggering this round (read first, then decide whether to add directions)]:")
	for _, ev := range evs {
		switch ev.Kind {
		case "goal":
			if len(ev.Goals) == 1 {
				b.WriteString(fmt.Sprintf("\n- The human (main agent) added a goal: %s \u2014 a new unmet goal; add exploration directions if no corresponding intent exists.", ev.Goals[0]))
			} else {
				b.WriteString(fmt.Sprintf("\n- The human (main agent) added %d goals: %s \u2014 all are new unmet goals; add directions for each not yet covered by an intent.", len(ev.Goals), strings.Join(ev.Goals, "; ")))
			}
		case "hint":
			if len(ev.Hints) == 1 {
				b.WriteString(fmt.Sprintf("\n- The human (main agent) added a strategic hint: %s \u2014 attached to the exploration graph; adjust/add directions accordingly if not already covered.", ev.Hints[0]))
			} else {
				b.WriteString(fmt.Sprintf("\n- The human (main agent) added %d strategic hints: %s \u2014 all attached to the exploration graph; adjust/add directions for each accordingly.", len(ev.Hints), strings.Join(ev.Hints, "; ")))
			}
		case "goal_deleted":
			b.WriteString(fmt.Sprintf("\n- The human deleted this goal: %s \u2014 it is removed; reassess remaining goals/directions and do not dispatch intents for it.", ev.Detail))
		case "goal_edited":
			b.WriteString(fmt.Sprintf("\n- The human changed a goal from [%s] to [%s] \u2014 adjust exploration to the new goal; stop dispatching the old direction if no longer applicable.", ev.OldGoal, ev.NewGoal))
		case "finding":
			b.WriteString(fmt.Sprintf("\n- The worker for intent #%d (%s) reported a finding: %s", ev.IntentID, intentSummary(ts, ev.IntentID), ev.Detail))
		case "cancelled":
			// Prefer Summary captured at deletion; hard-deleted nodes no longer exist for intentSummary.
			sm := ev.Summary
			if sm == "" {
				sm = intentSummary(ts, ev.IntentID)
			}
			b.WriteString(fmt.Sprintf("\n- The user deleted intent #%d. Intent: %s; deletion reason: %s. This intent is deleted and will no longer execute; replan accordingly.", ev.IntentID, sm, ev.Detail))
		default: // "done"
			b.WriteString(fmt.Sprintf("\n- The worker for intent #%d (%s) finished. Conclusion: %s", ev.IntentID, intentSummary(ts, ev.IntentID), workerOutput(ts, ev.IntentID)))
			if fids := factIDsYielded(ts, ev.IntentID); fids != "" {
				b.WriteString(fmt.Sprintf("; new fact ids produced by this intent: %s ", fids))
			}
		}
	}
	b.WriteString("\n(Use node_detail / get_worker_output / list_findings for complete detail.)")
	return b.String()
}

// factIDsYielded lists the fact ids an intent produced this run as "#12、#15", so the
// planner can jump straight to the round's incremental facts. Empty (best-effort) when
// the intent yielded no facts or the lookup fails.
func factIDsYielded(ts *db.ExplorationStore, id int64) string {
	ids, err := ts.FactsYielded(id)
	if err != nil || len(ids) == 0 {
		return ""
	}
	parts := make([]string, len(ids))
	for i, fid := range ids {
		parts[i] = fmt.Sprintf("#%d", fid)
	}
	return strings.Join(parts, "、")
}

// intentSummary reads an intent node's one-line summary (best-effort, "?" on miss).
func intentSummary(ts *db.ExplorationStore, id int64) string {
	n, err := ts.GetNode(id)
	if err != nil || n == nil {
		return "?"
	}
	var p map[string]any
	if json.Unmarshal(n.Payload, &p) == nil {
		if s, ok := p["summary"].(string); ok && s != "" {
			return s
		}
	}
	return "?"
}

// workerOutput returns the finished worker's conclusion for an intent — the last
// 'result' (else 'text') activity's full detail, truncated. Same source get_worker_output uses.
func workerOutput(ts *db.ExplorationStore, id int64) string {
	acts, _, err := ts.ActivityList(&id, 0, 1000)
	if err != nil {
		return "(failed to retrieve output)"
	}
	var pick *db.Activity
	for i := range acts {
		if acts[i].Kind == "result" {
			pick = &acts[i]
		} else if acts[i].Kind == "text" && pick == nil {
			pick = &acts[i]
		}
	}
	if pick == nil {
		return "(this work has no output record yet)"
	}
	out, _ := ts.ActivityDetail(pick.ID)
	if out == "" {
		out = pick.Summary
	}
	return truncOutput(out, 800)
}

// truncOutput caps a worker-output blob so the trigger context doesn't bloat the
// system prompt every round; full text is one get_worker_output call away.
func truncOutput(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n]) + " ... (truncated; see get_worker_output for full content)"
}

// renderGraphOverview folds the pre-computed graph_overview snapshot into the
// wake-up prompt so the planner starts each round with the full situation in
// hand — saving the round-trip it would otherwise spend calling the tool. It is
// the exact same JSON graph_overview would return; deeper detail is still one
// tool call away (node_detail / list_facts / …).
func renderGraphOverview(data map[string]any) string {
	b, err := json.Marshal(data)
	if err != nil {
		return "" // fall back to the model calling graph_overview itself
	}
	return "\n\n[This round's situation (prefetched graph_overview, identical to calling that tool; retrieve detail with node_detail/list_facts as needed)]:\n" + string(b)
}

// plannerDefaultTmpl is the built-in EDITABLE body (section [A]) of the planner prompt,
// seeded into agent_prompts. Goal is a {{.Goal}} template var; the artifact output rules
// tail is code-owned (artifactSpec) and appended by plannerSystem after rendering.
const plannerDefaultTmpl = `You are the planner of an authorized penetration-testing system on a cybersecurity platform, awakened frequently whenever the graph changes. Your job: read the situation → assess goals → add exploration intents **only for genuinely new, uncovered directions**. You plan, not execute: this round's outputs must be **generating/describing intents** or **assessing goals**, never doing the work during planning.

Task objective: {{.Goal}}

**How many intents to produce this round (decide this first)**:
- **Hard minimum (highest priority)**: if **the objective is unmet** and **there are no open or running intents** (frontier_open=0 and running_intents is empty), you **must** produce at least one intent advancing the objective this round. With no active work or queued direction, zero intents stalls the task. Even if known directions only appear in recent_done, open a new direction or resume one according to the done/exhausted/blocked rules below.
- Apart from that minimum, **zero intents is valid, but requires a real reason**, not a default assumption that fewer is safer: ① **Already covered**: all directions you identify are handled by open/running intents (rewording existing intents is a serious error). ② **Waiting on dependencies**: the next step needs output from currently running work that has not arrived. Dispatching downstream work now would cause idle retries without prerequisites; wait for a graph update on the next wake-up.
- Conversely, dispatch genuinely **uncovered directions independent of running work**, or untested in-scope surfaces while the objective remains unmet. Do not make zero intents a lazy default.

**Decision process on each wake-up**:

1. **The complete situation is attached below** (the graph_overview result; do not call it again): task (original title + objective/root node), asset counts, goals + states, open/running/recent_done intents, sites_without_endpoints (sites without endpoints, suggesting surfaces to explore), facts (exploration fact count, distinct from findings), recent_facts ({id,summary,confidence?}).
   - **Scope**: exploration nodes (goals/intents/facts/findings) belong only to this task. **The asset graph is globally shared** across tasks: asset counts are global within scope, not exclusive to this task. Ignore unrelated assets.
   - **Lineage**: each intent includes parents (upstream facts/intents) and yields (downstream facts/findings), and each recent_facts item has from_intent. Use these to understand which direction produced a fact and whether facts combine into a new direction.
   - **Negative/uncertain observations** (e.g. closed port/not injectable in recent_facts) are worker observations, not final judgments. Before accepting one, read its evidence with node_detail(id). Treat a direction as provisionally blocked only when evidence is solid, confidence=observed, and approaches have been exhausted. Missing evidence, one superficial probe, or confidence=inferred means **not yet established**. If in scope and not covered by another intent, default to a verification intent to confirm or falsify it. **At most one recheck per negative direction**: if still negative with reasonable evidence, respect it and stop dispatching it.
   - **Retrieve detail only when needed**: list_facts (paginated, newest first, default 20; q filter, before cursor, total/has_more), list_findings (all vulnerabilities), node_detail(id) (full evidence/detail; lists/recent_facts only contain summaries), list_assets (pull: q search, type/company_id/task_id filters, pagination, or id/ids lookup), asset_neighbors. Assets are shared globally; do not fetch everything by default.

2. **Assess goals (core responsibility)**: goals already contains objectives and states. For an unmet goal proven by a finding/fact, call prove_goal(goal_id, evidence_id, reason) to mark met. **Marking the last unmet goal automatically completes the entire task**. Completion is driven only by individual prove_goal calls; there is no other one-click completion method.
   - ⚠️ **Check quantitative acceptance criteria; never approve early**: for quantified goals (coverage X%, N flags, specified privileges), **you must** check measured values in graph_overview above (coverage.pct, findings_total, etc.) before prove_goal. If below the threshold, **do not** prove_goal; dispatch intents to close the gap. Do not mark met because the goal is mostly achieved or the core result is obtained. Example: requested coverage 100%, measured coverage.pct=40% → unmet; dispatch more tests.

3. **Optional, only at startup and extremely lightweight: orientation probes**. Only when the graph has almost no facts (recent_facts essentially empty, task just started) and the situation alone cannot make initial intents specific, use Bash or similar for very few read-only probes (e.g. 1–2 curl calls for the homepage/fingerprint). **The sole permitted output is a more precise intent description**, never vulnerability discovery/verification/exploitation or endpoint/directory/parameter enumeration results (those belong to workers; dispatch them as intents). Three hard boundaries:
   - Worker-produced facts already exist (facts>0 / nonempty recent_facts) → **do not probe yourself**. Base all judgments on existing facts; this round can only dispatch intents or end. To investigate a clue further, dispatch a worker intent instead of curling it yourself.
   - Even at startup, stop after at most ≤3 probes, solely to clarify initial intents. If you start investigating deeply rather than quickly orienting (enumerating endpoints/directories, trying IDs, decoding chains, repeatedly probing one interface, or testing injection/access-control/vulnerabilities), stop immediately and write an intent: all of that is worker work.
   - If existing facts/situation suffice, do not probe at all.

4. **Choose new directions**: **restraint here means not duplicating existing intents, not minimizing dispatch**. While the objective is unmet, ask what deeper, stronger, uncovered approaches can advance it, rather than whether to wrap up. Intents are **open-ended exploration directions**, not fixed categories/menus. Judge directions from facts, assets, and objectives; compare each with open + running + recent_done:
   - Covered by open/running → do not generate (already being handled).
   - Appeared in recent_done → **inspect its state (included in every item) to understand why it stopped before deciding**:
     · **done (normal completion)**: already covered; do not redispatch unchanged. Whether it is a dead end depends on yielded fact conclusions, not state. Redispatch only for a **materially new mechanism** (new fact/asset/parameter/clearly different approach), with summary explaining what changed. Rewording or hoping another attempt succeeds does not qualify; no retries.
     · **exhausted (budget ran out midway; only partial write-back) / blocked (model/network failure with little exploration)**: both leave incomplete information. First inspect get_worker_trace / get_worker_output for actual progress and the obstacle. Near a breakthrough when cut off → dispatch continuation from previous progress. Pure external failure (often blocked) → redispatch the same direction. Repeatedly stuck at one point → change approach/direction. Always use real trace progress, not state alone.
   - Entirely new, uncovered direction → generate.
   - All known directions covered by open/running → generate nothing and end, awaiting their progress. But if coverage exists only in recent_done, no open/running remains, and the goal is unmet, the hard minimum above requires a new or continuation intent.
   - **Depth before coverage**: coverage is a minimum/acceptance criterion, not the objective itself. After finding a high-value entry point potentially leading to RCE/privilege escalation/data disclosure, prioritize intents to pursue it deeply instead of superficially testing every asset to level coverage.
   - **Maintain route diversity; do not converge too early**: if existing intents all crowd one route/entry point and a **fundamentally different** uncovered direction exists (another entry surface/asset class/exploitation chain), prioritize it over synonymous intents on the same line. Judge substantive differences, not wording. If already covered, still generate nothing. Ideally maintain 2–3 routes with different mechanisms (e.g. upload chain versus authentication bypass), concentrating resources only after one yields evidence of progress toward the objective. **Diversity always obeys the top-level operation constraints**: never generate intents for excluded entry surfaces/ports/hosts/operations, however different they are.

   **Serial exploitation chains: dispatch stepwise, not in parallel.** For strongly dependent chains (①→②→③, each relying on actual output from the previous step), do not dispatch all steps at once: missing prerequisites only cause repetition/idle work. Record the whole chain in TodoWrite (one item per step), dispatch only steps whose prerequisites are satisfied (usually the first), then dispatch the next on a later wake-up after a fact arrives (the prompt includes the todo list), marking satisfied steps completed. Do not split one action into duplicate intents (confirming a trigger point versus triggering it is the same step). Multiple parallel intents are only for **independent dimensions** such as unrelated endpoints.

5. **Submit**: use **one** add_intent call to batch new directions (intents array, at most 4 highest-value entries; do not call repeatedly for individual items):
   - **summary**: one natural-language sentence describing the direction (complete target address + what + why), without fixed categories. Deduplication mainly compares this with existing intents.
   - **asset_ids**: IDs of target assets to test/attack (provide whenever possible; 0/1/multiple, from list_assets). Whenever a direction concerns concrete assets (site/interface/parameter/host), include them for coverage deduplication and asset linkage; include all for multi-asset directions. Leave empty only for purely global reconnaissance without concrete assets.
   - **parent_ids**: upstream nodes from which this direction was derived (optional; 0/1/multiple). Include all facts combined into one intent; also include upstream intents/findings that it derives from. Leave empty for entirely new top-level directions.

Do not duplicate or pad the list. But if the objective is unmet and deeper uncovered approaches exist, dispatch them. Be concise, focused, and efficient.`

func plannerSystem(goal, dataDir, workDir string) string {
	body := renderSystem("planner", plannerDefaultTmpl, PlannerVars{Goal: goal, DataDir: dataDir, Now: nowStr()})
	return body + artifactSpec(workDir)
}

// Plan runs one planning round. emit, if non-nil, receives the planner's execution
// steps (so users can see how it reads the situation and judges goals — the
// planner is the intent generator and was previously a black box). Returns whether
// the planner judged the goal met.
// triggers carries the concrete change(s) that fired this round — worker(s) done
// and/or finding(s) reported (may be several — the engine debounces a burst; empty
// for time/heartbeat wakes). They are spelled out at the top of the prompt so the
// planner looks first at the actual change (which intent, its output/finding).
func (p *Planner) Plan(ctx context.Context, taskID int64, as *db.AssetStore, ts *db.ExplorationStore, goal string, triggers []TriggerEvent, emit func(db.Activity)) (met bool, reason string, err error) {
	// cold-digest §2.3/§7: advance this task's planner-round counter, maintain the
	// cold_since_round stamps, and (if a threshold is hit) kick off background
	// compaction. Synchronous part is cheap (a few queries); the LLM compaction
	// runs in a detached goroutine so it never adds latency to this round.
	ctx, native, admissionErr := prepareNativeTaskRun(ctx, p.prov, "planner", RunInfo{TaskID: taskID, ExplorationID: explorationID(ts)}, ts, nil)
	if admissionErr != nil {
		return false, "", admissionErr
	}
	if native == nil {
		p.compactor.OnPlannerRound(ctx, ts)
	}
	if native != nil {
		as = nil
	} // global asset access is outside this native phase
	tsx := NewToolSet(ts, "planner")
	tsx.SetFindingRecorder(p.findingRecorder)
	if as != nil {
		tsx.SetAssetStore(as, as.Companies())
	}
	tsx.SetTaskID(taskID)
	tsx.SetCoverageEnabled(as == nil || as.CoverageEnabled(taskID))
	tsx.killWork = p.killWork   // enable kill_work tool (nil = unavailable)
	tsx.steerWork = p.steerWork // enable steer_work tool (nil = unavailable)
	if origin, _ := ts.OriginFactID(); origin > 0 {
		tsx.SetOwnerNode(origin) // planner-side anchors default to the task root (origin fact)
	}
	// Domain tools + SDK defaults (Read/Write/Edit/MultiEdit/LS/Glob/Grep/Bash).
	// When asset coverage is disabled, remove add_task_scope/list_untested_assets from the prompt.
	base := append(tsx.DropCoverageTools(tsx.PlannerTools()), actool.DefaultTools()...)
	if nativeRoleContext(ctx) {
		base = tsx.NativeRoleBase("planner")
	}
	ctx = WithRunInfo(ctx, RunInfo{TaskID: taskID, ExplorationID: explorationID(ts)})
	tools, def, cleanup := AugmentTools(ctx, "planner", base)
	defer cleanup()
	// Put key situation (just-completed intents + prefetched full graph) in this round's user input below;
	// system retains static planning text only. This stabilizes system for caching, at the cost that long rounds
	// may compact situation (planner rounds are normally short, low risk). Append situational to input below.
	situational := renderTriggers(ts, triggers) + renderGraphOverview(tsx.graphOverviewData())
	// Task deadline/endgame mode arrives via ctx (see taskclock.go). In the final round append task-timeout
	// planner wrap-up to this round's user input with situational as the current operating instructions,
	// so it only makes final goal assessments and creates no new intents.
	tc := taskClockFrom(ctx)
	if tc.Final {
		situational += "\n\n[Task final wrap-up (special instructions for this round, overriding normal planning above)]:" + resolveTaskTimeoutWrapup("planner")
	}
	// Create this task's working directory <workDir>/tasks/<taskID> first.
	taskDir := ensureRunDir(p.workDir, taskID, 0)
	ctx = intercept.WithReviewContext(ctx, taskDir, intercept.ReviewBackground{})
	sysBody := plannerSystem(goal, p.workDir, taskDir)
	if p.wantConstraints() {
		sysBody += constraintBlock(ts) // Inject operational constraints into system to bound exploration.
	}
	system, boundary := deferredSystem(sysBody, def)
	// Planner has no own wall-clock budget; deadline clamps MaxDuration to remaining time, entering
	// wrap-up at task expiry (timeout → task-timeout text; step budget → per-run text).
	maxDur, clamped := clampMaxDuration(tc.DeadlineUnix, 0)
	settle := wrapupSettlement("planner", nil)
	if tc.DeadlineUnix > 0 {
		settle = wrapupSettlementForTask("planner", nil, clamped)
	}
	opts := agentcore.Options{
		Provider:        p.prov,
		SystemPrompt:    system,
		DynamicBoundary: boundary,
		Tools:           tools,
		DeferredTools:   def.Deferred,
		UnlockSet:       def.Unlock,
		PermissionMode:  permission.ModeBypass,
		EnableWebFetch:  true, // Use recording proxy; load its CA to verify MITM-reissued HTTPS certificates.
		WebFetchProxy:   p.proxyAddr,
		WebFetchCACert:  p.proxyCACert,
		// Optional web search: ddgs needs no key; brave-free needs BraveKey; tavily needs TavilyKey.
		// WebSearchProxy is separate egress (http/https/socks5), unrelated to traffic-recording MITM proxy; empty means direct.
		EnableWebSearch:       p.webSearch.Enabled,
		WebSearchBackend:      p.webSearch.Backend,
		BraveSearchAPIKey:     p.webSearch.BraveKey,
		TavilySearchAPIKey:    p.webSearch.TavilyKey,
		DeepSeekSearchBaseURL: p.webSearch.DeepSeekBaseURL,
		DeepSeekSearchAPIKey:  p.webSearch.DeepSeekAPIKey,
		DeepSeekSearchModel:   p.webSearch.DeepSeekModel,
		WebSearchProxy:        p.webSearch.Proxy,
		BashEnv:               proxyEnv(p.proxyAddr, p.proxyCACert), // Bash subprocesses use the proxy and trust its CA by default.
		WorkingDir:            taskDir,                              // Task working directory <workDir>/tasks/<taskID>.
		ToolOutputDir:         cmdOutDir(taskDir),
		MaxTurns:              p.maxTurns, // 0 = unlimited (configurable in agent management)
		MaxDuration:           maxDur,     // 0 = unlimited; with deadline = remaining time.
		Compaction:            compactionConfig(p.compactionWindow()),
		// Share planning todos across wake-ups so serial chains survive rounds (new session, same store).
		Todos: p.todoFor(ts.ID()),
		// This round's step budget → SDK wrap-up persists decisions (add_intent for directions,
		// prove_goal for evidence, TodoWrite for serial chains), not an end to planning: later wake-ups continue it.
		// Use PromptByReason when task-deadline-clamped (see wrapupSettlementForTask).
		Settlement:   settle,
		NonStreaming: p.nonStreaming(), // Use Provider.Complete when the profile selects non-streaming.
		MaxTokens:    p.maxTokens(),    // 0 omits the cap and uses the server default.
	}
	if p.tx != nil { // persist raw LLM conversation; one accumulating file per task's planner
		opts.Transcript = p.tx
		opts.SessionID = fmt.Sprintf("exp%d-planner", ts.ID())
	}
	// Experimental: noa takes over context compression when enabled; persistent archives live under <workDir>/noa/<SessionID>.
	noaSession := fmt.Sprintf("exp%d-planner", ts.ID())
	if native == nil {
		enableNoa(&opts, p.noaEnabledFn, p.workDir, noaSession, noaWarn(noaSession))
	} else {
		ctx, err = finishNativeTaskOptions(ctx, native, &opts)
		if err != nil {
			return false, "", err
		}
	}
	// Situation (completed intents + full graph) is in this round's user input below, alongside
	// instructions and cross-wake todos (regenerable model planning notes belong in user input).
	// Opening depends on actual changes: changes point to the actual-changes block below; no changes
	// (heartbeat/hint/resume) must not falsely claim the graph changed; ask to review running intents instead.
	lead := "A concrete change just occurred (see Actual changes triggering this round below). Plan the next step accordingly:"
	if len(triggers) == 0 {
		lead = "This wake-up is a **periodic heartbeat/no concrete change signal**: the graph may not have changed. Review running intents as well: use steer_work for prolonged lack of progress or drift, kill_work when the entire direction is wrong, then assess goals and decide whether to add directions:"
		// On heartbeat/no-change wake, no open or running intents means exploration has stalled (no workers
		// or queued directions). Explicitly require new directions this round rather than an empty review loop.
		if active, err := ts.HasActiveIntent(); err == nil && !active {
			lead = "This is a **periodic heartbeat** wake-up, and **there are no open or running intents**: no active workers or queued directions, so exploration has stalled. You **must** produce one or more goal-advancing intents this round that **do not duplicate** existing graph intents (zero intents is not allowed). First assess from the situation below whether the goal is achieved; if not, add directions immediately:"
		}
	}
	input := lead + situational + "\n\nAssess the goals from the situation above. Mark them individually with prove_goal only when **genuinely achieved** (objective results obtained/target vulnerability confirmed). **Hard minimum: if the objective is unmet and there are no open or running intents (frontier_open=0 and running_intents empty), you must produce at least one intent advancing it this round. No active work or queued direction exists to wait for; zero intents stalls the task. Only when open/running intents are making progress or the objective is achieved may this round produce no new intents.**" +
		plannerTodoPrompt(opts.Todos)
	// MaxDuration interrupts running tools at wall-clock expiry and wraps up in place on a live ctx.
	// A stuck round cannot bypass wrap-up; no outer hard ctx needed. ctx handles pause / kill / shutdown only.
	_, _, err = captureRun(ctx, opts, input,
		func(r db.Activity) {
			if emit != nil {
				r.Worker = "planner" // planner activity has no intent_id (it generates them)
				emit(r)
			}
		})
	return tsx.GoalMet, tsx.Reason, err
}
