package agent

import (
	"context"
	"encoding/json"

	actool "github.com/Autumn-27/norma/tool"
)

// Expose built-in tools as an enumerable, DB-overridable catalog rather than code alone:
//   - BuiltinToolSeeds() expands execution-agent tools into seed records (key +
//     description + argument schema + default agent bindings), idempotently seeded into tools at startup.
//   - ToolResolve filters assembled tools by agent at runtime using DB rows,
//     overriding descriptions/schema and injecting argument defaults. Keys/handlers stay in code; DB changes prose/defaults only.
// Call handlers ALWAYS come from code. DB cannot change behavior, only model-visible descriptions/default inputs.

// ToolSeed is a seedable built-in snapshot: key is CoreTool.Name(), fixed to its handler
// and read-only in UI. Desc/Schema come from code; Agents are code-default bindings.
type ToolSeed struct {
	Key    string         // = CoreTool.Name(), immutable primary key.
	Desc   string         // Top-level description (UI-overridable).
	Schema map[string]any // Argument JSON Schema (structure read-only; description/default editable in UI).
	Agents []string       // Default bound agent keys (worker/planner/mainagent).
}

// builtinToolsByAgent constructs each execution agent's domain tools using a read-only shell
// ToolSet with nil stores. Constructors only place closures in Spec, never dereferencing stores,
// so nil is safe. Only read Name()/Description()/InputSchema() here; NEVER Call.
//
// Deliberately exclude SDK generic tools actool.DefaultTools() (Read/Write/Edit/MultiEdit/LS/Glob/
// Grep/Bash): all agents always have them, so no binding decision. Most documentation lives in Prompt();
// this catalog only covers Description(), making partial overrides misleading. No seed → no DB row → ToolResolve
// passes them unchanged, preserving behavior. Only artex domain tools enter this managed catalog.
func builtinToolsByAgent() map[string][]actool.CoreTool {
	ts := NewToolSet(nil, "")
	return map[string][]actool.CoreTool{
		"mainagent": ts.MainAgentTools(),
		"planner":   ts.PlannerTools(),
		"worker":    ts.WorkerTools(),
		// goals (decomposer) defaults to set_goals + set_constraints to persist goals and extracted
		// constraints. Shared managed tools with mainagent; UI edits description/schema and per-agent bindings.
		"goals": {ts.setGoals(), ts.setConstraints()},
		// auto defaults to finding reporting + asset management; other domain tools are opt-in via UI.
		// New databases seed here; existing ones migrate via seedAutoDefaultBindings.
		"auto": {ts.addFinding(), ts.insertAssets(), ts.addCompanyScope(), ts.listAssets(), ts.listCompanies()},
		// pentest (standalone) defaults to query/insert assets, report/list findings, and list companies.
		// New databases seed here; existing ones migrate via seedPentestDefaultBindings.
		"pentest": {ts.listAssets(), ts.insertAssets(), ts.addFinding(), ts.listFindings(), ts.listCompanies()},
	}
}

// defaultUnbound system tools still enter the catalog (visible in UI for manual agent binding),
// but default to NO agents: ToolResolve drops empty-bound tools for every agent; explicit opt-in required.
// They remain in some base tool set (e.g. goal_met in PlannerTools) so seeds can obtain desc/schema,
// and explicit user binding can retain the tool at runtime through ToolResolve.
//
// goal_met bypasses individual prove_goal calls to declare the WHOLE TASK complete: high impact and
// misjudgment risk, redundant with last prove_goal auto-completion. Default unbound; manual opt-in only.
var defaultUnbound = map[string]bool{"goal_met": true}

