package agent

import (
	"context"
	"fmt"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
)

// NativeCatalogSourceValid performs only nonsecret configuration checks. It
// deliberately does not load policy, phase, executor configuration or keys.
func (c Config) NativeCatalogSourceValid() bool {
	return c.Provider() == "codex-native" && c.Model == "gpt-6.1-sol" && nativeEndpoint(c.BaseURL) && !c.Stream && c.MaxTokens == 0 && c.MaxTokensField == "" && c.Proxy == "" && c.APIKey == "" && c.Native == nil && c.ThinkingType == "" && c.ReasoningEffort == "" && c.SessionHeaderKey == ""
}

// NativeRoleBase is also used at each normal native role launcher. Construction
// creates tool values only: it never runs a tool, executor or model.
func (t *ToolSet) NativeRoleBase(role string) []actool.CoreTool {
	switch role {
	case "goals":
		return []actool.CoreTool{t.setGoals(), t.setConstraints()}
	case "mainagent":
		return t.DropCoverageTools(t.MainAgentTools())
	case "planner":
		return t.DropCoverageTools(t.PlannerTools())
	case "worker":
		return append(t.WorkerTools(), nativeexec.Six()...)
	}
	return nil
}

// NativePreflightCatalog derives schemas only. Its private context is discarded;
// no provider, phase state, admission or executable authority is returned.
func NativePreflightCatalog(ctx context.Context, role, executorID, networkID string, store *db.ExplorationStore, taskID int64, reporter []actool.CoreTool, reportingReady bool, resolver func(context.Context, string, []actool.CoreTool) []actool.CoreTool) ([]llm.ToolSchema, string, error) {
	if ctx.Err() != nil || !nativeName.MatchString(executorID) || !nativeName.MatchString(networkID) || store == nil || taskID <= 0 || resolver == nil {
		return nil, "", nativeErr
	}
	ri := RunInfo{TaskID: taskID, ExplorationID: store.ID()}
	// Templates qualify T/E, not a proposed worker intent or reporter event.
	if e := checkNativeTaskMembership(store, ri, "goals"); e != nil {
		return nil, "", e
	}
	ts := NewToolSet(store, role)
	ts.SetTaskID(taskID)
	base := ts.NativeRoleBase(role)
	if role == "reporter" {
		base = reporter
	}
	if len(base) == 0 {
		return nil, "", fmt.Errorf("native role base unavailable")
	}
	ctx = context.WithValue(ctx, nativeTaskScopeKey{}, nativeTaskScope{store: store, run: ri, role: role, reportingReady: reportingReady})
	tools, _, cleanup := augmentTools(ctx, role, base, resolver)
	defer cleanup()
	present := map[string]bool{}
	for _, t := range tools {
		present[t.Name()] = true
	}
	for _, t := range base {
		if nativeRoleAllows(role, t.Name()) && !(t.Name() == "report_finding" && !reportingReady) && !present[t.Name()] {
			return nil, "", fmt.Errorf("native binding unavailable: %s/%s", role, t.Name())
		}
	}
	schemas := actool.NewRegistry(tools...).Schemas()
	digest, e := nativeRoleCatalog(&nativePhasePermit{ExecutorID: executorID, NetworkPolicyID: networkID}, nativePhaseRole{Role: role, Purpose: "run"}, schemas)
	return schemas, digest, e
}
