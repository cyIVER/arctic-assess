package nativeexec

import (
	"context"
	"encoding/json"
	"github.com/Autumn-27/norma/tool"
	"reflect"
	"testing"
)

type spyTool struct {
	tool.CoreTool
	calls *int
}

func (s spyTool) Call(context.Context, json.RawMessage, *tool.ToolContext) (tool.Result, error) {
	*s.calls++
	panic("HOST CALL")
}

type execSpy struct {
	calls   int
	request Request
}

func (s *execSpy) Execute(_ context.Context, r Request) (tool.Result, error) {
	s.calls++
	s.request = r
	return tool.Text("isolated"), nil
}
func binding(context.Context) (Binding, error) {
	return Binding{PhaseID: "phase", Generation: 1, TaskID: 1, ExplorationID: 2, IntentID: 3, Role: "worker", SessionID: "session", ExecutorID: "executor", NetworkPolicyID: "fixture"}, nil
}
func TestAdapterDispatchPreservesSchemaNeverHost(t *testing.T) {
	for _, original := range []tool.CoreTool{tool.NewRead(), tool.NewWrite(), tool.NewEdit(), tool.NewLS(), tool.NewBash(), tool.NewSleep()} {
		n := 0
		s := &execSpy{}
		w := Wrap(spyTool{original, &n}, binding, s)
		if !reflect.DeepEqual(w.InputSchema(), original.InputSchema()) || w.Name() != original.Name() || w.Prompt() != original.Prompt() || w.Description() != original.Description() {
			t.Fatal("schema changed")
		}
	}
	n := 0
	s := &execSpy{}
	w := Wrap(spyTool{tool.NewRead(), &n}, binding, s)
	r, e := w.Call(context.Background(), json.RawMessage(`{"file_path":"safe"}`), &tool.ToolContext{WorkingDir: "/controller-secret", Env: []string{"CANARY=secret"}, ToolUseID: "use-1"})
	if e != nil || r.Flatten() != "isolated" || s.calls != 1 || n != 0 || s.request.ToolUseID != "use-1" || s.request.Binding.IntentID != 3 {
		t.Fatalf("bad dispatch: %+v %v", r, e)
	}
}
func TestAdapterRejectsFinalMalformedAndHardDeny(t *testing.T) {
	s := &execSpy{}
	n := 0
	w := Wrap(spyTool{tool.NewBash(), &n}, binding, s)
	for _, in := range []string{`{"command":"true","alien":1}`, `{"command":"true","command":"false"}`, `{"command":"true","run_in_background":true}`, `{"command":"rm -rf /"}`, `{"command":"true"} {}`, `null`} {
		if _, e := w.Call(context.Background(), json.RawMessage(in), nil); e == nil {
			t.Errorf("admitted %s", in)
		}
	}
	if s.calls != 0 || n != 0 {
		t.Fatal("rejection dispatched")
	}
}
func TestAdapterFailClosedBinding(t *testing.T) {
	s := &execSpy{}
	w := Wrap(tool.NewRead(), func(context.Context) (Binding, error) { return Binding{}, nil }, s)
	if _, e := w.Call(context.Background(), json.RawMessage(`{"file_path":"safe"}`), nil); e == nil || s.calls != 0 {
		t.Fatal("empty authority admitted")
	}
}
