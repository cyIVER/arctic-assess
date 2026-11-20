//go:build artex_native_pg

package server

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestNativePreflightPlannerNormalFactory(t *testing.T) {
	s, f, _ := trafficEvidenceServer(t)
	finding, e := s.m.pg.GetFinding(f.FindingID)
	if e != nil {
		t.Fatal(e)
	}
	task := s.m.ResolveTask(fmt.Sprint(*finding.TaskID))
	if e = s.m.SetTaskStatus(task.ID, "running"); e != nil {
		t.Fatal(e)
	}
	model := &completionModel{proposal: func(n int, _ map[string]any) (string, any) {
		if n == 1 {
			return "add_intent", map[string]any{"summary": "Synthetic preflight normal planner SQL tracer"}
		}
		return "", nil
	}}
	p, cfg, _, _ := completionProvider(t, s, task, []string{"planner"}, model)
	s.llmProv = p
	s.llmCfg = cfg
	s.llmOn = true
	bundle := s.agentsForTask(task)
	if _, _, e = bundle.pl.Plan(t.Context(), *finding.TaskID, nil, task.Store, task.Goal, nil, nil); e != nil {
		t.Fatal(e)
	}
	nodes, e := task.Store.ListByKind(db.KindIntent, 100)
	if e != nil || len(nodes) != 1 || model.calls != 2 {
		t.Fatalf("actual normal planner failed: rows=%d calls=%d err=%v", len(nodes), model.calls, e)
	}
}

type completionRoundTrip func(*http.Request) (*http.Response, error)

