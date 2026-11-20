//go:build artex_native_pg

package server

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
)

type completionModel struct {
	mu       sync.Mutex
	calls    int
	proposal func(int, map[string]any) (string, any)
}

func (m *completionModel) serve(w http.ResponseWriter, r *http.Request) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.calls++
	var req map[string]any
	if json.NewDecoder(r.Body).Decode(&req) != nil {
		w.WriteHeader(400)
		return
	}
	name, input := m.proposal(m.calls, req)
	content := []any{map[string]any{"type": "text", "text": "synthetic qualification complete"}}
	stop := "end_turn"
	if name != "" {
		content = []any{map[string]any{"type": "tool_use", "id": fmt.Sprintf("call_%032x", m.calls), "name": name, "input": input}}
		stop = "tool_use"
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"protocol": "artex-native-v1", "profile": "codex-native", "generation_tokens_enforced": false, "message": map[string]any{"role": "assistant", "content": content}, "stop_reason": stop, "usage": map[string]int{"input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0}})
}
func completionWrite(t *testing.T, dir, name string, data []byte) {
	t.Helper()
	p := filepath.Join(dir, name)
	if e := os.WriteFile(p, data, 0600); e != nil {
		t.Fatal(e)
	}
	if e := os.Chmod(p, 0600); e != nil {
		t.Fatal(e)
	}
}
func completionProvider(t *testing.T, s *Server, task *Task, roles []string, model *completionModel) (llm.Provider, agent.Config, string, map[string]any) {
	t.Helper()
	httpd := httptest.NewServer(http.HandlerFunc(model.serve))
	t.Cleanup(httpd.Close)
	dir, e := os.MkdirTemp("", "cpx-")
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	if e = os.Chmod(dir, 0700); e != nil {
		t.Fatal(e)
	}
	var id [16]byte
	rand.Read(id[:])
	tid, _ := parseTaskID(task.ID)
	phase := map[string]any{"schema_version": 1, "phase_id": "completion-" + hex.EncodeToString(id[:]), "authority_generation": 1, "task_id": tid, "exploration_id": task.ExpID, "fixture_origin": "http://owned-assessment-fixture:8080", "network_policy_id": "synthetic-get-head", "executor_id": "synthetic-executor", "ledger_id": "synthetic-ledger", "expires_at": time.Now().Add(8 * time.Minute).UTC().Format(time.RFC3339Nano), "max_calls": 16, "max_aggregate_bytes": 2097152}
	var permits []any
	for _, role := range roles {
		schemas := agent.NativePGFixtureSchemas(role, task.Store, tid, contains(roles, "reporter"))
		if role == "reporter" {
			schemas = actool.NewRegistry(s.toolGetTaskNodeDetail(), s.toolGetFindingTraffic(), s.toolUpdateFindingReport()).Schemas()
		}
		raw, _ := json.Marshal(phase)
		digest, e := agent.NativePGFixtureCatalog(raw, role, schemas)
		if e != nil {
			t.Fatalf("catalog %s: %v", role, e)
		}
		metadata, _ := json.Marshal(map[string]any{"role": role, "catalog_sha256": digest, "tools": schemas})
		t.Logf("CATALOG %s", metadata)
		session := fmt.Sprintf("exp%d-%s", task.ExpID, role)
		if role == "mainagent" {
			session = fmt.Sprintf("exp%d-main", task.ExpID)
		}
		entry := map[string]any{"role": role, "purpose": "run", "intent_id": 0, "session_id": session, "catalog_sha256": digest}
		if role == "worker" {
			entry["dynamic_intent"] = true
			entry["session_id"] = ""
		}
		if role == "reporter" {
			entry["dynamic_finding"] = true
			entry["session_id"] = ""
		}
		permits = append(permits, entry)
	}
	phase["roles"] = permits
	raw, _ := json.Marshal(phase)
	completionWrite(t, dir, "phase.json", raw)
	endpoint := httpd.URL + "/artex/native/v1/complete"
	policy := map[string]any{"model": "gpt-6.1-sol", "protocol": "artex-native-v1", "endpoint": endpoint, "budget_mode": "time/bytes/calls", "timeout_seconds": 30, "max_calls": 16, "max_bytes": 65536, "generation_tokens_enforced": false, "native_tools": false, "streaming": false, "role_phase_enabled": true}
	raw, _ = json.Marshal(policy)
	completionWrite(t, dir, "policy.json", raw)
	completionWrite(t, dir, "service.key", []byte("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
	cfg := agent.ConfigFrom("codex-native", "gpt-6.1-sol", endpoint, "", "")
	p, e := agent.NewNativePGFixtureProvider(dir, cfg)
	if e != nil {
		t.Fatal(e)
	}
	return p, cfg, dir, phase
}
func TestNativeCompletionProductionGoalMainRuntime(t *testing.T) {
	if os.Getenv("ARTEX_TEST_PG_DSN") == "" {
		t.Fatal("approved real PG required")
	}
	s, f, _ := trafficEvidenceServer(t)
	finding, e := s.m.pg.GetFinding(f.FindingID)
	if e != nil {
		t.Fatal(e)
	}
	task := s.m.ResolveTask(fmt.Sprint(*finding.TaskID))
	tid, _ := parseTaskID(task.ID)
	if e := s.m.SetTaskStatus(task.ID, "running"); e != nil {
		t.Fatal(e)
	}
	model := &completionModel{proposal: func(n int, _ map[string]any) (string, any) {
		if n == 1 || n == 3 {
			return "set_goals", map[string]any{"goals": []any{map[string]any{"text": "Synthetic completion SQL qualification"}}}
		}
		return "", nil
	}}
	p, cfg, _, _ := completionProvider(t, s, task, []string{"goals", "mainagent"}, model)
	// Positive control uses the same real goal entrypoint and persisted bindings.
	if goals, e := agent.DecomposeGoalsWithProviderChecked(t.Context(), p, s.m.dir, task.Goal, "", nil, task.Store, tid, true, 0, nil); e != nil || len(goals) == 0 {
		t.Fatalf("positive actual goals: %v %+v", e, goals)
	}
	s.llmCfg = cfg
	s.llmProv = p
	s.llmOn = true
	bundle := s.agentsForTask(task)
	if goals, e := agent.DecomposeGoalsWithProviderChecked(t.Context(), bundle.runtime, s.m.dir, task.Goal, "", nil, task.Store, tid, true, 0, nil); e != nil || len(goals) == 0 {
		t.Fatalf("production goal runtime: %v %+v", e, goals)
	}
	model.proposal = func(n int, _ map[string]any) (string, any) {
		if n == 5 {
			return "add_hint", map[string]any{"text": "Synthetic main SQL qualification"}
		}
		return "", nil
	}
	if _, e := bundle.main.Chat(context.Background(), tid, 0, nil, task.Store, task.Goal, "Review current evidence", nil, nil, nil, nil, nil); e != nil {
		t.Fatalf("production main factory: %v", e)
	}
	hints, e := task.Store.ListByKind(db.KindHint, 100)
	if e != nil || len(hints) == 0 {
		t.Fatalf("actual main handler did not persist: %v", e)
	}
	denyGoals := func(t *testing.T) {
		t.Helper()
		before := model.calls
		if _, e := agent.DecomposeGoalsWithProviderChecked(t.Context(), bundle.runtime, s.m.dir, task.Goal, "", nil, task.Store, tid, true, 0, nil); e == nil || model.calls != before {
			t.Fatalf("negative reached provider or admitted: calls %d -> %d err=%v", before, model.calls, e)
		}
	}
	t.Run("paused", func(t *testing.T) {
		if e := s.m.pg.SetPaused(tid, true); e != nil {
			t.Fatal(e)
		}
		defer s.m.pg.SetPaused(tid, false)
		denyGoals(t)
	})
	t.Run("disabled_role", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE agents SET enabled=false WHERE key='goals'`)
		defer s.m.pg.Exec(`UPDATE agents SET enabled=true WHERE key='goals'`)
		denyGoals(t)
	})
	t.Run("missing_binding", func(t *testing.T) {
		row, e := s.m.pg.GetTool("set_goals")
		if e != nil || row == nil {
			t.Fatal(e)
		}
		old, _ := json.Marshal(row.Agents)
		s.m.pg.Exec(`UPDATE tools SET agents='[]'::jsonb WHERE key='set_goals'`)
		defer s.m.pg.Exec(`UPDATE tools SET agents=$1::jsonb WHERE key='set_goals'`, string(old))
		denyGoals(t)
	})
	t.Run("disabled_tool", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE tools SET enabled=false WHERE key='set_goals'`)
		defer s.m.pg.Exec(`UPDATE tools SET enabled=true WHERE key='set_goals'`)
		denyGoals(t)
	})
	t.Run("missing_source", func(t *testing.T) { s.llmOn = false; defer func() { s.llmOn = true }(); denyGoals(t) })
	t.Run("invalid_explicit_profile_no_global_fallback", func(t *testing.T) {
		id, e := s.m.pg.SaveProfile(&db.LLMProfile{Name: fmt.Sprintf("invalid-native-completion-%d", time.Now().UnixNano()), Format: "openai", Model: "invalid-fixture", APIKey: ""})
		if e != nil {
			t.Fatal(e)
		}
		defer s.m.pg.DeleteProfile(id)
		if e = s.m.pg.SetAgentLLMProfile("goals", &id); e != nil {
			t.Fatal(e)
		}
		defer s.m.pg.SetAgentLLMProfile("goals", nil)
		denyGoals(t)
	})
	t.Run("main_paused", func(t *testing.T) {
		s.m.pg.SetPaused(tid, true)
		defer s.m.pg.SetPaused(tid, false)
		before := model.calls
		if _, e := bundle.main.Chat(t.Context(), tid, 0, nil, task.Store, task.Goal, "synthetic", nil, nil, nil, nil, nil); e == nil || model.calls != before {
			t.Fatal("paused main reached model")
		}
	})
	t.Run("missing_role", func(t *testing.T) {
		r := &taskLLMRuntime{s: s, taskID: task.ID, agentKey: "missing-native-role"}
		ctx := agent.WithRunInfo(t.Context(), agent.RunInfo{TaskID: tid, ExplorationID: task.ExpID})
		if _, e := r.NativeTaskProvider(ctx); e == nil {
			t.Fatal("missing role resolved")
		}
	})
}

func TestNativeCompletionWorkerFindingToReporter(t *testing.T) {
	if os.Getenv("ARTEX_TEST_PG_DSN") == "" {
		t.Fatal("approved real PG required")
	}
	s, f, _ := trafficEvidenceServer(t)
	finding, e := s.m.pg.GetFinding(f.FindingID)
	if e != nil {
		t.Fatal(e)
	}
	task := s.m.ResolveTask(fmt.Sprint(*finding.TaskID))
	tid, _ := parseTaskID(task.ID)
	if e = s.m.SetTaskStatus(task.ID, "running"); e != nil {
		t.Fatal(e)
	}
	id, e := task.Store.AddNode(db.KindIntent, map[string]any{"summary": "Synthetic report qualification"}, 0, "open", "planner", nil)
	if e != nil {
		t.Fatal(e)
	}
	if ok, e := task.Store.ClaimIntent(id, "completion"); e != nil || !ok {
		t.Fatal(e)
	}
	intent, e := task.Store.GetNode(id)
	if e != nil {
		t.Fatal(e)
	}
	model := &completionModel{proposal: func(n int, _ map[string]any) (string, any) {
		if n == 1 {
			return "record_fact", map[string]any{"intent_id": id, "summary": "Synthetic worker production factory qualification", "confidence": "inferred"}
		}
		return "", nil
	}}
	p, cfg, dir, phase := completionProvider(t, s, task, []string{"worker"}, model)
	// Valid same-entrypoint positive control before adding report authority.
	config := map[string]any{"schema_version": 1, "reviewed": true, "phase_id": phase["phase_id"], "authority_generation": phase["authority_generation"], "task_id": tid, "exploration_id": task.ExpID, "executor_id": phase["executor_id"], "network_policy_id": phase["network_policy_id"], "fixture_origin": phase["fixture_origin"], "control_socket": filepath.Join(dir, "control.sock")}
	raw, _ := json.Marshal(config)
	completionWrite(t, dir, "executor.json", raw)
	completionWrite(t, dir, "executor.key", []byte("kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"))
	s.llmCfg = cfg
	s.llmProv = p
	s.llmOn = true
	s.chatAgent = agent.NewChatAgent(p, cfg.Model, s.m.dir, nil, 0)
	bundle := s.agentsForTask(task)
	if _, counts, e := bundle.wk.Execute(t.Context(), "worker", tid, nil, task.Store, intent, nil, nil, nil, nil); e != nil || counts.Facts != 1 {
		t.Fatalf("positive production Worker.Execute: %+v %v", counts, e)
	}
	// Unsupported reporter admission is the first behavioral RED. This exact
	// normal pipeline is extended below only after the reporter template exists.
	p, cfg, dir, phase = completionProvider(t, s, task, []string{"worker", "reporter"}, model)
	config["phase_id"] = phase["phase_id"]
	config["control_socket"] = filepath.Join(dir, "control.sock")
	raw, _ = json.Marshal(config)
	completionWrite(t, dir, "executor.json", raw)
	completionWrite(t, dir, "executor.key", []byte("kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"))
	s.llmCfg = cfg
	s.llmProv = p
	s.chatAgent = agent.NewChatAgent(p, cfg.Model, s.m.dir, nil, 0)
	s.invalidateTaskAgents()
	bundle = s.agentsForTask(task)
	var findingRow, findingNode, version int64
	model.proposal = func(n int, req map[string]any) (string, any) {
		switch n {
		case 3:
			return "report_finding", map[string]any{"intent_id": id, "vulnclass": "SYNTHETIC", "severity": "low", "summary": "Synthetic committed report tracer", "evidence": "Synthetic local fixture only, no assessment observations"}
		case 5:
			return "get_task_node_detail", map[string]any{"task_id": task.ID, "id": findingNode}
		case 6:
			return "get_finding_traffic", map[string]any{"finding_id": fmt.Sprint(findingRow)}
		case 7:
			return "update_finding_report", map[string]any{"finding_id": findingNode, "evidence_version": version, "report": "# Synthetic qualification report\n\nEvidence: synthetic committed finding.\n\nRemediation: synthetic fixture only."}
		}
		return "", nil
	}
	if _, counts, e := bundle.wk.Execute(t.Context(), "worker", tid, nil, task.Store, intent, nil, nil, nil, nil); e != nil || counts.Findings != 1 {
		t.Fatalf("worker report handler unavailable: %+v %v", counts, e)
	}
	nodes, e := task.Store.ListByKind(db.KindFinding, 100)
	if e != nil {
		t.Fatal(e)
	}
	for _, n := range nodes {
		if n.Origin == "worker" {
			findingNode = n.ID
		}
	}
	if findingNode <= 0 {
		t.Fatal("no committed worker finding")
	}
	findingRow, e = s.m.pg.FindingIDByNodeID(findingNode)
	if e != nil {
		t.Fatal(e)
	}
	persisted, e := s.m.pg.GetFinding(findingRow)
	if e != nil {
		t.Fatal(e)
	}
	version = persisted.EvidenceVersion
	// Separate ordinary scheduler pass over committed rows; no parsing of the
	// worker's tool result and no manual report/evidence tool execution.
	s.ctx = context.Background()
	triggers, e := s.m.pg.ListEnabledTriggers()
	if e != nil {
		t.Fatal(e)
	}
	s.m.pg.SetSchedState(schedKeyLastFinding, fmt.Sprint(findingNode-1))
	sc := newScheduler(s)
	sc.fireFindings(triggers)
	deadline := time.Now().Add(5 * time.Second)
	for {
		persisted, e = s.m.pg.GetFinding(findingRow)
		if e != nil {
			t.Fatal(e)
		}
		if persisted.Report != "" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("normal committed event never saved reporter output: model_calls=%d", model.calls)
		}
		time.Sleep(10 * time.Millisecond)
	}
	for {
		s.queueMu.Lock()
		active := s.triggerActive["reporter"]
		s.queueMu.Unlock()
		if active == 0 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("reporter queue failed to settle")
		}
		time.Sleep(10 * time.Millisecond)
	}
	if persisted.ReportEvidenceVersion != version {
		t.Fatal("evidence version not sealed")
	}
	var convID int64
	if e = s.m.pg.QueryRow(`SELECT id FROM conversations WHERE agent_key='reporter' ORDER BY id DESC LIMIT 1`).Scan(&convID); e != nil {
		t.Fatal(e)
	}
	if findingRow == findingNode {
		t.Fatal("fixture did not qualify independent row/node IDs")
	}
	t.Logf("REAL PG production Worker.Execute -> committed finding row %d / node %d -> scheduler -> reporter conversation %d -> standard versioned report; synthetic model only", findingRow, findingNode, convID)
	eventCtx, e := agent.WithNativeReporterFinding(t.Context(), s.m.pg, tid, findingNode, convID)
	if e != nil {
		t.Fatal(e)
	}
	ca := agent.NewChatAgent(&taskLLMRuntime{s: s, taskID: task.ID, agentKey: "reporter"}, "task-router", s.m.dir, nil, 0)
	ca.SetNativeReporterTools(s.nativeReporterTools())
	t.Run("opaque_positive", func(t *testing.T) {
		before := model.calls
		if _, e := ca.Chat(eventCtx, "reporter", fmt.Sprintf("conv-%d", convID), "Synthetic positive", 2, 0, false, nil); e != nil || model.calls != before+1 {
			t.Fatalf("opaque admitted control: %v", e)
		}
	})
	t.Run("no_authority_from_runinfo_or_message", func(t *testing.T) {
		old := agent.ToolAugment
		defer func() { agent.ToolAugment = old }()
		augments := 0
		agent.ToolAugment = func(context.Context, string) ([]actool.CoreTool, agent.DeferredInfo, func()) {
			augments++
			return nil, agent.DeferredInfo{}, func() {}
		}
		before := model.calls
		ctx := agent.WithRunInfo(t.Context(), agent.RunInfo{TaskID: tid, ExplorationID: task.ExpID, IntentID: id})
		_, e := ca.Chat(ctx, "reporter", fmt.Sprintf("conv-%d", convID), fmt.Sprintf("reporter finding_id=%d task=%d", findingRow, tid), 2, 0, false, nil)
		if e == nil || model.calls != before || augments != 0 {
			t.Fatalf("unbound reporter started support/provider: err=%v augments=%d calls=%d", e, augments, model.calls-before)
		}
	})
	denyReporter := func(t *testing.T) {
		t.Helper()
		before := model.calls
		if _, e := ca.Chat(eventCtx, "reporter", fmt.Sprintf("conv-%d", convID), "Synthetic denied", 2, 0, false, nil); e == nil || model.calls != before {
			t.Fatalf("invalid reporter reached model: %v calls=%d", e, model.calls-before)
		}
	}
	t.Run("paused_reporter_source", func(t *testing.T) { s.m.pg.SetPaused(tid, true); defer s.m.pg.SetPaused(tid, false); denyReporter(t) })
	t.Run("disabled_reporter", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE agents SET enabled=false WHERE key='reporter'`)
		defer s.m.pg.Exec(`UPDATE agents SET enabled=true WHERE key='reporter'`)
		denyReporter(t)
	})
	t.Run("disabled_report_tool", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE tools SET enabled=false WHERE key='update_finding_report'`)
		defer s.m.pg.Exec(`UPDATE tools SET enabled=true WHERE key='update_finding_report'`)
		denyReporter(t)
	})
	t.Run("evidence_changed_before_model", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE findings SET evidence_version=evidence_version+1 WHERE id=$1`, findingRow)
		defer s.m.pg.Exec(`UPDATE findings SET evidence_version=$1 WHERE id=$2`, version, findingRow)
		denyReporter(t)
	})
	for _, tc := range []struct {
		name, tool string
		input      map[string]any
	}{
		{"row_not_node", "update_finding_report", map[string]any{"finding_id": findingRow, "report": "must not overwrite", "evidence_version": version}},
		{"wrong_evidence_version", "update_finding_report", map[string]any{"finding_id": findingNode, "report": "must not overwrite", "evidence_version": version + 1}},
		{"cross_task", "get_task_node_detail", map[string]any{"task_id": fmt.Sprint(tid + 1), "id": findingNode}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			first := true
			model.proposal = func(int, map[string]any) (string, any) {
				if first {
					first = false
					return tc.tool, tc.input
				}
				return "", nil
			}
			errors := 0
			if _, e := ca.Chat(eventCtx, "reporter", fmt.Sprintf("conv-%d", convID), "Synthetic final-input denial", 3, 0, false, func(a db.Activity) {
				if a.Kind == "tool_result" && a.IsError {
					errors++
				}
			}); e != nil {
				t.Fatal(e)
			}
			if errors != 1 {
				t.Fatalf("expected actual guarded tool error, got %d", errors)
			}
			f, e := s.m.pg.GetFinding(findingRow)
			if e != nil || f.Report != persisted.Report {
				t.Fatal("denied report mutated")
			}
		})
	}
	t.Run("invalid_event_does_not_leave_busy_conversation", func(t *testing.T) {
		before := model.calls
		s.runTriggeredRun(triggeredRun{agentKey: "reporter", taskID: tid + 1, findingNodeID: findingNode, title: "Synthetic invalid event", message: "not authority"})
		var latest int64
		if e := s.m.pg.QueryRow(`SELECT id FROM conversations WHERE agent_key='reporter' ORDER BY id DESC LIMIT 1`).Scan(&latest); e != nil {
			t.Fatal(e)
		}
		s.chatMu.Lock()
		busy := s.chatBusy[s.convBusyKey(latest)]
		s.chatMu.Unlock()
		if busy || model.calls != before {
			t.Fatal("invalid event left busy state or reached provider")
		}
	})
	t.Run("worker_requires_explicit_bound_intent", func(t *testing.T) {
		first := true
		model.proposal = func(int, map[string]any) (string, any) {
			if first {
				first = false
				return "report_finding", map[string]any{"vulnclass": "SYNTHETIC", "severity": "low", "summary": "must not persist without bound intent"}
			}
			return "", nil
		}
		if _, counts, e := bundle.wk.Execute(t.Context(), "worker", tid, nil, task.Store, intent, nil, nil, nil, nil); e != nil || counts.Findings != 0 {
			t.Fatalf("unbound intent report persisted: %+v %v", counts, e)
		}
	})
}
