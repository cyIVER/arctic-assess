//go:build artex_native_pg

package agent

import (
	"context"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
	"syscall"
)

// NewNativePGFixtureProvider exists ONLY in the opt-in local PG qualification
// build. Production has no directory override and always uses nativeRuntimeDir.
func NewNativePGFixtureProvider(dir string, c Config) (llm.Provider, error) {
	policy, e := loadNativePolicyForConfig(dir, c, syscall.Openat)
	if e != nil {
		return nil, e
	}
	c.Native = policy
	c.BaseURL = policy.Endpoint
	p, e := newNativeRPC(c)
	if e != nil {
		return nil, e
	}
	p.appAdmission = true
	return p, nil
}

func NativePGFixtureCatalog(phaseJSON []byte, role string, tools []llm.ToolSchema) (string, error) {
	var p nativePhasePermit
	if e := strictNativeJSON(phaseJSON, &p); e != nil {
		return "", e
	}
	return nativeRoleCatalog(&p, nativePhaseRole{Role: role, Purpose: "run"}, tools)
}

func NativePGFixtureSchemas(role string, ts *db.ExplorationStore, taskID int64, reporting ...bool) []llm.ToolSchema {
	set := NewToolSet(ts, role)
	set.SetTaskID(taskID)
	var base []actool.CoreTool
	switch role {
	case "goals":
		base = []actool.CoreTool{set.setGoals(), set.setConstraints()}
	case "mainagent":
		base = set.DropCoverageTools(set.MainAgentTools())
	case "worker":
		base = append(set.WorkerTools(), nativeexec.Six()...)
	case "planner":
		base = set.DropCoverageTools(set.PlannerTools())
	}
	ctx := context.WithValue(context.Background(), nativeTaskScopeKey{}, nativeTaskScope{role: role, reportingReady: len(reporting) > 0 && reporting[0]})
	tools, _, clean := AugmentTools(ctx, role, base)
	defer clean()
	return actool.NewRegistry(tools...).Schemas()
}