func (f completionRoundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestNativeConcurrentCommittedFindingScheduler(t *testing.T) {
	nativeConcurrentFinding(t, "positive")
}
func TestNativeQueuedSourceRevocation(t *testing.T)  { nativeConcurrentFinding(t, "source") }
func TestNativeQueuedCatalogRevocation(t *testing.T) { nativeConcurrentFinding(t, "catalog") }
func nativeConcurrentFinding(t *testing.T, mode string) {
	s, f, _ := trafficEvidenceServer(t)
	initial, e := s.m.pg.GetFinding(f.FindingID)
	if e != nil {
		t.Fatal(e)
	}
	task := s.m.ResolveTask(fmt.Sprint(*initial.TaskID))
	tid := *initial.TaskID
	if e = s.m.SetTaskStatus(task.ID, "running"); e != nil {
		t.Fatal(e)
	}
	id, e := task.Store.AddNode(db.KindIntent, map[string]any{"summary": "Synthetic concurrent reporting"}, 0, "open", "planner", nil)
	if e != nil {
		t.Fatal(e)
	}
	if ok, e := task.Store.ClaimIntent(id, "overlap"); e != nil || !ok {
		t.Fatal(e)
	}
	intent, e := task.Store.GetNode(id)
	if e != nil {
		t.Fatal(e)
	}
	p, cfg, dir, phase := completionProvider(t, s, task, []string{"worker", "reporter"}, &completionModel{})
	raw, _ := json.Marshal(map[string]any{"schema_version": 1, "reviewed": true, "phase_id": phase["phase_id"], "authority_generation": phase["authority_generation"], "task_id": tid, "exploration_id": task.ExpID, "executor_id": phase["executor_id"], "network_policy_id": phase["network_policy_id"], "fixture_origin": phase["fixture_origin"], "control_socket": dir + "/control.sock"})
	completionWrite(t, dir, "executor.json", raw)
	completionWrite(t, dir, "executor.key", []byte("kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"))
	s.llmCfg = cfg
	s.llmProv = p
	s.llmOn = true
	s.chatAgent = agent.NewChatAgent(p, cfg.Model, s.m.dir, nil, 0)
	ctx, cancel := context.WithCancel(context.Background())
	s.ctx = ctx
	defer cancel()
	blocked := make(chan struct{})
	release := make(chan struct{})
	workerDone := make(chan error, 1)
	var workerCalls, reporterCalls atomic.Int32
	var findingNode, version int64
	response := func(name string, input any) *http.Response {
		content := []any{map[string]any{"type": "text", "text": "Synthetic concurrent qualification only"}}
		stop := "end_turn"
		if name != "" {
			content = []any{map[string]any{"type": "tool_use", "id": "call_00000000000000000000000000000001", "name": name, "input": input}}
			stop = "tool_use"
		}
		body, _ := json.Marshal(map[string]any{"protocol": "artex-native-v1", "profile": "codex-native", "generation_tokens_enforced": false, "message": map[string]any{"role": "assistant", "content": content}, "stop_reason": stop, "usage": map[string]int{"input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0}})
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(string(body)))}
	}
	agent.NativePGFixtureTransport(p, completionRoundTrip(func(r *http.Request) (*http.Response, error) {
		var req struct {
			Tools []struct {
				Name string `json:"name"`
			} `json:"tools"`
		}
		if e := json.NewDecoder(r.Body).Decode(&req); e != nil {
			return nil, e
		}
		worker := false
		for _, tool := range req.Tools {
			if tool.Name == "Read" {
				worker = true
			}
		}
		if worker {
			n := workerCalls.Add(1)
			if n == 1 {
				return response("report_finding", map[string]any{"intent_id": id, "vulnclass": "SYNTHETIC", "severity": "low", "summary": "Synthetic asynchronous finding", "evidence": "No assessment observations"}), nil
			}
			close(blocked)
			select {
			case <-release:
			case <-r.Context().Done():
				return nil, r.Context().Err()
			}
			return response("", nil), nil
		}
		n := reporterCalls.Add(1)
		if n == 1 {
			return response("update_finding_report", map[string]any{"finding_id": findingNode, "evidence_version": version, "report": "# Synthetic concurrent report\n\nNo assessment observations. Remediation: synthetic only."}), nil
		}
		return response("", nil), nil
	}))
	bundle := s.agentsForTask(task)
	go func() {
		_, counts, e := bundle.wk.Execute(ctx, "worker", tid, nil, task.Store, intent, nil, nil, nil, nil)
		if e == nil && counts.Findings != 1 {
			e = fmt.Errorf("finding count=%d", counts.Findings)
		}
		workerDone <- e
	}()
	select {
	case <-blocked:
	case <-time.After(5 * time.Second):
		cancel()
		t.Fatal("worker second model request never blocked")
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
	row, e := s.m.pg.FindingIDByNodeID(findingNode)
	if e != nil {
		t.Fatal(e)
	}
	persisted, e := s.m.pg.GetFinding(row)
	if e != nil {
		t.Fatal(e)
	}
	version = persisted.EvidenceVersion
	triggers, e := s.m.pg.ListEnabledTriggers()
	if e != nil {
		t.Fatal(e)
	}
	s.m.pg.SetSchedState(schedKeyLastFinding, fmt.Sprint(findingNode-1))
	newScheduler(s).fireFindings(triggers)
	// The real scheduler starts a reporter conversation while Worker remains in HTTP.
	time.Sleep(150 * time.Millisecond)
	if reporterCalls.Load() != 0 {
		t.Error("concurrent phase HTTP escaped single-inflight limit")
	}
	if mode == "source" {
		s.cfgMu.Lock()
		s.llmOn = false
		s.cfgMu.Unlock()
	}
	if mode == "catalog" {
		old, e := s.m.pg.GetTool("update_finding_report")
		if e != nil {
			t.Fatal(e)
		}
		defer s.m.pg.Exec(`UPDATE tools SET description=$1 WHERE key='update_finding_report'`, old.Description)
		s.m.pg.Exec(`UPDATE tools SET description=description || ' QUEUED DRIFT' WHERE key='update_finding_report'`)
	}
	close(release)
	select {
	case e := <-workerDone:
		if e != nil {
			t.Error(e)
		}
	case <-time.After(5 * time.Second):
		cancel()
		t.Fatal("worker did not settle")
	}
	deadline := time.Now().Add(3 * time.Second)
	for {
		persisted, e = s.m.pg.GetFinding(row)
		if e != nil {
			t.Fatal(e)
		}
		s.queueMu.Lock()
		active := s.triggerActive["reporter"]
		s.queueMu.Unlock()
		if active == 0 {
			break
		}
		if time.Now().After(deadline) {
			cancel()
			t.Fatal("reporter did not settle")
		}
		time.Sleep(10 * time.Millisecond)
	}
	if mode != "positive" {
		if persisted.Report != "" || reporterCalls.Load() != 0 {
			t.Fatalf("queued %s revocation reached HTTP/report: calls=%d saved=%v", mode, reporterCalls.Load(), persisted.Report != "")
		}
		return
	}
	if persisted.Report == "" || reporterCalls.Load() != 2 {
		t.Fatalf("phase busy lost real asynchronous reporter: worker=%d reporter=%d reportSaved=%v", workerCalls.Load(), reporterCalls.Load(), persisted.Report != "")
	}
	t.Logf("actual committed SQL finding %d, scheduler reporter, serialized worker=%d reporter=%d", findingNode, workerCalls.Load(), reporterCalls.Load())
}
