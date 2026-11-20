package agent

import (
	"context"
	"encoding/json"
	"github.com/Autumn-27/norma/llm"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestNativeIdentityDisabled(t *testing.T) {
	c := ConfigFrom("codex-native", "gpt-6.1-sol", "http://127.0.0.1:1/artex/native/v1/complete", "", "")
	if c.Provider() != "codex-native" {
		t.Fatal("native identity fell through")
	}
	if _, e := c.NewProvider(); e == nil {
		t.Fatal("unqualified native enabled")
	}
	c.MaxTokens = 1
	if _, e := newNativeRPC(c); e == nil {
		t.Fatal("operator cap accepted")
	}
	c.MaxTokens = 0
	c.Stream = true
	if _, e := newNativeRPC(c); e == nil {
		t.Fatal("stream accepted")
	}
	t.Setenv("ARTEX_LLM_PROVIDER", "codex-native")
	t.Setenv("ANTHROPIC_API_KEY", "synthetic-not-a-key")
	env, ok := FromEnv()
	if !ok || env.Provider() != "codex-native" || env.APIKey != "" {
		t.Fatal("native env fell through")
	}
}
func TestNativeRPCSyntheticNoTarget(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/artex/native/v1/complete" || r.Header.Get("Authorization") != "Bearer "+strings.Repeat("f", 64) {
			t.Error("route/auth")
		}
		var q map[string]any
		if e := json.NewDecoder(r.Body).Decode(&q); e != nil {
			t.Error(e)
		}
		if q["legacy_max_tokens_diagnostic_hint"] != float64(32768) || q["generation_tokens_enforced"] != false {
			t.Error("capability mismatch")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"protocol":"artex-native-v1","profile":"codex-native","generation_tokens_enforced":false,"message":{"role":"assistant","content":[{"type":"text","text":"SYNTHETIC NO TARGET"}]},"stop_reason":"end_turn","usage":{"input_tokens":3,"output_tokens":4,"cache_read_tokens":0,"cache_write_tokens":0}}`))
	}))
	defer s.Close()
	c := ConfigFrom("codex-native", "gpt-6.1-sol", s.URL+"/artex/native/v1/complete", "", "")
	c.Native = &NativeRPCPolicy{Endpoint: c.BaseURL, ServiceKey: strings.Repeat("f", 64), BudgetMode: "time/bytes/calls", Timeout: time.Second, MaxCalls: 1}
	p, e := newNativeRPC(c)
	if e != nil {
		t.Fatal(e)
	}
	m, stop, u, e := p.Complete(context.Background(), llm.CompletionRequest{Messages: []llm.Message{llm.UserText("fixture")}, MaxTokens: 32768})
	if e != nil || m.Text() != "SYNTHETIC NO TARGET" || stop != "end_turn" || u.OutputTokens != 4 {
		t.Fatalf("%v %v %v %v", m, stop, u, e)
	}
	if _, _, _, e = p.Complete(context.Background(), llm.CompletionRequest{}); e == nil {
		t.Fatal("call budget ignored")
	}
	for _, e := range p.Stream(context.Background(), llm.CompletionRequest{}) {
		if e == nil {
			t.Fatal("fake streaming")
		}
	}
}
