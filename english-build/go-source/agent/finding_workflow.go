package agent

import (
	"encoding/json"
	"fmt"

	"github.com/Autumn-27/artex/db"
	actool "github.com/Autumn-27/norma/tool"
)

const findingIDGuidance = "\n\n**Finding ID contract**: finding_id is the independent finding-record ID; finding_node_id is the exploration node ID. The id returned by list_findings / list_task_findings / node_detail / get_task_node_detail remains an exploration node ID; read the independent ID from finding_id in the same result. get_finding_traffic / bind_finding_traffic use the independent finding_id. The legacy update_finding_report finding_id argument still takes finding_node_id. Do not use the number on the first line of report_finding with evidence tools, or guess other numbers after an ID error."

// The server supplies the persisted setting. A missing setting/host is off.
// Consulted at assembly and again on writes so an already-running session
// cannot keep binding after the user switches the feature off.
var FindingTrafficBindingEnabled func() bool

func findingTrafficBindingEnabled() bool {
	return FindingTrafficBindingEnabled != nil && FindingTrafficBindingEnabled()
}

// Applied after ToolResolve: user descriptions and prompts remain intact, while
// all actual reporters (including Planner and custom chat agents) see the same
// API contract. Disabled/unbound tools are never reintroduced here.
func findingWorkflowTools(agentKey string, tools []actool.CoreTool) ([]actool.CoreTool, string) {
	if !findingTrafficBindingEnabled() {
		out := make([]actool.CoreTool, 0, len(tools))
		for _, tool := range tools {
			if tool.Name() == "bind_finding_traffic" {
				continue
			}
			if agentKey == "reporter" && (tool.Name() == "traffic_search" || tool.Name() == "traffic_get" || tool.Name() == "traffic_blob") {
				continue
			}
			switch tool.Name() {
			case "report_finding", "add_hint", "add_task_hint":
				// Work on a copy: toggling back on must restore the original schema.
				raw, _ := json.Marshal(tool.InputSchema())
				var schema map[string]any
				if json.Unmarshal(raw, &schema) == nil {
					stripTrafficParameters(schema)
					tool = DecorateTool(tool, tool.Description(), schema)
				}
			}
			out = append(out, tool)
		}
		return out, ""
	}
	out := append([]actool.CoreTool(nil), tools...)
	has := map[string]bool{}
	for i, tool := range out {
		has[tool.Name()] = true
		note := ""
		switch tool.Name() {
		case "report_finding":
			note = "\nBy default, the reporting agent verifies and binds traffic before writing the report. The reporter should retain verification commands, key output, existing real traffic IDs and their purpose in evidence so the reporting agent can check them against execution traces. Do not query extra packets merely for binding. Explicit immediate binding remains supported: traffic_refs or evidence_hint_id may carry verified references; the latter reads structured references from the specified hint in this task. If any reference is invalid, the entire report_finding call fails. TCP/no-packet cases do not require these optional arguments. Returned finding_id and finding_node_id identify the independent record and exploration node respectively."
		case "add_hint", "add_task_hint":
			note = "\nWhen handing off a confirmed vulnerability, preserve verified traffic IDs, roles, notes, and order in the corresponding hint traffic_refs (top-level for a single hint, in the corresponding hints element for a batch), and describe the specific vulnerability it proves in text. Do not hand off only prose while discarding existing traffic references. Unverified candidates must not be passed as evidence."
		case "get_finding_traffic", "bind_finding_traffic", "list_findings", "list_task_findings", "node_detail", "get_task_node_detail", "update_finding_report":
			note = findingIDGuidance
		}
		if note != "" {
			out[i] = DecorateTool(tool, tool.Description()+note, tool.InputSchema())
		}
	}
	guidance := ""
	if has["report_finding"] || has["add_task_hint"] || has["add_hint"] {
		guidance = "\n\n**Traffic evidence handoff (optional)**: by default, the reporting agent performs automatic binding after the finding is recorded and before writing its report. Retain verification commands, key output, existing real traffic IDs and their purpose in evidence; include intent_id in task context for traceability. Do not query extra packets merely for binding. Auto / Planner reporting on behalf of an executor must retain existing references. add_hint / add_task_hint can hand off traffic_refs; explicit immediate binding remains compatible with report_finding traffic_refs / evidence_hint_id. Record TCP/no-packet cases normally. Never guess IDs or repeat probes solely to obtain packets."
		if has["add_task_hint"] && !has["add_hint"] {
			guidance += "\nFor platform chat without task context, do not call report_finding directly. Hand off to the corresponding existing task with add_task_hint, let its task agent record the finding, and verify the result with list_task_findings."
		}
		if has["prove_goal"] || has["goal_met"] {
			guidance += "\nBefore declaring goals complete, finish reporting/handing off existing evidence from this run. Do not end the task or cancel workers merely because a text finding is recorded while evidence handoff remains incomplete. No-packet cases do not require waiting or forced capture."
		}
	}
	if has["update_finding_report"] && has["bind_finding_traffic"] && has["get_finding_traffic"] {
		guidance += "\n\n**Automatic traffic association before reporting (enabled)**: verify and bind traffic for this triggered finding, then write the report. First obtain explicit finding_id and finding_node_id from report_finding JSON or get_task_node_detail / list_task_findings. Read the finding detail, corresponding intent execution trace, and existing evidence manifest, prioritizing real IDs handed off by the reporter. If verification was HTTP and traffic tools are available, filter candidates with traffic_search and verify each request/response supports the finding with traffic_get; domain and time only filter candidates, not prove ownership. Bind confirmed evidence in reproduction order with bind_finding_traffic(finding_id, traffic_refs), choosing baseline / proof / verification / supporting and explaining its purpose. Operate only on this finding: do not create duplicate findings or probe the target again. After successful binding, reread get_finding_traffic for the latest version, read the required bodies, and pass the version actually read as evidence_version to update_finding_report (whose finding_id still takes finding_node_id). Do not append existing bindings again. For TCP, uncaptured traffic, unavailable tools, or no exact match, skip automatic binding and write normally from text/command evidence, explaining why. Never guess to fill traffic gaps. Do not claim binding succeeded if it failed; retain existing evidence and explain missing bindings in the report."
	}
	if guidance != "" || has["get_finding_traffic"] || has["update_finding_report"] {
		guidance += findingIDGuidance
	}
	return out, guidance
}

