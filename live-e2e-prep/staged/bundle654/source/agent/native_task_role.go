package agent

import (
	"context"
	"fmt"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/harness"
	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
	"reflect"
)

// nativeTaskScope exists only after a live exploration-to-task check. It is not
// constructible from RunInfo, a chat marker, prompt text or model arguments.
type nativeTaskScope struct {
	provider       *nativeRPC
	store          *db.ExplorationStore
	run            RunInfo
	role           string
	executor       nativeexec.Executor
	validate       func(context.Context, string) error
	reportingReady bool
}
type nativeTaskScopeKey struct{}

func checkNativeTaskMembership(ts *db.ExplorationStore, ri RunInfo, role string) error {
	if ts == nil || ri.TaskID <= 0 || ri.ExplorationID != ts.ID() || ri.SessionID != "" {
		return nativeErr
	}
	taskID, err := ts.TaskID()
	if err != nil || taskID != ri.TaskID {
		return nativeErr
	}
	// Inherited contexts are not a wildcard. Native source-task inheritance needs
	// an explicit reviewed policy; reject it before any normal support assembly.
	sources, err := ts.DirectSourceStores()
	if err != nil || len(sources) != 0 {
		return nativeErr
	}
	if role == "worker" {
		if ri.IntentID <= 0 {
			return nativeErr
		}
		node, err := ts.GetNode(ri.IntentID)
		if err != nil || node == nil || node.Kind != "intent" || node.State != "running" {
			return nativeErr
		}
	} else if role == "reporter" {
		if ri.IntentID <= 0 {
			return nativeErr
		}
		n, e := ts.GetNode(ri.IntentID)
		if e != nil || n == nil || n.Kind != db.KindIntent {
			return nativeErr
		}
	} else if ri.IntentID != 0 {
		return nativeErr
	}
	return nil
}

// BindNativeTaskRole is the DB-backed host launch boundary. Dynamic worker
// templates cannot be used by BindNativeRole; only this path mints a child run.
func (p *nativeRPC) BindNativeTaskRole(ctx context.Context, role string, ri RunInfo, ts *db.ExplorationStore, tools []llm.ToolSchema) (context.Context, error) {
	if err := checkNativeTaskMembership(ts, ri, role); err != nil {
		return nil, err
	}
	phase := p.policy.phase
	if phase == nil || phase.TaskID != ri.TaskID || phase.ExplorationID != ri.ExplorationID {
		return nil, nativeErr
	}
	scope := nativeTaskScope{provider: p, store: ts, run: ri, role: role}
	if prior, ok := ctx.Value(nativeTaskScopeKey{}).(nativeTaskScope); ok && prior.provider == p && prior.run == ri && prior.role == role {
		scope.executor = prior.executor
		scope.validate = prior.validate
		scope.reportingReady = prior.reportingReady
	}
	ctx = context.WithValue(ctx, nativeTaskScopeKey{}, scope)
	if role == "reporter" {
		return p.bindNativeReporter(ctx, ri, tools)
	}
	if role != "worker" {
		return p.BindNativeRole(ctx, role, "run", ri, tools)
	}
	for _, template := range phase.Roles {
		if template.Role != "worker" || !template.DynamicIntent {
			continue
		}
		if RunInfoFrom(ctx) != ri || transcript.SessionIDFrom(ctx) != WorkerSessionID(ri.ExplorationID, ri.IntentID) {
			return nil, nativeErr
		}
		hash, err := nativeRoleCatalog(phase, template, tools)
		if err != nil || hash != template.CatalogSHA256 {
			return nil, nativeErr
		}
		child := template
		child.IntentID = ri.IntentID
		child.SessionID = WorkerSessionID(ri.ExplorationID, ri.IntentID)
		child.DynamicIntent = false
		bound := context.WithValue(ctx, nativeRoleAdmissionKey{}, nativeRoleAdmission{phase.state, child, ri})
		if !p.validateNativeRole(bound, llm.CompletionRequest{Tools: tools}) {
			return nil, nativeErr
		}
		return bound, nil
	}
	return nil, nativeErr
}

