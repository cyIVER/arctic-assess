package agent

import (
	"context"
	"encoding/json"
	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/permission"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestNativeRejectedSettingsNeverOpenKey(t *testing.T) {
	d := nativePrivateTempDir(t)
	os.WriteFile(filepath.Join(d, "policy.json"), []byte(fixturePolicy), 0600)
	os.WriteFile(filepath.Join(d, "service.key"), []byte(strings.Repeat("a", 64)), 0600)
	for _, tc := range []struct {
		name   string
		change func(*Config)
	}{
		{"URI", func(c *Config) { c.BaseURL = "http://127.0.0.1:12345/artex/native/v1/complete" }},
		{"badURI", func(c *Config) { c.BaseURL = "https://outside.invalid/" }},
		{"thinking", func(c *Config) { c.ThinkingType = "enabled" }},
		{"reasoning", func(c *Config) { c.ReasoningEffort = "high" }},
		{"header", func(c *Config) { c.SessionHeaderKey = "X-Session" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c := Config{Model: "gpt-6.1-sol"}
			tc.change(&c)
			reads := 0
			spy := func(fd int, n string, f int, m uint32) (int, error) {
				if n == "service.key" {
					reads++
				}
				return syscall.Openat(fd, n, f, m)
			}
			if _, e := loadNativePolicyForConfig(d, c, spy); e == nil {
				t.Fatal("rejected setting admitted")
			}
			if reads != 0 {
				t.Fatalf("key opens=%d, want ZERO", reads)
			}
		})
	}
	reads := 0
	spy := func(fd int, n string, f int, m uint32) (int, error) {
		if n == "service.key" {
			reads++
		}
		return syscall.Openat(fd, n, f, m)
	}
	c := Config{Format: "codex-native", Model: "gpt-6.1-sol", BaseURL: "http://172.29.88.1:18761/artex/native/v1/complete"}
	p, e := loadNativePolicyForConfig(d, c, spy)
	if e != nil || reads != 1 {
		t.Fatalf("valid policy: %v opens=%d", e, reads)
	}
	c.Native = p
	if _, e = newNativeRPC(c); e != nil {
		t.Fatal(e)
	}
}

func TestNativeNormaNonStreamingEmptyTools(t *testing.T) {
	raw := os.Getenv("SYNTHETIC_PORTS")
	if raw == "" {
		t.Skip("Python fixture required")
	}
	// The existing cross-language test owns the persistent Python text fixture's
	// finite budget, so use separate processes? Its text fixture permits 8 calls.
	ports := map[string]string{}
	if e := json.Unmarshal([]byte(raw), &ports); e != nil {
		t.Fatal(e)
	}
	endpoint := "http://127.0.0.1:" + ports["text"] + "/artex/native/v1/complete"
	for _, hint := range []int{8192, 1500} {
		c := ConfigFrom("codex-native", "gpt-6.1-sol", endpoint, "", "")
		c.Native = &NativeRPCPolicy{Endpoint: endpoint, ServiceKey: strings.Repeat("f", 64), BudgetMode: "time/bytes/calls", Timeout: 2 * time.Second, MaxCalls: 2}
		p, e := newNativeRPC(c)
		if e != nil {
			t.Fatal(e)
		}
		reply, e := agentcore.Run(context.Background(), agentcore.Options{Provider: p, SystemPrompt: []string{"SYNTHETIC NO TARGET"}, PermissionMode: permission.ModeBypass, MaxTurns: 1, MaxTokens: hint, NonStreaming: true, DisableBackgroundTasks: true}, "SYNTHETIC NO TARGET")
		if e != nil || strings.TrimSpace(reply) != "SYNTHETIC NO TARGET" {
			t.Fatalf("Norma harness hint=%d reply=%q err=%v", hint, reply, e)
		}
		t.Logf("actual Norma nonstream empty-tools diagnostic hint %d; not full connection-admission/compaction runtime", hint)
	}
}
