package agent

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/permission"
	actool "github.com/Autumn-27/norma/tool"
	"github.com/Autumn-27/norma/transcript"
)

// Runtime interface assertion keeps this first RED compiler-valid against the
// prior slice: the missing feature must fail an executed assertion, not a build.
type roleFixtureBinder interface {
	BindNativeRole(context.Context, string, string, RunInfo, []llm.ToolSchema) (context.Context, error)
	RevokeNativeRolePhase()
}
type roleRoundTrip func(*http.Request) (*http.Response, error)

func (f roleRoundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

const roleSyntheticResponse = `{"protocol":"artex-native-v1","profile":"codex-native","generation_tokens_enforced":false,"message":{"role":"assistant","content":[{"type":"text","text":"SYNTHETIC ROLE FIXTURE NO OBSERVATIONS"}]},"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}`

func roleFixtureDigest(t *testing.T, phase map[string]any, role string, tools []llm.ToolSchema) string {
	t.Helper()
	b, e := json.Marshal(map[string]any{"role": role, "purpose": "run", "executor_id": phase["executor_id"], "network_policy_id": phase["network_policy_id"], "tools": tools})
	if e != nil {
		t.Fatal(e)
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func admittedRoleFixture(t *testing.T) (*nativeRPC, roleFixtureBinder, context.Context, llm.CompletionRequest, *int) {
	t.Helper()
	// Use the actual ARTEX planner handler's full SDK-advertised schema/description.
	tsx := NewToolSet(nil, "planner")
	tools := actool.NewRegistry(tsx.addIntent()).Schemas()
	d, phase := rolePermitFixture(t)

	phase["max_calls"] = 2
	phase["roles"].([]any)[0].(map[string]any)["catalog_sha256"] = roleFixtureDigest(t, phase, "planner", tools)
	writeRolePermit(t, d, phase)
	policy, opens, e := loadRoleFixture(t, d)
	if e != nil || opens != 1 {
		t.Fatalf("positive loader failed: %v opens=%d", e, opens)
	}
	c := ConfigFrom("codex-native", "gpt-6.1-sol", policy.Endpoint, "", "")
	c.Native = policy
	p, e := newNativeRPC(c)
	if e != nil {
		t.Fatal(e)
	}
	p.appAdmission = true
	n := new(int)
	p.client.Transport = roleRoundTrip(func(r *http.Request) (*http.Response, error) {
		*n++
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(roleSyntheticResponse))}, nil
	})
	binder, ok := any(p).(roleFixtureBinder)
	if !ok {
		t.Fatal("missing trusted role admission constructor/revocation boundary")
	}
	ctx := transcript.WithSessionID(context.Background(), "exp200-planner")
	ctx = WithRunInfo(ctx, RunInfo{TaskID: 21, ExplorationID: 200})
	ctx, e = binder.BindNativeRole(ctx, "planner", "run", RunInfoFrom(ctx), tools)
	if e != nil {
		t.Fatalf("positive role binding: %v", e)
	}
	return p, binder, ctx, llm.CompletionRequest{Messages: []llm.Message{llm.UserText("SYNTHETIC NO TARGET")}, Tools: tools}, n
}
func TestNativeRoleBoundComplete(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	m, _, _, e := p.Complete(ctx, r)
	if e != nil || m.Text() != "SYNTHETIC ROLE FIXTURE NO OBSERVATIONS" || *n != 1 {
		t.Fatalf("admitted role failed: %v transport=%d", e, *n)
	}
	for _, tc := range []struct {
		name   string
		change func(context.Context, llm.CompletionRequest) (context.Context, llm.CompletionRequest)
	}{
		{"unmarked", func(_ context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			return context.Background(), r
		}},
		{"chat_not_role", func(_ context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			return context.WithValue(context.Background(), nativeChatContextKey{}, true), r
		}},
		{"task", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			return WithRunInfo(c, RunInfo{TaskID: 22, ExplorationID: 200}), r
		}},
		{"intent", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			return WithRunInfo(c, RunInfo{TaskID: 21, ExplorationID: 200, IntentID: 3}), r
		}},
		{"exploration", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			return WithRunInfo(c, RunInfo{TaskID: 21, ExplorationID: 201}), r
		}},
		{"session", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			return transcript.WithSessionID(c, "exp201-planner"), r
		}},
		{"catalog_removed_support", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			r.Tools = nil
			return c, r
		}},
		{"catalog_drift", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			r.Tools = append([]llm.ToolSchema{}, r.Tools...)
			r.Tools[0].Description += " changed"
			return c, r
		}},
		{"payload", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			r.Messages = []llm.Message{llm.UserText(strings.Repeat("x", 65536))}
			return c, r
		}},
		{"canceled", func(c context.Context, r llm.CompletionRequest) (context.Context, llm.CompletionRequest) {
			c, cancel := context.WithCancel(c)
			cancel()
			return c, r
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c, q := tc.change(ctx, r)
			if _, _, _, e := p.Complete(c, q); e == nil || *n != 1 {
				t.Fatalf("denial failed: err=%v transport=%d", e, *n)
			}
		})
	}
	// Reconstructed providers share the validated phase allowance, not p.calls.
	c := ConfigFrom("codex-native", "gpt-6.1-sol", p.policy.Endpoint, "", "")
	c.Native = &p.policy
	other, e := newNativeRPC(c)
	if e != nil {
		t.Fatal(e)
	}
	other.appAdmission = true
	other.client.Transport = p.client.Transport
	if _, _, _, e = other.Complete(ctx, r); e != nil || *n != 2 {
		t.Fatalf("second shared phase attempt: %v transport=%d", e, *n)
	}
	if _, _, _, e = p.Complete(ctx, r); e == nil || *n != 2 {
		t.Fatalf("phase budget reset across provider: %v transport=%d", e, *n)
	}
}
func TestNativeRoleBindScopeAndStop(t *testing.T) {
	p, binder, ctx, r, n := admittedRoleFixture(t)
	for _, tc := range []struct {
		role, purpose, session string
		ri                     RunInfo
	}{
		{"worker", "run", "exp200-worker-i7", RunInfo{TaskID: 21, ExplorationID: 200, IntentID: 7}},
		{"planner", "compact", "exp200-planner", RunInfo{TaskID: 21, ExplorationID: 200}},
		{"planner", "run", "exp200-planner", RunInfo{TaskID: 22, ExplorationID: 200}},
	} {
		bad := transcript.WithSessionID(WithRunInfo(context.Background(), tc.ri), tc.session)
		if _, e := binder.BindNativeRole(bad, tc.role, tc.purpose, tc.ri, r.Tools); e == nil {
			t.Fatal("invalid host role tuple admitted")
		}
	}
	binder.RevokeNativeRolePhase()
	if _, _, _, e := p.Complete(ctx, r); e == nil || *n != 0 {
		t.Fatalf("revoked phase reached transport: %v calls=%d", e, *n)
	}
	if _, e := binder.BindNativeRole(ctx, "planner", "run", RunInfoFrom(ctx), r.Tools); e == nil {
		t.Fatal("revoked phase rebound")
	}
}
func TestNativeRoleExpiredAfterBinding(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	p.policy.phase.ExpiresAt = time.Now().Add(-time.Second)
	if _, _, _, e := p.Complete(ctx, r); e == nil || *n != 0 {
		t.Fatalf("expiry bypass: %v calls=%d", e, *n)
	}
}

