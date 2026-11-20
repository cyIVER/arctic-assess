package agent

import (
	"context"
	"encoding/json"
	actool "github.com/Autumn-27/norma/tool"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const fixturePolicy = `{"model":"gpt-6.1-sol","protocol":"artex-native-v1","endpoint":"http://172.29.88.1:18761/artex/native/v1/complete","budget_mode":"time/bytes/calls","timeout_seconds":90,"max_calls":4,"max_bytes":65536,"generation_tokens_enforced":false,"native_tools":false,"streaming":false}`

// Make the fixture satisfy the same private-directory contract as deployment.
// Record the original mode to establish (not assume) any TempDir/umask mismatch.
func nativePrivateTempDir(t *testing.T) string {
	t.Helper()
	d := t.TempDir()
	before, err := os.Stat(d)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(d, 0700); err != nil {
		t.Fatal(err)
	}
	after, err := os.Stat(d)
	if err != nil || after.Mode().Perm() != 0700 {
		t.Fatalf("private fixture directory: %v", err)
	}
	t.Logf("fixture directory mode before=%04o after=%04o", before.Mode().Perm(), after.Mode().Perm())
	return d
}

func TestNativePolicyAdmission(t *testing.T) {
	for _, tc := range []struct {
		name, body string
		mode       os.FileMode
		good       bool
	}{
		{"valid", fixturePolicy, 0600, true}, {"missing", "", 0600, false}, {"malformed", "{", 0600, false}, {"mode", fixturePolicy, 0644, false},
		{"model", strings.Replace(fixturePolicy, "gpt-6.1-sol", "other", 1), 0600, false},
		{"host", strings.Replace(fixturePolicy, "172.29.88.1", "172.29.88.2", 1), 0600, false},
		{"capability", strings.Replace(fixturePolicy, `"native_tools":false`, `"native_tools":true`, 1), 0600, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			d := nativePrivateTempDir(t)
			if tc.body != "" {
				if err := os.WriteFile(filepath.Join(d, "policy.json"), []byte(tc.body), tc.mode); err != nil {
					t.Fatal(err)
				}
				if err := os.Chmod(filepath.Join(d, "policy.json"), tc.mode); err != nil {
					t.Fatal(err)
				}
			}
			os.WriteFile(filepath.Join(d, "service.key"), []byte(strings.Repeat("a", 64)), 0600)
			p, e := loadNativePolicy(d)
			if (e == nil) != tc.good {
				t.Fatalf("admission good=%v error=%v", tc.good, e)
			}
			if tc.good {
				c := Config{Native: p, Model: "gpt-6.1-sol", Format: "codex-native", BaseURL: p.Endpoint}
				if _, e := newNativeRPC(c); e != nil {
					t.Fatal(e)
				}
			}
		})
	}
}
func TestNativePolicySymlinkAndOwnership(t *testing.T) {
	d := nativePrivateTempDir(t)
	f := filepath.Join(d, "target")
	os.WriteFile(f, []byte(fixturePolicy), 0600)
	os.Symlink(f, filepath.Join(d, "policy.json"))
	if _, e := loadNativePolicy(d); e == nil {
		t.Fatal("symlink admitted")
	}
	if privateNativeOwner(123456, 0600) {
		t.Fatal("foreign owner admitted")
	}
	if privateNativeOwner(uint32(os.Geteuid()), 0640) {
		t.Fatal("nonprivate mode admitted")
	}
}
func TestNativeSecretJSON(t *testing.T) {
	b, e := json.Marshal(Config{Native: &NativeRPCPolicy{ServiceKey: "SYNTHETIC_PRIVATE_KEY"}})
	if e != nil || strings.Contains(string(b), "SYNTHETIC_PRIVATE_KEY") || strings.Contains(string(b), "Native") {
		t.Fatalf("secret serialization: %s %v", b, e)
	}
	b, _ = json.Marshal(NativeRPCPolicy{ServiceKey: "SYNTHETIC_PRIVATE_KEY"})
	if strings.Contains(string(b), "SYNTHETIC_PRIVATE_KEY") {
		t.Fatal("key leaked")
	}
}
func TestNativeRejectUnsupportedOptions(t *testing.T) {
	c := Config{Format: "codex-native", Model: "gpt-6.1-sol", BaseURL: "http://127.0.0.1:18761/artex/native/v1/complete", Native: &NativeRPCPolicy{Endpoint: "http://127.0.0.1:18761/artex/native/v1/complete", ServiceKey: strings.Repeat("a", 64), BudgetMode: "time/bytes/calls", Timeout: 90 * time.Second, MaxCalls: 2}}
	for _, change := range []func(*Config){func(c *Config) { c.Stream = true }, func(c *Config) { c.MaxTokens = 1 }, func(c *Config) { c.Proxy = "http://127.0.0.1" }, func(c *Config) { c.Model = "other" }} {
		x := c
		change(&x)
		if _, e := newNativeRPC(x); e == nil {
			t.Fatal("unsupported option accepted")
		}
	}
	if _, e := c.NewProvider(); e == nil {
		t.Fatal("in-memory policy is not startup authority")
	}
}
func TestNativeBashGuardBeforeExecutor(t *testing.T) {
	n := 0
	d := nativePrivateTempDir(t)
	underlying := actool.Build(actool.Spec{Name: "Bash", Run: func(context.Context, json.RawMessage, *actool.ToolContext) (actool.Result, error) {
		n++
		return actool.Text("fixture"), nil
	}})
	tool := nativeBash(underlying, d)
	for _, in := range []string{`{}`, `{"command":"id"}`, `{"command":"` + nativeCurl + `","run_in_background":false}`, `{"command":"` + nativeCurl + `","timeout_ms":10000,"other":1}`} {
		if _, e := tool.Call(context.Background(), json.RawMessage(in), &actool.ToolContext{WorkingDir: d}); e == nil {
			t.Fatal("guard allowed", in)
		}
	}
	if n != 0 {
		t.Fatal("executor reached on denial")
	}
	in, _ := json.Marshal(map[string]any{"command": nativeCurl, "timeout_ms": 10000})
	if _, e := tool.Call(context.Background(), in, &actool.ToolContext{WorkingDir: d}); e != nil {
		t.Fatal(e)
	}
	if n != 1 {
		t.Fatal(n)
	}
	if _, e := tool.Call(context.Background(), in, &actool.ToolContext{WorkingDir: d + "/other"}); e == nil {
		t.Fatal("workdir drift accepted")
	}
	tools := nativeLabTools(d)
	if len(tools) != 1 || tools[0].Name() != "Bash" {
		t.Fatal("inventory")
	}
}
