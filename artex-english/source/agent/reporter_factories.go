package agent

import (
	"context"
	"encoding/json"
	"github.com/Autumn-27/norma/permission"
	actool "github.com/Autumn-27/norma/tool"
)

// Reporter factories own metadata for both normal server handlers and preflight.
// A nil handler is schema-only and fails closed if accidentally called.
func reporterBaseTool(readOnly bool, name, desc string, schema map[string]any, run func(context.Context, json.RawMessage) (actool.Result, error)) actool.CoreTool {
	spec := actool.Spec{Name: name, Description: desc, Schema: schema,
		Permissions: func(context.Context, json.RawMessage, permission.Context) permission.Decision {
			return permission.Allowed()
		},
		Run: func(ctx context.Context, in json.RawMessage, _ *actool.ToolContext) (actool.Result, error) {
			if run == nil {
				return actool.Result{}, nativeErr
			}
			if e := ValidateNativeDomainInput(ctx, name, schema, in); e != nil {
				return actool.Result{}, e
			}
			return run(ctx, in)
		}}
	if readOnly {
		spec.ReadOnly = func(json.RawMessage) bool { return true }
		spec.Concurrent = func(json.RawMessage) bool { return true }
	}
	return actool.Build(spec)
}
func reporterStrParam(desc string) map[string]any {
	return map[string]any{"type": "string", "description": desc}
}
func reporterObjSchema(properties map[string]any, required ...string) map[string]any {
	out := map[string]any{"type": "object", "properties": properties}
	if len(required) > 0 {
		req := make([]any, len(required))
		for i, r := range required {
			req[i] = r
		}
		out["required"] = req
	}
	return out
}
func ReporterNodeTool(run func(context.Context, json.RawMessage) (actool.Result, error)) actool.CoreTool {
	return reporterBaseTool(true, "get_task_node_detail",
		"Read complete contents of an exploration node in a specified task (finding/fact/intent/goal: summary plus detail/evidence/PoC). id is the exploration node ID (returned by report_finding or listed as id in list_task_findings). Retrieve the complete evidence before writing a vulnerability report.",
		reporterObjSchema(map[string]any{
			"task_id": reporterStrParam("Task id"),
			"id":      map[string]any{"type": "integer", "description": "Exploration node id (not asset id)"},
		}, "task_id", "id"), run)
}
func ReporterUpdateTool(run func(context.Context, json.RawMessage) (actool.Result, error)) actool.CoreTool {
	return reporterBaseTool(false, "update_finding_report",
		"Write/update a detailed report for a recorded vulnerability (complete Markdown, replacing the old contents). Pass the exploration node id returned by report_finding (the number in \"finding recorded: <id>\") as finding_id. Include overview, impact, reproduction steps, evidence/PoC, and remediation.",
		reporterObjSchema(map[string]any{
			"finding_id":       map[string]any{"type": "integer", "description": "Target finding node id (id returned by report_finding)"},
			"report":           reporterStrParam("Complete detailed report in Markdown"),
			"evidence_version": map[string]any{"type": "integer", "description": "Evidence version returned by get_finding_traffic; prevents saving a report over newer evidence changes"},
		}, "finding_id", "report"), run)
}
func ReporterTrafficTool(run func(context.Context, json.RawMessage) (actool.Result, error)) actool.CoreTool {
	return reporterBaseTool(true, "get_finding_traffic", "Read real traffic evidence bound to a finding, independently of capture settings. Use the independent finding-record ID from report_finding JSON as finding_id (not the exploration node ID on the first line). Omit binding_id initially to retrieve the manifest and version. An empty manifest is normal: for TCP/non-HTTP or uncaptured traffic, write the report from text/command evidence; binding is not mandatory. If bindings exist, read body segments using binding_id, side(request/response), and offset. Pass the version actually read as evidence_version to update_finding_report, whose finding_id still uses the exploration node ID.",
		reporterObjSchema(map[string]any{"finding_id": reporterStrParam("Independent finding-record ID"), "binding_id": reporterStrParam("Binding ID from the manifest; omit to return the manifest"), "side": reporterStrParam("request or response; default response"), "offset": map[string]any{"type": "integer"}, "length": map[string]any{"type": "integer"}}, "finding_id"), run)
}