func stripTrafficParameters(schema map[string]any) {
	props, _ := schema["properties"].(map[string]any)
	delete(props, "traffic_refs")
	delete(props, "evidence_hint_id")
	if required, ok := schema["required"].([]any); ok {
		kept := required[:0]
		for _, key := range required {
			if key != "traffic_refs" && key != "evidence_hint_id" {
				kept = append(kept, key)
			}
		}
		schema["required"] = kept
	}
	if hints, ok := props["hints"].(map[string]any); ok {
		if items, ok := hints["items"].(map[string]any); ok {
			stripTrafficParameters(items)
		}
	}
}

// HintTrafficSchema is shared by the task-local and cross-task hint tools.
func HintTrafficSchema() map[string]any {
	return map[string]any{"type": "array", "description": "Optional: verified traffic references supporting the specific vulnerability in this hint, preserving order. After handoff, report_finding can carry these references via evidence_hint_id.", "items": obj(map[string]any{"traffic_id": str("Real traffic ID"), "role": str("baseline / proof / verification / supporting"), "note": str("What conclusion this traffic supports")}, "traffic_id")}
}

func (t *ToolSet) findingRefsFromHint(hintID int64, explicit []db.TrafficRef) ([]db.TrafficRef, error) {
	if hintID <= 0 {
		return db.NormalizeTrafficRefs(explicit)
	}
	n, err := t.ts.GetNode(hintID) // local store only: inherited hints cannot supply evidence
	if err != nil {
		return nil, err
	}
	if n == nil || n.Kind != db.KindHint {
		return nil, fmt.Errorf("evidence_hint_id=%d must identify a hint node in this task (inherited hints cannot be used directly for binding)", hintID)
	}
	var payload struct {
		Refs []db.TrafficRef `json:"traffic_refs"`
	}
	if err := json.Unmarshal(n.Payload, &payload); err != nil {
		return nil, err
	}
	return db.NormalizeTrafficRefs(append(append([]db.TrafficRef{}, explicit...), payload.Refs...))
}
