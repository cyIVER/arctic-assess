package agent

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/Autumn-27/norma/llm"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// This permit is administrator-owned runtime data, never a Config/API/env value.
// Loading it does not authorize a model call or an effect. Reporter templates
// require a separately SQL-qualified committed finding/conversation event.
type nativePhasePermit struct {
	state             *nativePhaseState
	SchemaVersion     int               `json:"schema_version"`
	PhaseID           string            `json:"phase_id"`
	Generation        int64             `json:"authority_generation"`
	TaskID            int64             `json:"task_id"`
	ExplorationID     int64             `json:"exploration_id"`
	FixtureOrigin     string            `json:"fixture_origin"`
	NetworkPolicyID   string            `json:"network_policy_id"`
	ExecutorID        string            `json:"executor_id"`
	LedgerID          string            `json:"ledger_id"`
	ExpiresAt         time.Time         `json:"expires_at"`
	MaxCalls          int               `json:"max_calls"`
	MaxAggregateBytes int               `json:"max_aggregate_bytes"`
	Roles             []nativePhaseRole `json:"roles"`
}
type nativePhaseRole struct {
	DynamicIntent  bool   `json:"dynamic_intent,omitempty"`
	DynamicFinding bool   `json:"dynamic_finding,omitempty"`
	Role           string `json:"role"`
	Purpose        string `json:"purpose"`
	IntentID       int64  `json:"intent_id"`
	SessionID      string `json:"session_id"`
	CatalogSHA256  string `json:"catalog_sha256"`
}

var nativeDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)

func parseNativePhase(raw []byte) (*nativePhasePermit, error) {
	var p nativePhasePermit
	if strictNativeJSON(raw, &p) != nil {
		return nil, nativeErr
	}
	now := time.Now()
	if p.SchemaVersion != 1 || !nativeName.MatchString(p.PhaseID) || p.Generation <= 0 || p.TaskID <= 0 || p.ExplorationID <= 0 || !nativeName.MatchString(p.NetworkPolicyID) || !nativeName.MatchString(p.ExecutorID) || !nativeName.MatchString(p.LedgerID) || !p.ExpiresAt.After(now) || p.ExpiresAt.After(now.Add(600*time.Second)) || p.MaxCalls < 1 || p.MaxCalls > 16 || p.MaxAggregateBytes < nativeCap || p.MaxAggregateBytes > 2*1024*1024 || len(p.Roles) < 1 || len(p.Roles) > 16 {
		return nil, nativeErr
	}
	u, e := url.Parse(p.FixtureOrigin)
	if e != nil || u.Scheme != "http" || u.Hostname() == "" || u.User != nil || u.Path != "" || u.RawPath != "" || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || u.String() != p.FixtureOrigin {
		return nil, nativeErr
	}
	seen := map[string]bool{}
	for _, r := range p.Roles {
		session := fmt.Sprintf("exp%d-%s", p.ExplorationID, r.Role)
		if r.DynamicFinding && r.Role != "reporter" {
			return nil, nativeErr
		}
		switch r.Role {
		case "goals", "planner", "mainagent":
			if r.DynamicIntent {
				return nil, nativeErr
			}
			if r.IntentID != 0 {
				return nil, nativeErr
			}
			if r.Role == "mainagent" {
				session = fmt.Sprintf("exp%d-main", p.ExplorationID)
			}
		case "reporter":
			if !r.DynamicFinding || r.DynamicIntent || r.IntentID != 0 || r.SessionID != "" {
				return nil, nativeErr
			}
			session = "reporter-template"
		case "worker":
			if r.DynamicIntent {
				if r.IntentID != 0 || r.SessionID != "" {
					return nil, nativeErr
				}
				session = ""
			} else {
				if r.IntentID <= 0 {
					return nil, nativeErr
				}
				session = fmt.Sprintf("exp%d-worker-i%d", p.ExplorationID, r.IntentID)
			}
		default:
			return nil, nativeErr
		}
		if r.Purpose != "run" || (r.Role != "reporter" && r.SessionID != session) || !nativeDigest.MatchString(r.CatalogSHA256) || seen[session] {
			return nil, nativeErr
		}
		seen[session] = true
	}
	// Process-local defense only. The independent broker remains responsible for
	// durable reservations and sealing on restart; this does not replace its ledger.
	canonical, e := json.Marshal(p)
	if e != nil {
		return nil, nativeErr
	}
	digest := sha256.Sum256(canonical)
	key := fmt.Sprintf("%s/%d", p.PhaseID, p.Generation)
	nativePhaseStates.Lock()
	defer nativePhaseStates.Unlock()
	if old := nativePhaseStates.states[key]; old != nil {
		if old.digest != digest {
			return nil, nativeErr
		}
		p.state = old
	} else {
		phaseCtx, cancel := context.WithCancel(context.Background())
		p.state = &nativePhaseState{digest: digest, ctx: phaseCtx, cancel: cancel}
		nativePhaseStates.states[key] = p.state
	}
	return &p, nil
}