func TestNativeRoleActualNormaLoop(t *testing.T) {
	p, _, ctx, _, n := admittedRoleFixture(t)
	tsx := NewToolSet(nil, "planner")
	reply, e := agentcore.Run(ctx, agentcore.Options{
		Provider: p, Tools: []actool.CoreTool{tsx.addIntent()}, PermissionMode: permission.ModeBypass,
		NonStreaming: true, DisableBackgroundTasks: true, MaxTurns: 1,
	}, "SYNTHETIC NO TARGET")
	if e != nil || reply != "SYNTHETIC ROLE FIXTURE NO OBSERVATIONS" || *n != 1 {
		t.Fatalf("actual Norma role loop: reply=%q err=%v calls=%d", reply, e, *n)
	}
	t.Log("actual Norma loop and actual add_intent catalog; no DB handler invoked, no assessment acceptance")
}

func TestNativeRolePhaseReloadAndAggregateBudget(t *testing.T) {
	p, _, ctx, r, n := admittedRoleFixture(t)
	if _, _, _, e := p.Complete(ctx, r); e != nil {
		t.Fatal(e)
	}
	raw, e := json.Marshal(p.policy.phase)
	if e != nil {
		t.Fatal(e)
	}
	loaded, e := parseNativePhase(raw)
	if e != nil {
		t.Fatal(e)
	}
	if loaded.state != p.policy.phase.state {
		t.Fatal("identical phase reload reset shared state")
	}
	loaded.state.mu.Lock()
	calls := loaded.state.calls
	loaded.state.mu.Unlock()
	if calls != 1 {
		t.Fatalf("reload calls=%d", calls)
	}
	// The request plus its full response reservation must fit before any IO.
	loaded.MaxAggregateBytes = nativeCap
	c := ConfigFrom("codex-native", "gpt-6.1-sol", p.policy.Endpoint, "", "")
	policy := p.policy
	policy.phase = loaded
	c.Native = &policy
	other, e := newNativeRPC(c)
	if e != nil {
		t.Fatal(e)
	}
	other.appAdmission = true
	other.client.Transport = p.client.Transport
	if _, _, _, e = other.Complete(ctx, r); e == nil || *n != 1 {
		t.Fatalf("aggregate limit: err=%v calls=%d", e, *n)
	}
}

func TestNativeRoleRevokeCancelsInflight(t *testing.T) {
	p, binder, ctx, r, n := admittedRoleFixture(t)
	started := make(chan struct{})
	done := make(chan error, 1)
	p.client.Transport = roleRoundTrip(func(req *http.Request) (*http.Response, error) {
		close(started)
		<-req.Context().Done()
		return nil, req.Context().Err()
	})
	go func() { _, _, _, e := p.Complete(ctx, r); done <- e }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("positive in-flight transport not reached")
	}
	binder.RevokeNativeRolePhase()
	select {
	case e := <-done:
		if e == nil {
			t.Fatal("revoked in-flight returned success")
		}
	case <-time.After(time.Second):
		t.Fatal("revocation did not cancel owned transport")
	}
	if *n != 0 {
		t.Fatal("unexpected fixture transport")
	}
	p.policy.phase.state.mu.Lock()
	busy := p.policy.phase.state.inFlight
	p.policy.phase.state.mu.Unlock()
	if busy {
		t.Fatal("in-flight slot not settled")
	}
}
