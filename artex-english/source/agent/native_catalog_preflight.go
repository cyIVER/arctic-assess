package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
	"io"
	"net/url"
	"strings"
)

type NativeCatalogGlobal struct {
	Format   string `json:"format"`
	Model    string `json:"model"`
	Endpoint string `json:"endpoint"`
}
type NativeCatalogRequest struct {
	TaskID          int64               `json:"task_id"`
	ExplorationID   int64               `json:"exploration_id"`
	ExecutorID      string              `json:"executor_id"`
	NetworkPolicyID string              `json:"network_policy_id"`
	FixtureOrigin   string              `json:"fixture_origin"`
	ExpectedGlobal  NativeCatalogGlobal `json:"expected_global"`
}
type NativeCatalogRole struct {
	Role           string            `json:"role"`
	AgentID        int64             `json:"agent_id"`
	CatalogSHA256  string            `json:"catalog_sha256"`
	Tools          []llm.ToolSchema  `json:"tools"`
	ToolBindingIDs map[string]string `json:"tool_binding_ids"`
}
type NativeCatalogResult struct {
	Provenance      string              `json:"provenance"`
	Isolation       string              `json:"isolation"`
	SchemaVersion   int                 `json:"schema_version"`
	TaskID          int64               `json:"task_id"`
	ExplorationID   int64               `json:"exploration_id"`
	Database        string              `json:"database"`
	ReadOnly        bool                `json:"read_only"`
	Source          string              `json:"source"`
	Admission       bool                `json:"native_admission"`
	Global          NativeCatalogGlobal `json:"global"`
	ExecutorID      string              `json:"executor_id"`
	NetworkPolicyID string              `json:"network_policy_id"`
	FixtureOrigin   string              `json:"fixture_origin"`
	Roles           []NativeCatalogRole `json:"roles"`
}

// RunNativeCatalogPreflight is the one-shot CLI seam. It does not construct a
// Server, Manager or provider. The global argument is selected by the normal
// configuration reader, not by request data. ExpectedGlobal is an equality gate.
func RunNativeCatalogPreflight(ctx context.Context, pg *db.DB, global Config, input io.Reader, output io.Writer) error {
	var req NativeCatalogRequest
	dec := json.NewDecoder(io.LimitReader(input, 65537))
	dec.DisallowUnknownFields()
	if dec.Decode(&req) != nil || dec.Decode(new(any)) != io.EOF {
		return fmt.Errorf("invalid catalog metadata")
	}
	expected := NativeCatalogGlobal{Format: global.Provider(), Model: global.Model, Endpoint: global.BaseURL}
	u, e := url.Parse(req.FixtureOrigin)
	if e != nil || u.Scheme != "http" || u.Hostname() == "" || u.User != nil || u.Path != "" || u.RawQuery != "" || u.Fragment != "" || u.String() != req.FixtureOrigin || req.TaskID <= 0 || req.ExplorationID <= 0 || !global.NativeCatalogSourceValid() || req.ExpectedGlobal != expected {
		return fmt.Errorf("catalog source or metadata mismatch")
	}
	available, sourceErr := pg.NativeGlobalSourceAvailable()
	if sourceErr != nil || !available {
		return fmt.Errorf("native global source unavailable")
	}
	task, e := pg.GetTask(req.TaskID)
	if e != nil || task == nil || task.ExplorationID != req.ExplorationID || task.Status != "running" || task.Paused || len(task.LLMProfileIDs) != 0 || task.ActiveLLMProfileID != nil {
		return fmt.Errorf("native global task source unavailable")
	}
	result := NativeCatalogResult{Provenance: "normal-role-factories/DBResolver/final-wrapped-registry", SchemaVersion: 1, TaskID: req.TaskID, ExplorationID: req.ExplorationID, Source: "global-config; agent profile NULL; task chain empty", Global: expected, ExecutorID: req.ExecutorID, NetworkPolicyID: req.NetworkPolicyID, FixtureOrigin: req.FixtureOrigin}
	var ro string
	if e = pg.QueryRow(`SELECT current_database(),current_setting('transaction_read_only'),current_setting('transaction_isolation')`).Scan(&result.Database, &ro, &result.Isolation); e != nil || ro != "on" || result.Isolation != "repeatable read" {
		return fmt.Errorf("read-only catalog transaction required")
	}
	result.ReadOnly = true
	rows, e := pg.ListTools()
	if e != nil {
		return fmt.Errorf("catalog binding rows unavailable")
	}
	byKey := map[string]*db.Tool{}
	for _, row := range rows {
		byKey[row.Key] = row
	}
	// Same production factories; no server startup is needed to construct tools.
	reporter := []actool.CoreTool{ReporterNodeTool(nil), ReporterTrafficTool(nil), ReporterUpdateTool(nil)}
	triggers, e := pg.ListEnabledTriggers()
	if e != nil {
		return fmt.Errorf("reporter trigger unavailable")
	}
	ready := false
	for _, tr := range triggers {
		if tr.AgentKey == "reporter" && (tr.OnFinding || (tr.OnToolCall && catalogContainsFold(tr.ToolNames, "report_finding"))) {
			ready = true
		}
	}
	if !ready {
		return fmt.Errorf("reporter trigger unavailable")
	}
	for _, role := range []string{"goals", "mainagent", "planner", "worker", "reporter"} {
		a, e := pg.GetAgentByKey(role)
		if e != nil || a == nil || !a.Enabled || a.LLMProfileID != nil {
			return fmt.Errorf("native global role source unavailable: %s", role)
		}
		var resolutionFailed bool
		resolve := func(c context.Context, key string, tools []actool.CoreTool) []actool.CoreTool {
			out := ResolveNativeTools(pg, key, tools)
			if len(out) == 0 {
				resolutionFailed = true
			}
			return out
		}
		tools, digest, e := NativePreflightCatalog(ctx, role, req.ExecutorID, req.NetworkPolicyID, pg.Exploration(req.ExplorationID), req.TaskID, reporter, true, resolve)
		if e != nil || resolutionFailed {
			return fmt.Errorf("native catalog resolution failed: %s", role)
		}
		entry := NativeCatalogRole{Role: role, AgentID: a.ID, CatalogSHA256: digest, Tools: tools, ToolBindingIDs: map[string]string{}}
		for _, tool := range tools {
			if row := byKey[tool.Name]; row != nil {
				entry.ToolBindingIDs[tool.Name] = row.Key
			}
		}
		result.Roles = append(result.Roles, entry)
	}
	return json.NewEncoder(output).Encode(result)
}

func catalogContainsFold(values []string, want string) bool {
	for _, v := range values {
		if strings.EqualFold(v, want) {
			return true
		}
	}
	return false
}