type nativePhaseState struct {
	mu                   sync.Mutex
	digest               [32]byte
	calls, reservedBytes int
	inFlight, stopped    bool
	flightDone           chan struct{}
	ctx                  context.Context
	cancel               context.CancelFunc
}

var nativePhaseStates = struct {
	sync.Mutex
	states map[string]*nativePhaseState
}{states: map[string]*nativePhaseState{}}

type nativeRoleAdmissionKey struct{}
type nativeRoleAdmission struct {
	state *nativePhaseState
	role  nativePhaseRole
	run   RunInfo
}

// BindNativeRole is a trusted Go-host boundary, not a request/RunInfo authority
// parser. The private permit must already name this exact run and final catalog.
// Normal role launchers must validate DB membership and disable SDK support
// before calling it. Neither a chat marker nor arbitrary RunInfo grants access.
func (p *nativeRPC) BindNativeRole(ctx context.Context, role, purpose string, ri RunInfo, tools []llm.ToolSchema) (context.Context, error) {
	phase := p.policy.phase
	if phase == nil || phase.state == nil || ctx.Err() != nil || !time.Now().Before(phase.ExpiresAt) || ri.TaskID != phase.TaskID || ri.ExplorationID != phase.ExplorationID || ri.SessionID != "" || RunInfoFrom(ctx) != ri {
		return nil, nativeErr
	}
	phase.state.mu.Lock()
	stopped := phase.state.stopped
	phase.state.mu.Unlock()
	if stopped {
		return nil, nativeErr
	}
	session := transcript.SessionIDFrom(ctx)
	for _, r := range phase.Roles {
		if r.DynamicFinding {
			continue
		}
		if r.Role == role && r.Purpose == purpose && r.IntentID == ri.IntentID && r.SessionID == session {
			fingerprint, e := nativeRoleCatalog(phase, r, tools)
			if e != nil || fingerprint != r.CatalogSHA256 {
				return nil, nativeErr
			}
			return context.WithValue(ctx, nativeRoleAdmissionKey{}, nativeRoleAdmission{phase.state, r, ri}), nil
		}
	}
	return nil, nativeErr
}

func (p *nativeRPC) RevokeNativeRolePhase() {
	if phase := p.policy.phase; phase != nil && phase.state != nil {
		phase.state.mu.Lock()
		phase.state.stopped = true
		phase.state.cancel()
		phase.state.mu.Unlock()
	}
}

func nativeRoleToolNames(role string) string {
	allowed := map[string]string{
		"reporter":  "get_task_node_detail node_detail get_finding_traffic update_finding_report",
		"goals":     "set_goals set_constraints",
		"planner":   "graph_overview list_findings list_facts node_detail get_worker_output get_worker_trace search_all_worker_traces list_goals add_intent prove_goal kill_work steer_work",
		"worker":    "report_finding list_findings record_fact node_detail get_worker_trace search_all_worker_traces Read Write Edit LS Bash sleep",
		"mainagent": "graph_overview list_findings list_facts node_detail get_worker_output get_worker_trace search_all_worker_traces add_hint add_intent steer_work record_fact",
	}
	return allowed[role]
}
func nativeRoleAllows(role, name string) bool {
	return strings.Contains(" "+nativeRoleToolNames(role)+" ", " "+name+" ") && name != ""
}
func nativeRoleCatalog(phase *nativePhasePermit, role nativePhaseRole, tools []llm.ToolSchema) (string, error) {
	if len(tools) < 1 || len(tools) > 32 || nativeRoleToolNames(role.Role) == "" {
		return "", nativeErr
	}
	seen := map[string]bool{}
	for _, t := range tools {
		if seen[t.Name] || !nativeRoleAllows(role.Role, t.Name) || t.InputSchema["type"] != "object" {
			return "", nativeErr
		}
		seen[t.Name] = true
	}
	raw, e := json.Marshal(map[string]any{"role": role.Role, "purpose": role.Purpose, "executor_id": phase.ExecutorID, "network_policy_id": phase.NetworkPolicyID, "tools": tools})
	if e != nil || len(raw) > nativeCap {
		return "", nativeErr
	}
	h := sha256.Sum256(raw)
	return hex.EncodeToString(h[:]), nil
}

