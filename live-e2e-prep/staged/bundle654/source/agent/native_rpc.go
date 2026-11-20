package agent

// Private Norma Provider candidate. NewProvider never admits this unqualified path.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"github.com/Autumn-27/norma/llm"
	"io"
	"iter"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"sync"
	"time"
)

const nativeCap = 65536

var nativeErr = errors.New("codex-native: rejected private RPC contract (no retry/fallback)")
var nativeName = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_-]{0,63}$`)
var nativeID = regexp.MustCompile(`^call_[a-f0-9]{32}$`)

// NativeRPCPolicy is not persisted or sourced from environment/user API input.
// Its endpoint/service key must be bound by an administrator after admission.
type NativeRPCPolicy struct {
	runtimeDir string
	phase      *nativePhasePermit
	Endpoint   string
	ServiceKey string `json:"-"`
	BudgetMode string
	Timeout    time.Duration
	MaxCalls   int
}
type nativeRPC struct {
	policy       NativeRPCPolicy
	client       *http.Client
	mu           sync.Mutex
	calls        int
	appAdmission bool
}

var _ llm.Provider = (*nativeRPC)(nil)

// This marker grants no role/tool authority; it only forbids task replay.
func (*nativeRPC) NativeInferenceOnly() bool { return true }

func newNativeRPC(c Config) (*nativeRPC, error) {
	if c.Provider() != "codex-native" || c.Model != "gpt-6.1-sol" || c.Stream || c.MaxTokens > 0 || c.MaxTokensField != "" || c.Proxy != "" || c.APIKey != "" || c.Native == nil || c.ThinkingType != "" || c.ReasoningEffort != "" || c.SessionHeaderKey != "" {
		return nil, nativeErr
	}
	p := *c.Native
	if p.BudgetMode != "time/bytes/calls" || p.Timeout <= 0 || p.Timeout > 90*time.Second || p.MaxCalls < 1 || p.MaxCalls > 16 || !regexp.MustCompile(`^[a-f0-9]{64}$`).MatchString(p.ServiceKey) || c.BaseURL != p.Endpoint {
		return nil, nativeErr
	}
	u, e := url.Parse(p.Endpoint)
	if e != nil || u.Scheme != "http" || !((u.Hostname() == "127.0.0.1" && u.Port() != "") || u.Host == "172.29.88.1:18761") || u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || u.Path != "/artex/native/v1/complete" || u.RawPath != "" {
		return nil, nativeErr
	}
	// Exact numeric loopback: no DNS, ambient proxies, redirects or public origin.
	tr := &http.Transport{Proxy: nil, DialContext: (&net.Dialer{Timeout: p.Timeout}).DialContext, DisableKeepAlives: true, MaxResponseHeaderBytes: 8192}
	return &nativeRPC{policy: p, client: &http.Client{Transport: tr, Timeout: p.Timeout, CheckRedirect: func(*http.Request, []*http.Request) error { return nativeErr }}}, nil
}
func (p *nativeRPC) Stream(context.Context, llm.CompletionRequest) iter.Seq2[llm.StreamEvent, error] {
	return func(yield func(llm.StreamEvent, error) bool) {
		yield(llm.StreamEvent{}, errors.New("codex-native: streaming unsupported"))
	}
}

type nativeRequest struct {
	Model                         string           `json:"model"`
	Protocol                      string           `json:"protocol"`
	Profile                       string           `json:"profile"`
	BudgetMode                    string           `json:"budget_mode"`
	GenerationTokensEnforced      bool             `json:"generation_tokens_enforced"`
	LegacyMaxTokensDiagnosticHint int              `json:"legacy_max_tokens_diagnostic_hint"`
	System                        []string         `json:"system"`
	Messages                      []llm.Message    `json:"messages"`
	Tools                         []llm.ToolSchema `json:"tools"`
}
type nativeResponse struct {
	Protocol                 string         `json:"protocol"`
	Profile                  string         `json:"profile"`
	GenerationTokensEnforced *bool          `json:"generation_tokens_enforced"`
	Message                  llm.Message    `json:"message"`
	StopReason               string         `json:"stop_reason"`
	Usage                    map[string]int `json:"usage"`
}

func (p *nativeRPC) Complete(ctx context.Context, r llm.CompletionRequest) (llm.Message, string, llm.Usage, error) {
	fail := func() (llm.Message, string, llm.Usage, error) { return llm.Message{}, "", llm.Usage{}, nativeErr }
	if p.policy.phase != nil {
		if !p.validateNativeRole(ctx, r) {
			return fail()
		}
	} else if p.appAdmission && ctx.Value(nativeChatContextKey{}) != true {
		return fail()
	}
	if !p.mu.TryLock() {
		return fail()
	}
	defer p.mu.Unlock()
	ctx, cancel := context.WithTimeout(ctx, p.policy.Timeout)
	defer cancel()
	if phase := p.policy.phase; phase != nil {
		stop := context.AfterFunc(phase.state.ctx, cancel)
		defer stop()
		var expiryCancel context.CancelFunc
		ctx, expiryCancel = context.WithDeadline(ctx, phase.ExpiresAt)
		defer expiryCancel()
	}
	if ctx.Err() != nil || p.calls >= p.policy.MaxCalls || len(r.Messages) < 1 || len(r.Messages) > 128 || len(r.Tools) > 32 || r.MaxTokens < 0 || r.Temperature != nil || len(r.Stop) > 0 || (r.Thinking != "" && r.Thinking != "disabled") {
		return fail()
	}
	catalog := map[string]llm.ToolSchema{}
	seen := map[string]bool{}
	pending := map[string]bool{}
	for _, t := range r.Tools {
		if !nativeName.MatchString(t.Name) || catalog[t.Name].Name != "" || t.InputSchema["type"] != "object" {
			return fail()
		}
		catalog[t.Name] = t
	}
	for _, m := range r.Messages {
		if (m.Role != llm.RoleUser && m.Role != llm.RoleAssistant) || len(m.Content) < 1 || len(m.Content) > 32 {
			return fail()
		}
		for _, b := range m.Content {
			switch b.Type {
			case llm.BlockText:
				if len(pending) > 0 {
					return fail()
				}
			case llm.BlockToolUse:
				if m.Role != llm.RoleAssistant || !nativeID.MatchString(b.ID) || seen[b.ID] || catalog[b.Name].Name == "" || !nativeObject(b.Input) {
					return fail()
				}
				seen[b.ID] = true
				pending[b.ID] = true
			case llm.BlockToolResult:
				if m.Role != llm.RoleUser || !pending[b.ToolUseID] {
					return fail()
				}
				delete(pending, b.ToolUseID)
				for _, c := range b.Content {
					if c.Type != llm.BlockText {
						return fail()
					}
				}
			default:
				return fail()
			}
		}
	}
	if len(pending) > 0 {
		return fail()
	}
	system := r.System
	if system == nil {
		system = []string{}
	}
	tools := r.Tools
	if tools == nil {
		tools = []llm.ToolSchema{}
	}
	raw, e := json.Marshal(nativeRequest{"gpt-6.1-sol", "artex-native-v1", "codex-native", "time/bytes/calls", false, r.MaxTokens, system, r.Messages, tools})
	if e != nil || len(raw) > nativeCap {
		return fail()
	}
	release, admitted := p.reserveNativeRole(ctx, len(raw))
	if !admitted {
		return fail()
	}
	defer release()
	req, e := http.NewRequestWithContext(ctx, "POST", p.policy.Endpoint, bytes.NewReader(raw))
	if e != nil {
		return fail()
	}
	req.Header.Set("Authorization", "Bearer "+p.policy.ServiceKey)
	req.Header.Set("Content-Type", "application/json")
	p.calls++ // consume once before IO: failures never retry or refund
	res, e := p.client.Do(req)
	if e != nil {
		return fail()
	}
	defer res.Body.Close()
	if res.StatusCode != 200 || res.Header.Get("Content-Type") != "application/json" {
		return fail()
	}
	body, e := io.ReadAll(io.LimitReader(res.Body, nativeCap+1))
	if e != nil || len(body) > nativeCap || ctx.Err() != nil {
		return fail()
	}
	var o nativeResponse
	d := json.NewDecoder(bytes.NewReader(body))
	d.DisallowUnknownFields()
	if d.Decode(&o) != nil || d.Decode(new(any)) != io.EOF || o.Protocol != "artex-native-v1" || o.Profile != "codex-native" || o.GenerationTokensEnforced == nil || *o.GenerationTokensEnforced || o.Message.Role != llm.RoleAssistant || len(o.Message.Content) < 1 || len(o.Message.Content) > 8 {
		return fail()
	}
	hasTools := false
	for _, b := range o.Message.Content {
		switch b.Type {
		case llm.BlockText:
			if b.Text == "" {
				return fail()
			}
		case llm.BlockToolUse:
			if !nativeID.MatchString(b.ID) || seen[b.ID] || catalog[b.Name].Name == "" || !nativeObject(b.Input) {
				return fail()
			}
			seen[b.ID] = true
			hasTools = true
		default:
			return fail()
		}
	}
	if (hasTools && o.StopReason != "tool_use") || (!hasTools && o.StopReason != "end_turn") || len(o.Usage) != 4 {
		return fail()
	}
	for _, k := range []string{"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"} {
		v, ok := o.Usage[k]
		if !ok || v < 0 {
			return fail()
		}
	}
	return o.Message, o.StopReason, llm.Usage{InputTokens: o.Usage["input_tokens"], OutputTokens: o.Usage["output_tokens"], CacheReadTokens: o.Usage["cache_read_tokens"], CacheWriteTokens: o.Usage["cache_write_tokens"]}, nil
}
func nativeObject(raw json.RawMessage) bool {
	var o map[string]any
	return json.Unmarshal(raw, &o) == nil && o != nil
}
