package agent

import (
	"bytes"
	"context"
	"encoding/json"
	"strconv"
	"strings"
	"time"

	"github.com/Autumn-27/artex/nativeexec"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

func nativeLiveScope(ctx context.Context) (nativeTaskScope, error) {
	scope, ok := ctx.Value(nativeTaskScopeKey{}).(nativeTaskScope)
	a, bound := ctx.Value(nativeRoleAdmissionKey{}).(nativeRoleAdmission)
	if !ok || !bound || scope.provider == nil || ctx.Err() != nil {
		return nativeTaskScope{}, nativeErr
	}
	phase := scope.provider.policy.phase
	if phase == nil || a.state != phase.state || a.run != scope.run || a.role.Role != scope.role || RunInfoFrom(ctx) != scope.run || transcript.SessionIDFrom(ctx) != a.role.SessionID || !time.Now().Before(phase.ExpiresAt) {
		return nativeTaskScope{}, nativeErr
	}
	phase.state.mu.Lock()
	stopped := phase.state.stopped
	phase.state.mu.Unlock()
	if stopped || checkNativeTaskMembership(scope.store, scope.run, scope.role) != nil {
		return nativeTaskScope{}, nativeErr
	}
	if scope.role == "reporter" {
		event, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
		if !ok || event.validate(ctx) != nil {
			return nativeTaskScope{}, nativeErr
		}
	}
	if scope.validate != nil && scope.validate(ctx, "") != nil {
		return nativeTaskScope{}, nativeErr
	}
	return scope, nil
}
func resolveNativeExecution(ctx context.Context) (nativeexec.Binding, error) {
	s, err := nativeLiveScope(ctx)
	if err != nil || s.role != "worker" {
		return nativeexec.Binding{}, nativeErr
	}
	p := s.provider.policy.phase
	return nativeexec.Binding{PhaseID: p.PhaseID, Generation: p.Generation, TaskID: s.run.TaskID, ExplorationID: s.run.ExplorationID, IntentID: s.run.IntentID, Role: s.role, SessionID: transcript.SessionIDFrom(ctx), ExecutorID: p.ExecutorID, NetworkPolicyID: p.NetworkPolicyID}, nil
}

// This guard runs inside the original domain handler, after DB-default injection
// and post-permission/hook edits. Untrusted nested IDs never become authority.
func nativeDomainInput(ctx context.Context, name string, schema map[string]any, in json.RawMessage) error {
	if !nativeRoleContext(ctx) {
		return nil
	}
	s, err := nativeLiveScope(ctx)
	if err != nil || !nativeRoleAllows(s.role, name) {
		return nativeErr
	}
	if name == "report_finding" {
		if !s.reportingReady {
			return nativeErr
		}
		var input map[string]json.RawMessage
		if strictNativeJSON(in, &input) != nil {
			return nativeErr
		}
		var id int64
		if json.Unmarshal(input["intent_id"], &id) != nil || id != s.run.IntentID || id <= 0 {
			return nativeErr
		}
	}
	if s.validate != nil && s.validate(ctx, name) != nil {
		return nativeErr
	}
	if actool.ValidateInput(schema, in) != nil {
		return nativeErr
	}
	var value any
	if len(in) > 32768 || strictNativeJSON(in, &value) != nil {
		return nativeErr
	}
	dec := json.NewDecoder(bytes.NewReader(in))
	dec.UseNumber()
	if dec.Decode(&value) != nil {
		return nativeErr
	}
	var idValue func(any) (int64, error)
	idValue = func(v any) (int64, error) {
		raw := ""
		switch n := v.(type) {
		case json.Number:
			raw = n.String()
		case string:
			raw = n
		default:
			return 0, nativeErr
		}
		id, e := strconv.ParseInt(raw, 10, 64)
		if e != nil || id <= 0 || strconv.FormatInt(id, 10) != raw {
			return 0, nativeErr
		}
		return id, nil
	}
	checkID := func(key string, v any) error {
		id, e := idValue(v)
		if e != nil {
			return e
		}
		if s.role == "reporter" {
			event, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
			if !ok {
				return nativeErr
			}
			switch key {
			case "finding_id":
				expected := event.finding
				if name == "update_finding_report" {
					expected = event.node
				}
				if id != expected {
					return nativeErr
				}
				return nil
			case "id", "finding_node_id":
				if id != event.node && !(name == "node_detail" && id == event.intent) {
					return nativeErr
				}
				return nil
			case "intent_id":
				if id != event.intent {
					return nativeErr
				}
				return nil
			case "task_id", "exploration_id":
			default:
				return nativeErr
			}
		}
		switch key {
		case "task_id":
			if id != s.run.TaskID {
				return nativeErr
			}
			return nil
		case "exploration_id":
			if id != s.run.ExplorationID {
				return nativeErr
			}
			return nil
		case "asset_id", "company_id":
			return nativeErr // global assets require a separate reviewed scope adapter
		case "intent_id":
			if s.role == "worker" && id != s.run.IntentID {
				return nativeErr
			}
		}
		node, e := s.store.GetNode(id)
		if e != nil || node == nil {
			return nativeErr
		}
		if key == "intent_id" && node.Kind != "intent" {
			return nativeErr
		}
		if key == "goal_id" && node.Kind != "goal" {
			return nativeErr
		}
		return nil
	}
	var walk func(any) error
	walk = func(v any) error {
		switch x := v.(type) {
		case map[string]any:
			for k, val := range x {
				if strings.HasSuffix(k, "_ids") {
					arr, ok := val.([]any)
					if !ok {
						return nativeErr
					}
					for _, item := range arr {
						if err := checkID(strings.TrimSuffix(k, "s"), item); err != nil {
							return err
						}
					}
				} else if k == "id" || strings.HasSuffix(k, "_id") {
					if err := checkID(k, val); err != nil {
						return err
					}
				}
				if err := walk(val); err != nil {
					return err
				}
			}
		case []any:
			for _, item := range x {
				if err := walk(item); err != nil {
					return err
				}
			}
		}
		return nil
	}
	if s.role == "reporter" && name == "update_finding_report" {
		event := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
		obj, ok := value.(map[string]any)
		if !ok {
			return nativeErr
		}
		v, ok := obj["evidence_version"].(json.Number)
		if !ok {
			return nativeErr
		}
		version, e := v.Int64()
		if e != nil || version != event.version {
			return nativeErr
		}
	}
	return walk(value)
}
