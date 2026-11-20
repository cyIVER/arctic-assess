package agent

import (
	"context"
	"fmt"
	"time"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/transcript"
)

type nativeFindingKey struct{}
type nativeFindingAuthority struct {
	pg                                                              *db.DB
	task, exploration, intent, finding, node, conversation, version int64
}

// WithNativeReporterFinding is a trusted scheduler boundary. Identity comes from
// committed SQL rows, never a tool-result string, prompt, chat marker or RunInfo.
// A fresh conversation is bound to exactly one committed finding and intent.
func WithNativeReporterFinding(ctx context.Context, pg *db.DB, taskID, nodeID, conversationID int64) (context.Context, error) {
	if pg == nil || ctx.Err() != nil || taskID <= 0 || nodeID <= 0 || conversationID <= 0 {
		return nil, nativeErr
	}
	id, e := pg.FindingIDByNodeID(nodeID)
	if e != nil {
		return nil, nativeErr
	}
	f, e := pg.GetFinding(id)
	if e != nil || f == nil || f.TaskID == nil || f.NodeID == nil || *f.TaskID != taskID || *f.NodeID != nodeID {
		return nil, nativeErr
	}
	task, e := pg.GetTask(taskID)
	if e != nil || task == nil {
		return nil, nativeErr
	}
	a := nativeFindingAuthority{pg: pg, task: taskID, exploration: task.ExplorationID, finding: id, node: nodeID, conversation: conversationID, version: f.EvidenceVersion}
	var count int
	e = pg.QueryRow(`SELECT count(*),COALESCE(min(n.id),0) FROM exploration_edges e JOIN exploration_nodes n ON n.id=e.src_id AND n.exploration_id=e.exploration_id WHERE e.exploration_id=$1 AND e.dst_id=$2 AND e.rel='yields' AND n.kind='intent'`, a.exploration, nodeID).Scan(&count, &a.intent)
	if e != nil || count != 1 || a.validate(ctx) != nil {
		return nil, nativeErr
	}
	return context.WithValue(ctx, nativeFindingKey{}, a), nil
}
func (a nativeFindingAuthority) validate(ctx context.Context) error {
	if ctx.Err() != nil || a.pg == nil {
		return nativeErr
	}
	task, e := a.pg.GetTask(a.task)
	if e != nil || task == nil || task.ExplorationID != a.exploration || task.Status != "running" || task.Paused {
		return nativeErr
	}
	conv, e := a.pg.GetConversation(a.conversation)
	if e != nil || conv == nil || conv.AgentKey != "reporter" {
		return nativeErr
	}
	f, e := a.pg.GetFinding(a.finding)
	if e != nil || f == nil || f.TaskID == nil || f.NodeID == nil || *f.TaskID != a.task || *f.NodeID != a.node || f.EvidenceVersion != a.version {
		return nativeErr
	}
	ts := a.pg.Exploration(a.exploration)
	n, e := ts.GetNode(a.node)
	if e != nil || n == nil || n.Kind != db.KindFinding {
		return nativeErr
	}
	n, e = ts.GetNode(a.intent)
	if e != nil || n == nil || n.Kind != db.KindIntent {
		return nativeErr
	}
	var count int
	if a.pg.QueryRow(`SELECT count(*) FROM exploration_edges WHERE exploration_id=$1 AND src_id=$2 AND dst_id=$3 AND rel='yields'`, a.exploration, a.intent, a.node).Scan(&count) != nil || count != 1 {
		return nativeErr
	}
	return nil
}
func HasNativeReporterFinding(ctx context.Context) bool {
	_, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
	return ok
}
func (p *nativeRPC) bindNativeReporter(ctx context.Context, ri RunInfo, tools []llm.ToolSchema) (context.Context, error) {
	event, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
	phase := p.policy.phase
	if !ok || event.validate(ctx) != nil || phase == nil || phase.state == nil || ri.TaskID != event.task || ri.ExplorationID != event.exploration || ri.IntentID != event.intent || !time.Now().Before(phase.ExpiresAt) || RunInfoFrom(ctx) != ri || transcript.SessionIDFrom(ctx) != fmt.Sprintf("conv-%d", event.conversation) {
		return nil, nativeErr
	}
	for _, r := range phase.Roles {
		if r.Role == "reporter" && r.DynamicFinding {
			hash, e := nativeRoleCatalog(phase, r, tools)
			if e != nil || hash != r.CatalogSHA256 {
				return nil, nativeErr
			}
			r.DynamicFinding = false
			r.IntentID = event.intent
			r.SessionID = fmt.Sprintf("conv-%d", event.conversation)
			ctx = context.WithValue(ctx, nativeRoleAdmissionKey{}, nativeRoleAdmission{phase.state, r, ri})
			if !p.validateNativeRole(ctx, llm.CompletionRequest{Tools: tools}) {
				return nil, nativeErr
			}
			return ctx, nil
		}
	}
	return nil, nativeErr
}
func nativeReporterTemplate(p *nativeRPC) bool {
	if p == nil || p.policy.phase == nil {
		return false
	}
	for _, r := range p.policy.phase.Roles {
		if r.Role == "reporter" && r.DynamicFinding {
			return true
		}
	}
	return false
}

// ValidateNativeDomainInput is shared by original server domain handlers, after
// decoration/defaults. It does not itself grant authority.
func ValidateNativeDomainInput(ctx context.Context, name string, schema map[string]any, raw []byte) error {
	return nativeDomainInput(ctx, name, schema, raw)
}

func NativeReporterTaskID(ctx context.Context) (int64, bool) {
	a, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
	return a.task, ok
}
