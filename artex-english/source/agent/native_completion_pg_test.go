//go:build artex_native_pg

package agent

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/nativeexec"
	actool "github.com/Autumn-27/norma/tool"
)

type completionExecutor struct{ calls int }

func (e *completionExecutor) Execute(ctx context.Context, r nativeexec.Request) (actool.Result, error) {
	e.calls++
	if r.Tool != "Read" {
		return actool.Result{}, fmt.Errorf("unexpected tool")
	}
	helper, err := nativeexec.Select("Read")
	if err != nil {
		return actool.Result{}, err
	}
	return helper.Call(ctx, r.Input, &actool.ToolContext{WorkingDir: "."})
}

// Same normal Worker.Execute entrypoint, real exploration/intent, actual SDK
// Read and record_fact. The scripted transport is not inference or isolation.
func TestNativeCompletionWorkerProductionConstructor(t *testing.T) {
	dsn := os.Getenv("ARTEX_TEST_PG_DSN")
	if dsn == "" {
		t.Fatal("approved real PG required")
	}
	d, err := db.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	task, err := d.CreateTask("worker completion fixture", "Read synthetic local evidence", nil, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer d.DeleteTask(task.ID)
	ts := d.Exploration(task.ExplorationID)
	id, err := ts.AddNode(db.KindIntent, map[string]any{"summary": "Read synthetic local evidence"}, 0, "open", "planner", nil)
	if err != nil {
		t.Fatal(err)
	}
	ok, err := ts.ClaimIntent(id, "completion")
	if err != nil || !ok {
		t.Fatal(err)
	}
	intent, err := ts.GetNode(id)
	if err != nil {
		t.Fatal(err)
	}
	oldA, oldR := ToolAugment, ToolResolve
	defer func() { ToolAugment = oldA; ToolResolve = oldR }()
	ToolAugment = nil
	ToolResolve = func(_ context.Context, _ string, base []actool.CoreTool) []actool.CoreTool {
		var out []actool.CoreTool
		for _, v := range base {
			if v.Name() == "Read" || v.Name() == "record_fact" {
				out = append(out, v)
			}
		}
		return out
	}
	set := NewToolSet(ts, "worker")
	set.SetTaskID(task.ID)
	tools := []actool.CoreTool{set.recordFact(), actool.NewRead()}
	dir, phase := rolePermitFixture(t)
	phase["task_id"] = task.ID
	phase["exploration_id"] = task.ExplorationID
	phase["roles"] = []any{map[string]any{"role": "worker", "purpose": "run", "dynamic_intent": true, "intent_id": 0, "session_id": "", "catalog_sha256": roleFixtureDigest(t, phase, "worker", actool.NewRegistry(tools...).Schemas())}}
	writeRolePermit(t, dir, phase)
	policy, _, err := loadRoleFixture(t, dir)
	if err != nil {
		t.Fatal(err)
	}
	cfg := ConfigFrom("codex-native", "gpt-6.1-sol", policy.Endpoint, "", "")
	cfg.Native = policy
	evidence := t.TempDir() + "/synthetic.txt"
	if err = os.WriteFile(evidence, []byte("synthetic evidence; no target observations"), 0600); err != nil {
		t.Fatal(err)
	}
	run := func(withExecutor bool) (int, error) {
		p, e := newNativeRPC(cfg)
		if e != nil {
			t.Fatal(e)
		}
		p.appAdmission = true
		calls := 0
		p.client.Transport = roleRoundTrip(func(req *http.Request) (*http.Response, error) {
			calls++
			body := roleSyntheticResponse
			var input any
			name := ""
			if calls == 1 {
				name = "Read"
				input = map[string]any{"file_path": evidence}
			}
			if calls == 2 {
				name = "record_fact"
				input = map[string]any{"intent_id": id, "summary": "synthetic completion persisted", "confidence": "inferred"}
			}
			if name != "" {
				raw, _ := json.Marshal(map[string]any{"protocol": "artex-native-v1", "profile": "codex-native", "generation_tokens_enforced": false, "message": map[string]any{"role": "assistant", "content": []any{map[string]any{"type": "tool_use", "id": fmt.Sprintf("call_%032x", calls), "name": name, "input": input}}}, "stop_reason": "tool_use", "usage": map[string]int{"input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0}})
				body = string(raw)
			}
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}, nil
		})
		w := NewWorker(p, "gpt-6.1-sol", t.TempDir(), nil, 0, 4)
		ex := &completionExecutor{}
		if withExecutor {
			w.SetNativeExecutor(ex)
		}
		_, counts, e := w.Execute(t.Context(), "worker", task.ID, nil, ts, intent, nil, nil, nil, nil)
		if withExecutor && (calls != 3 || ex.calls != 1 || counts.Facts != 1) {
			t.Fatalf("positive Worker.Execute failed seam: calls=%d executor=%d counts=%+v err=%v", calls, ex.calls, counts, e)
		}
		return calls, e
	}
	if _, err = run(true); err != nil {
		t.Fatalf("same-entrypoint positive: %v", err)
	}
	// Missing config is deliberately a negative control at the real executor seam.
	if n, e := run(false); e == nil || n != 0 {
		t.Fatalf("missing executor admitted: n=%d err=%v", n, e)
	}
	// Desired production behavior: a trusted provider with a reviewed private
	// executor configuration must be usable without manually injecting an executor.
	// This first RED records the absent production installation, not a nil DB.
	socketDir, e := os.MkdirTemp("", "exc-")
	if e != nil {
		t.Fatal(e)
	}
	defer os.RemoveAll(socketDir)
	if e = os.Chmod(socketDir, 0700); e != nil {
		t.Fatal(e)
	}
	socket := filepath.Join(socketDir, "executor.sock")
	listener, e := net.Listen("unix", socket)
	if e != nil {
		t.Fatal(e)
	}
	defer listener.Close()
	key := []byte(strings.Repeat("k", 32))
	finished := make(chan error, 1)
	go func() {
		conn, e := listener.Accept()
		if e != nil {
			finished <- e
			return
		}
		defer conn.Close()
		var n uint32
		if e = binary.Read(conn, binary.BigEndian, &n); e != nil {
			finished <- e
			return
		}
		if n < 32 || n > 65536 {
			finished <- fmt.Errorf("bad frame")
			return
		}
		raw := make([]byte, n)
		if _, e = io.ReadFull(conn, raw); e != nil {
			finished <- e
			return
		}
		mac := hmac.New(sha256.New, key)
		mac.Write(raw[32:])
		if !hmac.Equal(raw[:32], mac.Sum(nil)) {
			finished <- fmt.Errorf("bad HMAC")
			return
		}
		var r nativeexec.Request
		if e = json.Unmarshal(raw[32:], &r); e != nil {
			finished <- e
			return
		}
		if r.Binding.TaskID != task.ID || r.Binding.ExplorationID != task.ExplorationID || r.Binding.IntentID != id {
			finished <- fmt.Errorf("binding drift")
			return
		}
		result, e := (&completionExecutor{}).Execute(t.Context(), r)
		if e != nil {
			finished <- e
			return
		}
		if result.IsError || !strings.Contains(result.Flatten(), "synthetic evidence") {
			finished <- fmt.Errorf("real SDK Read failed: %s", result.Flatten())
			return
		}
		reply, _ := json.Marshal(map[string]any{"version": 1, "result": result})
		binary.Write(conn, binary.BigEndian, uint32(len(reply)))
		_, e = conn.Write(reply)
		finished <- e
	}()
	config := map[string]any{"schema_version": 1, "reviewed": true, "phase_id": phase["phase_id"], "authority_generation": phase["authority_generation"], "task_id": task.ID, "exploration_id": task.ExplorationID, "executor_id": phase["executor_id"], "network_policy_id": phase["network_policy_id"], "fixture_origin": phase["fixture_origin"], "control_socket": socket}
	raw, _ := json.Marshal(config)
	for name, data := range map[string][]byte{"executor.json": raw, "executor.key": key} {
		if e = os.WriteFile(filepath.Join(dir, name), data, 0600); e != nil {
			t.Fatal(e)
		}
		if e = os.Chmod(filepath.Join(dir, name), 0600); e != nil {
			t.Fatal(e)
		}
	}
	policy, _, err = loadRoleFixture(t, dir)
	if err != nil {
		t.Fatal(err)
	}
	cfg.Native = policy
	if n, e := run(false); e != nil || n != 3 {
		t.Fatalf("production constructor has no trusted executor installation: calls=%d err=%v", n, e)
	}
	if e = <-finished; e != nil {
		t.Fatal(e)
	}
}
