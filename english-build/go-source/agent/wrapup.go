package agent

import (
	"strings"

	"github.com/Autumn-27/norma/harness"
)

// The SDK injects the wrap-up/settlement prompt when the agent exhausts its
// turn budget (MaxTurns) or times out (run_seconds/MaxDuration), so it persists
// identified but unsaved results and ends with a one-sentence summary.
//
// Admins can override each agent wrap-up prompt in agents.wrapup_prompt; empty
// uses the built-in default. Only prompt text is editable here; disabled tools
// and settlement budget policy are controlled by code.

// WrapupOverride, if set, returns the stored wrap-up prompt for an agent key and
// whether a non-empty one exists. Wired by the server to the agents table (like
// PromptOverride for system prompts). nil / empty → the built-in default is used.
var WrapupOverride func(agentKey string) (string, bool)

// WrapupMaxTurnsOverride, if set, returns the admin-configured turn budget for the
// wrap-up phase of an agent and whether a positive one exists. Wired to the agents
// table. nil / ≤0 → the built-in per-agent default (wrapupTurnDefaults) is used.
var WrapupMaxTurnsOverride func(agentKey string) (int, bool)

// Built-in wrap-up prompts by agent key. Workers reuse settleWrapUpPrompt in
// worker.go; planner/mainagent have their own. Unknown/custom keys use a generic fallback.
var wrapupDefaults = map[string]string{
	"worker":    settleWrapUpPrompt,
	"planner":   plannerWrapUpDefault,
	"mainagent": mainAgentWrapUpDefault,
}

// wrapupTurnDefaults gives each settlement phase its own turn budget (positive
// admin values override it). All get 10 turns to persist results; unknown keys
// use genericWrapupTurns.
var wrapupTurnDefaults = map[string]int{
	"worker":    10,
	"planner":   10,
	"mainagent": 10,
}

const genericWrapupTurns = 10

const plannerWrapUpDefault = "Your turn budget for this planning round is nearly exhausted. Only THIS ROUND is ending: the system will wake you again as the situation changes; the task is not terminating, so do not wind down the entire planning process. Persist conclusions already reached this round, but DO NOT invent intents merely to wrap up (zero intents this round remains a valid outcome): (1) If you have identified directions that SHOULD BE DISPATCHED NOW, submit them in one batch with add_intent; do not withhold ready directions. (2) For goals already proven achieved by findings/facts, call prove_goal to mark met; do not miss them. (3) Record any multi-step serial exploitation chain with TodoWrite so you can dispatch its next step on a later wake-up. Then end this round without a summary."

const mainAgentWrapUpDefault = "Your turn budget is nearly exhausted and this interaction is ending. Do not start new exploration or operations. **In a separate single plain-text sentence**, summarize current progress, key conclusions, and the recommended next step for the user."

const genericWrapUpDefault = "You are about to be terminated because your budget is exhausted. First persist completed results that have not yet been saved, then **in a separate single plain-text sentence** summarize what you did and the key conclusions (this sentence will be displayed as the run result)."

// WrapupDefault returns the built-in default wrap-up prompt for an agent key —
// used by the admin UI as the "restore default" value and empty-field placeholder.
func WrapupDefault(agentKey string) string {
	if d, ok := wrapupDefaults[agentKey]; ok {
		return d
	}
	return genericWrapUpDefault
}

// WrapupTurnsDefault returns the built-in wrap-up turn budget for an agent key —
// used by the admin UI as the "0 = default N" hint.
func WrapupTurnsDefault(agentKey string) int {
	if n, ok := wrapupTurnDefaults[agentKey]; ok {
		return n
	}
	return genericWrapupTurns
}

// resolveWrapup returns the effective wrap-up prompt: the DB override (if set and
// non-empty) over the built-in default.
func resolveWrapup(agentKey string) string {
	if WrapupOverride != nil {
		if t, ok := WrapupOverride(agentKey); ok && strings.TrimSpace(t) != "" {
			return t
		}
	}
	return WrapupDefault(agentKey)
}

// resolveWrapupTurns returns the effective wrap-up turn budget: a positive DB
// override over the built-in per-agent default.
func resolveWrapupTurns(agentKey string) int {
	if WrapupMaxTurnsOverride != nil {
		if v, ok := WrapupMaxTurnsOverride(agentKey); ok && v > 0 {
			return v
		}
	}
	return WrapupTurnsDefault(agentKey)
}