func (p *nativeRPC) validateNativeRole(ctx context.Context, r llm.CompletionRequest) bool {
	phase := p.policy.phase
	a, ok := ctx.Value(nativeRoleAdmissionKey{}).(nativeRoleAdmission)
	if phase == nil || !ok || a.state != phase.state || ctx.Err() != nil || !time.Now().Before(phase.ExpiresAt) || RunInfoFrom(ctx) != a.run || transcript.SessionIDFrom(ctx) != a.role.SessionID {
		return false
	}
	if scope, scoped := ctx.Value(nativeTaskScopeKey{}).(nativeTaskScope); scoped {
		if scope.role == "reporter" {
			event, ok := ctx.Value(nativeFindingKey{}).(nativeFindingAuthority)
			if !ok || event.validate(ctx) != nil {
				return false
			}
		}
		if scope.validate != nil {
			if scope.validate(ctx, "") != nil {
				return false
			}
			for _, t := range r.Tools {
				if scope.validate(ctx, t.Name) != nil {
					return false
				}
			}
		}
		if scope.provider != p || scope.run != a.run || scope.role != a.role.Role || checkNativeTaskMembership(scope.store, scope.run, scope.role) != nil {
			return false
		}
		if scope.validate != nil {
			// Resample the same normal factories/resolver, including DB metadata
			// overrides, after queueing and immediately before HTTP. No authority
			// is minted by schema derivation; the original sealed digest wins.
			reporter := []actool.CoreTool{ReporterNodeTool(nil), ReporterTrafficTool(nil), ReporterUpdateTool(nil)}
			_, current, e := NativePreflightCatalog(ctx, scope.role, phase.ExecutorID, phase.NetworkPolicyID, scope.store, scope.run.TaskID, reporter, scope.reportingReady, ToolResolve)
			if e != nil || current != a.role.CatalogSHA256 {
				return false
			}
		}
	}
	phase.state.mu.Lock()
	stopped := phase.state.stopped
	phase.state.mu.Unlock()
	if stopped {
		return false
	}
	hash, e := nativeRoleCatalog(phase, a.role, r.Tools)
	return e == nil && hash == a.role.CatalogSHA256
}

// Reserve pessimistically for the maximum response. Failed/lost responses never
// refund attempts or bytes. Capacity is separate and released after IO settles.
func (p *nativeRPC) reserveNativeRole(ctx context.Context, size int, request llm.CompletionRequest) (func(), bool) {
	phase := p.policy.phase
	if phase == nil {
		return func() {}, true
	}
	s := phase.state
	for {
		// Revalidate live source/DB membership and exact sealed catalog after every
		// wait, before charging any attempt. Never hold phase mutex during SQL or wait.
		if !p.validateNativeRole(ctx, request) {
			return nil, false
		}
		s.mu.Lock()
		if s.stopped || ctx.Err() != nil || !time.Now().Before(phase.ExpiresAt) {
			s.mu.Unlock()
			return nil, false
		}
		if s.inFlight {
			done := s.flightDone
			s.mu.Unlock()
			select {
			case <-done:
			case <-ctx.Done():
				return nil, false
			case <-s.ctx.Done():
				return nil, false
			}
			continue
		}
		if s.calls >= phase.MaxCalls || p.calls >= p.policy.MaxCalls || size+nativeCap > phase.MaxAggregateBytes-s.reservedBytes {
			s.mu.Unlock()
			return nil, false
		}
		s.calls++
		s.reservedBytes += size + nativeCap
		p.calls++
		s.inFlight = true
		s.flightDone = make(chan struct{})
		done := s.flightDone
		s.mu.Unlock()
		return func() { s.mu.Lock(); s.inFlight = false; close(done); s.mu.Unlock() }, true
	}
}

// encoding/json alone accepts duplicate object keys. Reject them recursively
// before decoding the exact typed schema; no coercion or unknown fields.
func strictNativeJSON(raw []byte, out any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	var value func() error
	value = func() error {
		tok, e := d.Token()
		if e != nil {
			return e
		}
		delim, ok := tok.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := map[string]bool{}
			for d.More() {
				k, e := d.Token()
				if e != nil {
					return e
				}
				s, ok := k.(string)
				if !ok || seen[s] {
					return nativeErr
				}
				seen[s] = true
				if e = value(); e != nil {
					return e
				}
			}
			end, e := d.Token()
			if e != nil || end != json.Delim('}') {
				return nativeErr
			}
		case '[':
			for d.More() {
				if e := value(); e != nil {
					return e
				}
			}
			end, e := d.Token()
			if e != nil || end != json.Delim(']') {
				return nativeErr
			}
		default:
			return nativeErr
		}
		return nil
	}
	if e := value(); e != nil {
		return e
	}
	if _, e := d.Token(); e != io.EOF {
		return nativeErr
	}
	d = json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if e := d.Decode(out); e != nil {
		return e
	}
	if d.Decode(new(any)) != io.EOF {
		return nativeErr
	}
	return nil
}
