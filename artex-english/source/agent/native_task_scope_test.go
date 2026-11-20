package agent

import (
	"context"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
	"testing"
)

type nativeTaskBinder interface {
	BindNativeTaskRole(context.Context, string, RunInfo, *db.ExplorationStore, []llm.ToolSchema) (context.Context, error)
}

func TestNativeTaskBindingRequiresRealStore(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	if _, _, _, err := p.Complete(ctx, r); err != nil || *n != 1 {
		t.Fatalf("valid positive control: %v", err)
	}
	binder, ok := any(p).(nativeTaskBinder)
	if !ok {
		t.Fatal("missing DB-membership task role boundary")
	}
	if _, err := binder.BindNativeTaskRole(ctx, "planner", RunInfoFrom(ctx), nil, r.Tools); err == nil {
		t.Fatal("nil DB admitted")
	}
}
func TestNativeRoleAssemblyNoMCP(t *testing.T) {
	_, _, ctx, _, _ := admittedRoleFixture(t)
	oldA, oldR := ToolAugment, ToolResolve
	defer func() { ToolAugment = oldA; ToolResolve = oldR }()
	aug, res := 0, 0
	ToolAugment = func(context.Context, string) ([]actool.CoreTool, DeferredInfo, func()) {
		aug++
		return nil, DeferredInfo{}, func() {}
	}
	ToolResolve = func(_ context.Context, _ string, b []actool.CoreTool) []actool.CoreTool { res++; return b }
	tools, _, clean := AugmentTools(ctx, "planner", []actool.CoreTool{NewToolSet(nil, "planner").addIntent()})
	clean()
	if len(tools) != 1 || res != 1 {
		t.Fatalf("real enabled-binding resolution bypassed: tools=%d resolves=%d", len(tools), res)
	}
	if aug != 0 {
		t.Fatalf("native role started skill/MCP assembly: calls=%d", aug)
	}
}