// BuiltinToolSeeds deduplicates agent tools into seeds: same-name tools (e.g. list_assets across
// agents) share one entry with unioned Agents; defaultUnbound tools force empty bindings.
func BuiltinToolSeeds() []ToolSeed {
	byAgent := builtinToolsByAgent()
	order := []string{"mainagent", "goals", "planner", "worker", "auto", "pentest"}

	type acc struct {
		tool   actool.CoreTool
		agents []string
	}
	m := map[string]*acc{}
	var keys []string
	for _, ak := range order {
		for _, t := range byAgent[ak] {
			a, ok := m[t.Name()]
			if !ok {
				a = &acc{tool: t}
				m[t.Name()] = a
				keys = append(keys, t.Name())
			}
			a.agents = append(a.agents, ak)
		}
	}

	out := make([]ToolSeed, 0, len(keys))
	for _, k := range keys {
		a := m[k]
		agents := a.agents
		if defaultUnbound[k] {
			agents = []string{} // Cataloged, manually bindable, but default unbound; [] rather than null, like other tools.
		}
		out = append(out, ToolSeed{
			Key:    k,
			Desc:   a.tool.Description(),
			Schema: a.tool.InputSchema(),
			Agents: agents,
		})
	}
	return out
}

// ToolResolve, if set, post-processes an agent's fully-assembled tool list against
// the DB tools table: it drops tools not bound to this agent (or globally disabled)
// and wraps the rest so the model sees the DB-overridden description/schema and
// Default inputs get injected. Tools with no matching DB row (MCP/skill/host tools like
// traffic) pass through untouched. nil = tools unchanged. Wired in server/assembly.go.
var ToolResolve func(ctx context.Context, agentKey string, tools []actool.CoreTool) []actool.CoreTool

// DecorateTool wraps t so Description()/InputSchema() report the DB overrides and
// Call() injects scalar parameter defaults (from schema's "default" props) whenever
// the model omitted them. Name/Prompt/permission/scheduler flags delegate to t, so
// the tool's identity and handler are unchanged. Empty desc/schema fall back to t's.
func DecorateTool(t actool.CoreTool, desc string, schema map[string]any) actool.CoreTool {
	if desc == "" {
		desc = t.Description()
	}
	if len(schema) == 0 {
		schema = t.InputSchema()
	}
	return &overriddenTool{CoreTool: t, desc: desc, schema: schema}
}

// overriddenTool is a CoreTool decorator: it embeds the original (so all behavioral
// methods — Prompt/IsReadOnly/IsConcurrencySafe/CheckPermissions/Name — delegate)
// and overrides only the model-facing description/schema plus default injection.
type overriddenTool struct {
	actool.CoreTool
	desc   string
	schema map[string]any
}

func (o *overriddenTool) Description() string         { return o.desc }
func (o *overriddenTool) InputSchema() map[string]any { return o.schema }

func (o *overriddenTool) Call(ctx context.Context, in json.RawMessage, tc *actool.ToolContext) (actool.Result, error) {
	return o.CoreTool.Call(ctx, injectDefaults(in, o.schema), tc)
}

// injectDefaults fills scalar parameter defaults declared in the (possibly edited)
// schema into the input JSON whenever the model omitted the field or left it empty/
// null. Structure (names/types/required) is untouched; only default values are merged in.
func injectDefaults(in json.RawMessage, schema map[string]any) json.RawMessage {
	defs := scalarDefaults(schema)
	if len(defs) == 0 {
		return in
	}
	m := map[string]json.RawMessage{}
	if len(in) > 0 {
		if err := json.Unmarshal(in, &m); err != nil {
			return in // non-object input: don't touch it
		}
	}
	changed := false
	for k, dv := range defs {
		if cur, ok := m[k]; !ok || isEmptyJSON(cur) {
			m[k] = dv
			changed = true
		}
	}
	if !changed {
		return in
	}
	b, err := json.Marshal(m)
	if err != nil {
		return in
	}
	return b
}

// scalarDefaults extracts properties[k]["default"] for scalar params (string/
// integer/number/boolean). Array/object defaults are skipped: merging them is
// ambiguous and not worth the surprise.
func scalarDefaults(schema map[string]any) map[string]json.RawMessage {
	props, _ := schema["properties"].(map[string]any)
	if len(props) == 0 {
		return nil
	}
	out := map[string]json.RawMessage{}
	for name, raw := range props {
		p, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		dv, ok := p["default"]
		if !ok || dv == nil {
			continue
		}
		switch p["type"] {
		case "string", "integer", "number", "boolean":
			if b, err := json.Marshal(dv); err == nil {
				out[name] = b
			}
		}
	}
	return out
}

func isEmptyJSON(raw json.RawMessage) bool {
	s := string(raw)
	return s == "null" || s == `""`
}