func prepareNativeTaskRun(ctx context.Context, prov llm.Provider, role string, ri RunInfo, ts *db.ExplorationStore, executor nativeexec.Executor, loaders ...func(llm.Provider) (nativeexec.Executor, error)) (context.Context, *nativeRPC, error) {
	original := prov
	ctx = WithRunInfo(ctx, ri)
	if ctx.Err() != nil {
		return nil, nil, ctx.Err()
	}
	if source, ok := prov.(interface {
		NativeTaskProvider(context.Context) (llm.Provider, error)
	}); ok {
		// Resolve a runtime source only after the live task membership check. Pin the
		// selected native provider for the whole run; never rotate to a legacy engine.
		if err := checkNativeTaskMembership(ts, ri, role); err != nil {
			return nil, nil, err
		}
		var err error
		prov, err = source.NativeTaskProvider(ctx)
		if err != nil {
			return nil, nil, err
		}
	}
	p, ok := prov.(*nativeRPC)
	if !ok {
		return ctx, nil, nil
	}
	if p.policy.phase == nil || !p.appAdmission || ri.TaskID != p.policy.phase.TaskID || ri.ExplorationID != p.policy.phase.ExplorationID {
		return nil, nil, nativeErr
	}
	if role == "worker" {
		if err := checkNativeTaskMembership(ts, ri, role); err != nil {
			return nil, nil, err
		}
		if executor == nil && len(loaders) == 1 && loaders[0] != nil {
			var err error
			executor, err = loaders[0](p)
			if err != nil {
				return nil, nil, nativeErr
			}
		}
		if executor == nil {
			return nil, nil, fmt.Errorf("%w: isolated worker executor unavailable", nativeErr)
		}
		v := reflect.ValueOf(executor)
		if (v.Kind() == reflect.Pointer || v.Kind() == reflect.Interface) && v.IsNil() {
			return nil, nil, nativeErr
		}
	}
	if err := checkNativeTaskMembership(ts, ri, role); err != nil {
		return nil, nil, err
	}
	session := fmt.Sprintf("exp%d-%s", ri.ExplorationID, role)
	if role == "worker" {
		session = WorkerSessionID(ri.ExplorationID, ri.IntentID)
	}
	if role == "mainagent" {
		session = fmt.Sprintf("exp%d-main", ri.ExplorationID)
	}
	if role == "reporter" {
		event, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
		if !ok || event.validate(ctx) != nil {
			return nil, nil, nativeErr
		}
		session = fmt.Sprintf("conv-%d", event.conversation)
	}
	ctx = WithRunInfo(transcript.WithSessionID(ctx, session), ri)
	scope := nativeTaskScope{provider: p, store: ts, run: ri, role: role, executor: executor}
	if ready, ok := original.(interface{ NativeReportingReady(context.Context) bool }); ok && nativeReporterTemplate(p) {
		scope.reportingReady = ready.NativeReportingReady(ctx)
	}
	if validator, ok := original.(interface {
		ValidateNativeTaskRun(context.Context, RunInfo, string, string) error
	}); ok {
		scope.validate = func(c context.Context, name string) error { return validator.ValidateNativeTaskRun(c, ri, role, name) }
	}
	return context.WithValue(ctx, nativeTaskScopeKey{}, scope), p, nil
}

func finishNativeTaskOptions(ctx context.Context, p *nativeRPC, opts *agentcore.Options) (context.Context, error) {
	scope, ok := ctx.Value(nativeTaskScopeKey{}).(nativeTaskScope)
	if !ok || scope.provider != p {
		return nil, nativeErr
	}
	opts.Provider = p
	opts.SessionID = transcript.SessionIDFrom(ctx)
	opts.EnableWebFetch = false
	opts.EnableWebSearch = false
	opts.WebFetchProxy = ""
	opts.WebFetchCACert = ""
	opts.WebSearchProxy = ""
	opts.BraveSearchAPIKey = ""
	opts.TavilySearchAPIKey = ""
	opts.DeepSeekSearchAPIKey = ""
	opts.DeepSeekSearchBaseURL = ""
	opts.DeepSeekSearchModel = ""
	opts.BashEnv = nil
	opts.Todos = nil
	opts.AskUser = nil
	opts.Plan = nil
	opts.Memory = nil
	opts.Skills = nil
	opts.DeferredTools = nil
	opts.UnlockSet = nil
	opts.DisableBackgroundTasks = true
	opts.Compaction = nil
	opts.Compactor = nil
	opts.Settlement = nil
	opts.Deps = harness.QueryDeps{}
	opts.Hooks = nil // native effects use the sealed final-argument boundary, never host hooks
	opts.TokenBudget = 0
	opts.EscalateMaxTokens = false
	opts.NonStreaming = true
	return p.BindNativeTaskRole(ctx, scope.role, scope.run, scope.store, actool.NewRegistry(opts.Tools...).Schemas())
}

// AdmittedNativeTaskProvider preserves an already admitted opaque provider.
// Marker interfaces and RunInfo are deliberately insufficient.
func AdmittedNativeTaskProvider(p llm.Provider) (llm.Provider, bool) {
	n, ok := p.(*nativeRPC)
	if !ok || !n.appAdmission || n.policy.phase == nil {
		return nil, false
	}
	return n, true
}

// IsNativeRoleRun exposes only the mode, not the opaque phase authority.
func IsNativeRoleRun(ctx context.Context) bool { return nativeRoleContext(ctx) }

func nativeRoleContext(ctx context.Context) bool {
	if _, ok := ctx.Value(nativeTaskScopeKey{}).(nativeTaskScope); ok {
		return true
	}
	_, ok := ctx.Value(nativeRoleAdmissionKey{}).(nativeRoleAdmission)
	return ok
}
