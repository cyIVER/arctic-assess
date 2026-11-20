package agent

import (
	"context"
	"encoding/json"
	"github.com/Autumn-27/artex/db"
	actool "github.com/Autumn-27/norma/tool"
	"testing"
)

func TestNativeCoreAssemblyNeverCallsController(t *testing.T) {
	p, _, _, _, _ := admittedRoleFixture(t)
	calls := 0
	core := actool.Build(actool.Spec{Name: "Bash", Schema: actool.NewBash().InputSchema(), Run: func(context.Context, json.RawMessage, *actool.ToolContext) (actool.Result, error) {
		calls++
		return actool.Text("synthetic control"), nil
	}})
	if _, err := core.Call(context.Background(), json.RawMessage(`{"command":"synthetic"}`), nil); err != nil || calls != 1 {
		t.Fatal("positive handler control failed")
	}
	ctx := context.WithValue(context.Background(), nativeRoleAdmissionKey{}, nativeRoleAdmission{state: p.policy.phase.state, role: nativePhaseRole{Role: "worker"}})
	oldA, oldR := ToolAugment, ToolResolve
	ToolAugment = nil
	ToolResolve = func(_ context.Context, _ string, b []actool.CoreTool) []actool.CoreTool { return b }
	defer func() { ToolAugment = oldA; ToolResolve = oldR }()
	tools, _, clean := AugmentTools(ctx, "worker", []actool.CoreTool{core})
	defer clean()
	if len(tools) != 1 {
		t.Fatal("missing isolated candidate")
	}
	if _, err := tools[0].Call(ctx, json.RawMessage(`{"command":"synthetic"}`), nil); err == nil || calls != 1 {
		t.Fatalf("controller fallback reached: calls=%d err=%v", calls, err)
	}
}

func TestNativeDomainCallRequiresDBScope(t *testing.T) {
	_, _, ctx, _, _ := admittedRoleFixture(t)
	calls := 0
	domain := writeTool("add_intent", "synthetic guard control", obj(map[string]any{}), func(context.Context, json.RawMessage) (actool.Result, error) {
		calls++
		return actool.Text("synthetic"), nil
	})
	if _, err := domain.Call(context.Background(), json.RawMessage(`{}`), nil); err != nil || calls != 1 {
		t.Fatal("positive legacy handler control failed")
	}
	if _, err := domain.Call(ctx, json.RawMessage(`{}`), nil); err == nil || calls != 1 {
		t.Fatal("native handler ran without live DB membership")
	}
}

func TestNativeMainRejectsMissingDBBeforePreparation(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	if _, _, _, err := p.Complete(ctx, r); err != nil || *n != 1 {
		t.Fatalf("positive provider: %v", err)
	}
	defer func() {
		if v := recover(); v != nil {
			t.Fatalf("native main reached preparation before DB denial: %v", v)
		}
	}()
	m := NewMainAgent(p, "gpt-6.1-sol", t.TempDir(), nil, 0, 1)
	if _, err := m.Chat(context.Background(), 21, 0, nil, nil, "synthetic task", "synthetic", nil, nil, nil, nil, nil); err == nil {
		t.Fatal("missing DB scope accepted")
	}
	if *n != 1 {
		t.Fatal("missing DB reached provider")
	}
}

func TestNativeRoleMissingBindingResolverDeniesCatalog(t *testing.T) {
	_, _, ctx, _, _ := admittedRoleFixture(t)
	oldR := ToolResolve
	defer func() { ToolResolve = oldR }()
	base := []actool.CoreTool{NewToolSet(nil, "planner").addIntent()}
	ToolResolve = func(_ context.Context, _ string, b []actool.CoreTool) []actool.CoreTool { return b }
	positive, _, cl := AugmentTools(ctx, "planner", base)
	cl()
	if len(positive) != 1 {
		t.Fatal("positive binding control failed")
	}
	ToolResolve = nil
	denied, _, cl := AugmentTools(ctx, "planner", base)
	cl()
	if len(denied) != 0 {
		t.Fatal("native assembled tools without an enabled-binding resolver")
	}
}

func TestNativePlannerRejectsMissingDBBeforePreparation(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	if _, _, _, err := p.Complete(ctx, r); err != nil || *n != 1 {
		t.Fatalf("positive provider: %v", err)
	}
	defer func() {
		if v := recover(); v != nil {
			t.Fatalf("native planner reached legacy preparation before missing DB denial: %v", v)
		}
	}()
	pl := NewPlanner(p, "gpt-6.1-sol", t.TempDir(), nil, 0, 1)
	if _, _, err := pl.Plan(context.Background(), 21, nil, nil, "synthetic task", nil, nil); err == nil {
		t.Fatal("missing DB scope accepted")
	}
	if *n != 1 {
		t.Fatal("missing DB reached provider")
	}
}
func TestNativePlannerCatalogDropsHostTools(t *testing.T) {
	_, _, ctx, _, _ := admittedRoleFixture(t)
	oldA, oldR := ToolAugment, ToolResolve
	ToolAugment = nil
	ToolResolve = func(_ context.Context, _ string, b []actool.CoreTool) []actool.CoreTool { return b }
	defer func() { ToolAugment = oldA; ToolResolve = oldR }()
	tools, _, clean := AugmentTools(ctx, "planner", []actool.CoreTool{NewToolSet(nil, "planner").addIntent(), actool.NewBash()})
	defer clean()
	if len(tools) != 1 || tools[0].Name() != "add_intent" {
		t.Fatal("planner native catalog retained host-executed core tools")
	}
}
func TestNativeWorkerNoExecutorBeforePreparation(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	if _, _, _, err := p.Complete(ctx, r); err != nil || *n != 1 {
		t.Fatalf("positive provider: %v", err)
	}
	defer func() {
		if v := recover(); v != nil {
			t.Fatalf("worker prepared before isolated executor admission: %v", v)
		}
	}()
	w := NewWorker(p, "gpt-6.1-sol", t.TempDir(), nil, 0, 1)
	if _, _, err := w.Execute(context.Background(), "worker", 21, nil, nil, &db.Node{ID: 999, Kind: "intent", State: "running"}, nil, nil, nil, nil); err == nil {
		t.Fatal("worker without isolated executor accepted")
	}
	if *n != 1 {
		t.Fatal("worker without executor reached provider")
	}
}