// wrapupSettlement builds the settlement config for an agent's run. Prompt and the
// turn budget are admin-editable per agent; disabled tools are code-owned policy so
// a user can't edit away the "stop probing" guardrail. Resolved fresh each run
// (reads DB live), so edits apply on the next run without a restart.
func wrapupSettlement(agentKey string, disabledTools []string) *harness.Settlement {
	return &harness.Settlement{
		Prompt:        resolveWrapup(agentKey),
		DisabledTools: disabledTools,
		MaxTurns:      resolveWrapupTurns(agentKey),
	}
}

// ---------- Task-level timeout wrap-up (see docs/任务级超时与收尾设计.md) ----------
//
// Separate from per-run wrap-up: one run exhausting its budget does not mean
// the whole task is ending. Planner semantics differ: continue planning after
// a run, but stop dispatching and assess final goals at task timeout. Worker/planner only.

// WrapupTaskTimeoutOverride / ...TurnsOverride provide DB overrides for task
// timeout prompts and budgets (agents.task_timeout_wrapup_prompt / _max_turns; worker/planner only).
var (
	WrapupTaskTimeoutOverride      func(agentKey string) (string, bool)
	WrapupTaskTimeoutTurnsOverride func(agentKey string) (int, bool)
)

var taskTimeoutWrapupDefaults = map[string]string{
	"worker":  workerTaskTimeoutDefault,
	"planner": plannerTaskTimeoutDefault,
}

const workerTaskTimeoutDefault = "**The entire task has reached its timeout and is ending** (not merely this run's budget: the whole exploration has reached its deadline). This is your final opportunity: (1) Persist ALL identified but unsaved results: insert_assets for new assets, record_fact for exploration conclusions/facts, and report_finding for confirmed vulnerabilities. (2) Do not start any new commands or probes. (3) **End with a separate single plain-text sentence** summarizing your key conclusions for this intent."

const plannerTaskTimeoutDefault = "**The entire task has reached its timeout and is ending** (the whole task, not just this round). Make a final goal assessment using ALL current facts and findings: call prove_goal to mark met for goals proven achieved by evidence; do not miss any. **Do not generate any new intents** (they would no longer be executed). End after assessment without a summary."

// TaskTimeoutWrapupDefault returns the built-in task timeout prompt for admin placeholders/reset.
func TaskTimeoutWrapupDefault(agentKey string) string {
	return taskTimeoutWrapupDefaults[agentKey] // Empty for unconfigured mainagent/chat.
}

// resolveTaskTimeoutWrapup prefers nonempty DB overrides to built-ins. Empty
// means no task timeout prompt (not worker/planner); callers fall back to per-run.
func resolveTaskTimeoutWrapup(agentKey string) string {
	if WrapupTaskTimeoutOverride != nil {
		if t, ok := WrapupTaskTimeoutOverride(agentKey); ok && strings.TrimSpace(t) != "" {
			return t
		}
	}
	return TaskTimeoutWrapupDefault(agentKey)
}

func resolveTaskTimeoutTurns(agentKey string) int {
	if WrapupTaskTimeoutTurnsOverride != nil {
		if v, ok := WrapupTaskTimeoutTurnsOverride(agentKey); ok && v > 0 {
			return v
		}
	}
	return resolveWrapupTurns(agentKey) // Default to the per-run turn budget.
}

// wrapupSettlementForTask builds settlement for a worker/planner run that is aware
// of the task deadline. See §5 of the design doc:
//   - clamped=true: this run is bounded by the task deadline. Timeout means
//     task expiry; MaxTurns means turns ran out first, so use the per-run prompt.
//   - clamped=false: both reasons use the per-run prompt (wrapupSettlement).
//
// PromptByReason lets the harness select from the actual settlement reason, not a build-time guess.
func wrapupSettlementForTask(agentKey string, disabledTools []string, clamped bool) *harness.Settlement {
	perRun := resolveWrapup(agentKey)
	st := &harness.Settlement{
		Prompt:        perRun, // Fallback; both reasons use this when not clamped.
		DisabledTools: disabledTools,
		MaxTurns:      resolveWrapupTurns(agentKey),
	}
	if clamped {
		if tt := resolveTaskTimeoutWrapup(agentKey); tt != "" {
			st.PromptByReason = map[harness.TerminalReason]string{
				harness.ReasonTimeout:  tt,     // Task deadline reached.
				harness.ReasonMaxTurns: perRun, // Turns exhausted while task time remains.
			}
			st.MaxTurns = resolveTaskTimeoutTurns(agentKey)
		}
	}
	return st
}
