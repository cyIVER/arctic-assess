package server

import (
	"context"
	"fmt"
	"strconv"

	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	actool "github.com/Autumn-27/norma/tool"
)

// Only this deliberately narrow original-domain surface is exposed to native
// reporting. No SDK effects, global asset registry, MCP or platform management.
func (s *Server) nativeReporterTools() []actool.CoreTool {
	return []actool.CoreTool{s.toolGetTaskNodeDetail(), s.toolGetFindingTraffic(), s.toolUpdateFindingReport()}
}
func (r *taskLLMRuntime) NativeReportingReady(ctx context.Context) bool {
	if ctx.Err() != nil || r.s == nil || r.s.m == nil || r.s.m.pg == nil {
		return false
	}
	pg := r.s.m.pg
	a, e := pg.GetAgentByKey("reporter")
	if e != nil || a == nil || !a.Enabled {
		return false
	}
	// Resolving the reporter source is read-only here. Invalid explicit profiles
	// deny instead of silently borrowing the worker/global profile.
	source := &taskLLMRuntime{s: r.s, taskID: r.taskID, agentKey: "reporter"}
	selection, e := source.current()
	if e != nil || !nativeTaskSelection(selection) {
		return false
	}
	for _, name := range []string{"get_task_node_detail", "get_finding_traffic", "update_finding_report"} {
		t, e := pg.GetTool(name)
		if e != nil || t == nil || !t.Enabled || !contains(t.Agents, "reporter") {
			return false
		}
	}
	triggers, e := pg.ListEnabledTriggers()
	if e != nil {
		return false
	}
	for _, tr := range triggers {
		if tr.AgentKey == "reporter" && (tr.OnFinding || (tr.OnToolCall && containsFold(tr.ToolNames, "report_finding"))) {
			return true
		}
	}
	return false
}
func (sc *Scheduler) nativeReporterEvent(tr *db.AgentTrigger, e db.TaskEvent) bool {
	if tr.AgentKey != "reporter" {
		return false
	}
	r := &taskLLMRuntime{s: sc.s, taskID: strconv.FormatInt(e.TaskID, 10), agentKey: "reporter"}
	selection, err := r.current()
	if err != nil {
		return true
	} // invalid source never enters legacy chat
	if !nativeTaskSelection(selection) {
		return false
	}
	if !r.NativeReportingReady(sc.s.ctx) {
		return true
	}
	// Queue the committed DB event itself. Report identity never crosses a text
	// parser and must not be coalesced into another finding/task's conversation.
	sc.s.startTriggeredRun(triggeredRun{agentKey: "reporter", title: fmt.Sprintf("finding 触发 · task#%d", e.TaskID), message: tr.FindingMessage + tr.ToolCallMessage, taskID: e.TaskID, taskDesc: e.TaskDesc, taskGoal: e.TaskGoal, findingNodeID: e.NodeID})
	return true
}
func (sc *Scheduler) nativeReporterTask(taskID int64) bool {
	selection, e := (&taskLLMRuntime{s: sc.s, taskID: strconv.FormatInt(taskID, 10), agentKey: "reporter"}).current()
	return e != nil || nativeTaskSelection(selection)
}

// qualifyNativeFindingConversation binds T/E/I/F(row)/F(node)/C from SQL after
// CreateConversation, and before provider construction or any model call.
func (s *Server) qualifyNativeFindingConversation(item triggeredRun, c *db.Conversation) (context.Context, error) {
	if c.AgentKey != "reporter" || item.findingNodeID <= 0 {
		return nil, fmt.Errorf("native reporter event unavailable")
	}
	return agent.WithNativeReporterFinding(s.ctx, s.m.pg, item.taskID, item.findingNodeID, c.ID)
}
