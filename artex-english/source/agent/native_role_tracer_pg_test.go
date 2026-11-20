//go:build artex_native_pg

package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// Explicit opt-in: no skip and no replacement database. The model transport is
// a labelled proposal spy, not a live assessment or claimed model observation.
func TestNativePlannerCreatesIntentThroughRealPlan(t *testing.T) {
	dsn := os.Getenv("ARTEX_TEST_PG_DSN")
	if dsn == "" {
		t.Fatal("UNEXECUTED: approved ARTEX_TEST_PG_DSN required")
	}
	d, err := db.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	task, err := d.CreateTask("native domain tracer", "Review the authorized synthetic fixture for information disclosure", nil, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer d.DeleteTask(task.ID)
	ts := d.Exploration(task.ExplorationID)
	tool := NewToolSet(ts, "planner").addIntent()
	schema, _ := json.Marshal(tool.InputSchema())
	agents := json.RawMessage(`["planner"]`)
	if err = d.SeedTool(tool.Name(), tool.Description(), schema, agents); err != nil {
		t.Fatal(err)
	}
	oldA, oldR := ToolAugment, ToolResolve
	defer func() { ToolAugment = oldA; ToolResolve = oldR }()
	augmentCalls := 0
	ToolAugment = func(context.Context, string) ([]actool.CoreTool, DeferredInfo, func()) {
		augmentCalls++
		return nil, DeferredInfo{}, func() {}
	}
	// Exercise persisted enabled bindings and actual original handler/schema. The
	// production server resolver independently applies this same native-only gate.
	ToolResolve = func(_ context.Context, role string, base []actool.CoreTool) []actool.CoreTool {
		rows, e := d.ListTools()
		if e != nil {
			return []actool.CoreTool{}
		}
		out := []actool.CoreTool{}
		for _, candidate := range base {
			for _, row := range rows {
				if candidate.Name() != row.Key || row.Key != "add_intent" || !row.Enabled {
					continue
				}
				bound := false
				for _, r := range row.Agents {
					if r == role {
						bound = true
					}
				}
				if !bound {
					continue
				}
				var s map[string]any
				if json.Unmarshal(row.Schema, &s) != nil {
					return []actool.CoreTool{}
				}
				out = append(out, DecorateTool(candidate, row.Description, s))
			}
		}
		return out
	}
	resolved := ToolResolve(context.Background(), "planner", []actool.CoreTool{tool})
	if len(resolved) != 1 {
		t.Fatal("positive persisted planner binding unavailable")
	}
	plannerSchemas := actool.NewRegistry(resolved...).Schemas()
	workerSet := NewToolSet(ts, "worker")
	workerSet.SetTaskID(task.ID)
	workerTools := append([]actool.CoreTool{workerSet.recordFact()}, nativeexec.Six()...)
	workerSchemas := actool.NewRegistry(workerTools...).Schemas()
	dir, phase := rolePermitFixture(t)
	phase["task_id"] = task.ID
	phase["exploration_id"] = task.ExplorationID
	phase["roles"] = []any{
		map[string]any{"role": "planner", "purpose": "run", "intent_id": 0, "session_id": fmt.Sprintf("exp%d-planner", task.ExplorationID), "catalog_sha256": roleFixtureDigest(t, phase, "planner", plannerSchemas)},
		map[string]any{"role": "worker", "purpose": "run", "dynamic_intent": true, "intent_id": 0, "session_id": "", "catalog_sha256": roleFixtureDigest(t, phase, "worker", workerSchemas)},
	}
	writeRolePermit(t, dir, phase)
	policy, opens, err := loadRoleFixture(t, dir)
	if err != nil || opens != 1 {
		t.Fatalf("private permit: %v key_opens=%d", err, opens)
	}
	cfg := ConfigFrom("codex-native", "gpt-6.1-sol", policy.Endpoint, "", "")
	cfg.Native = policy
	p, err := newNativeRPC(cfg)
	if err != nil {
		t.Fatal(err)
	}
	p.appAdmission = true
	calls := 0
	p.client.Transport = roleRoundTrip(func(req *http.Request) (*http.Response, error) {
		calls++
		body := roleSyntheticResponse
		if calls == 1 {
			body = `{"protocol":"artex-native-v1","profile":"codex-native","generation_tokens_enforced":false,"message":{"role":"assistant","content":[{"type":"tool_use","id":"call_11111111111111111111111111111111","name":"add_intent","input":{"summary":"Inspect the authorized synthetic fixture for publicly exposed diagnostic information"}}]},"stop_reason":"tool_use","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}`
		}
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}, nil
	})
	pl := NewPlanner(p, "gpt-6.1-sol", t.TempDir(), nil, 0, 3)
	pl.SetNoaEnabled(func() bool { t.Fatal("native called NoA resolver"); return true })
	if _, _, err = pl.Plan(t.Context(), task.ID, nil, ts, task.Goal, nil, nil); err != nil {
		t.Fatal(err)
	}
	nodes, err := ts.ListByKind(db.KindIntent, 100)
	if err != nil || len(nodes) != 1 || calls != 2 || augmentCalls != 0 {
		t.Fatalf("persisted intents=%d provider_calls=%d mcp=%d err=%v", len(nodes), calls, augmentCalls, err)
	}
	intent := nodes[0]
	if intent.Origin != "planner" || !strings.Contains(string(intent.Payload), "publicly exposed diagnostic") {
		t.Fatalf("not the real planner proposal: %+v", intent)
	}
	claimed, err := ts.ClaimIntent(intent.ID, "native-tracer")
	if err != nil || !claimed {
		t.Fatalf("actual scheduler claim failed: %v", err)
	}
	ri := RunInfo{TaskID: task.ID, ExplorationID: task.ExplorationID, IntentID: intent.ID}
	ctx := transcript.WithSessionID(WithRunInfo(t.Context(), ri), WorkerSessionID(ts.ID(), intent.ID))
	if _, err = p.BindNativeRole(ctx, "worker", "run", ri, workerSchemas); err == nil {
		t.Fatal("template bound without DB boundary")
	}
	ctx, err = p.BindNativeTaskRole(ctx, "worker", ri, ts, workerSchemas)
	if err != nil {
		t.Fatal(err)
	}
	good := json.RawMessage(fmt.Sprintf(`{"intent_id":%d,"summary":"synthetic DB tracer fact; no target observations","confidence":"inferred"}`, intent.ID))
	if _, err = workerSet.recordFact().Call(ctx, good, nil); err != nil {
		t.Fatalf("positive real domain handler: %v", err)
	}
	bad := json.RawMessage(fmt.Sprintf(`{"intent_id":%d,"facts":[{"intent_id":%d,"summary":"must not persist"}]}`, intent.ID, intent.ID+1))
	if _, err = workerSet.recordFact().Call(ctx, bad, nil); err == nil {
		t.Fatal("nested worker ID drift admitted")
	}
	if err = ts.SetIntentState(intent.ID, "stopped"); err != nil {
		t.Fatal(err)
	}
	if _, err = resolveNativeExecution(ctx); err == nil {
		t.Fatal("stopped intent retained effect binding")
	}
	if _, _, _, err = p.Complete(ctx, llm.CompletionRequest{Messages: []llm.Message{llm.UserText("synthetic")}, Tools: workerSchemas}); err == nil || calls != 2 {
		t.Fatal("revoked DB membership reached provider")
	}
	t.Logf("REAL PG Plan persisted unknown intent %d; dynamic binding from template, final nested-ID denial, stopped-intent denial; synthetic provider only, no executor/E2E claim", intent.ID)
}
