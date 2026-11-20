package agent

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

// All keys, identities, origins and transport replies in these tests are synthetic.
func rolePermitFixture(t *testing.T) (string, map[string]any) {
	t.Helper()
	d := nativePrivateTempDir(t)
	if e := os.Chmod(d, 0700); e != nil {
		t.Fatal(e)
	}
	var policy map[string]any
	if e := json.Unmarshal([]byte(fixturePolicy), &policy); e != nil {
		t.Fatal(e)
	}
	policy["role_phase_enabled"] = true
	raw, _ := json.Marshal(policy)
	for name, b := range map[string][]byte{"policy.json": raw, "service.key": []byte(strings.Repeat("a", 64))} {
		if e := os.WriteFile(filepath.Join(d, name), b, 0600); e != nil {
			t.Fatal(e)
		}
		if e := os.Chmod(filepath.Join(d, name), 0600); e != nil {
			t.Fatal(e)
		}
	}
	var id [16]byte
	if _, e := rand.Read(id[:]); e != nil {
		t.Fatal(e)
	}
	phase := map[string]any{
		"schema_version": 1, "phase_id": "synthetic-" + hex.EncodeToString(id[:]), "authority_generation": 1,
		"task_id": 21, "exploration_id": 200, "fixture_origin": "http://owned-assessment-fixture:8080",
		"network_policy_id": "synthetic-get-head", "executor_id": "synthetic-isolated-worker", "ledger_id": "synthetic-ledger",
		"expires_at": time.Now().UTC().Add(5 * time.Minute).Format(time.RFC3339Nano),
		"max_calls":  16, "max_aggregate_bytes": 2097152,
		"roles": []any{map[string]any{"role": "planner", "purpose": "run", "intent_id": 0, "session_id": "exp200-planner", "catalog_sha256": strings.Repeat("b", 64)}},
	}
	return d, phase
}
func writeRolePermit(t *testing.T, d string, phase map[string]any) {
	t.Helper()
	b, e := json.Marshal(phase)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(d, "phase.json"), b, 0600); e != nil {
		t.Fatal(e)
	}
	if e = os.Chmod(filepath.Join(d, "phase.json"), 0600); e != nil {
		t.Fatal(e)
	}
}
func loadRoleFixture(t *testing.T, d string) (*NativeRPCPolicy, int, error) {
	t.Helper()
	opens := 0
	p, e := loadNativePolicyForConfig(d, Config{Model: "gpt-6.1-sol"}, func(fd int, n string, f int, m uint32) (int, error) {
		if n == "service.key" {
			opens++
		}
		return syscall.Openat(fd, n, f, m)
	})
	return p, opens, e
}
func TestNativeRolePhasePermitBeforeKey(t *testing.T) {
	t.Run("valid_positive_control", func(t *testing.T) {
		d, phase := rolePermitFixture(t)
		writeRolePermit(t, d, phase)
		p, opens, e := loadRoleFixture(t, d)
		if e != nil || p == nil || opens != 1 {
			t.Fatalf("valid role phase rejected: policy=%v key_opens=%d error=%v", p != nil, opens, e)
		}
		t.Log("positive private phase reaches exactly one synthetic key open")
	})
	for _, tc := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"unknown", func(p map[string]any) { p["unexpected"] = true }},
		{"expired", func(p map[string]any) { p["expires_at"] = time.Now().Add(-time.Second).UTC().Format(time.RFC3339Nano) }},
		{"too_long", func(p map[string]any) {
			p["expires_at"] = time.Now().Add(11 * time.Minute).UTC().Format(time.RFC3339Nano)
		}},
		{"task_zero", func(p map[string]any) { p["task_id"] = 0 }},
		{"origin_path", func(p map[string]any) { p["fixture_origin"] = "http://owned-assessment-fixture:8080/escape" }},
		{"calls", func(p map[string]any) { p["max_calls"] = 17 }},
		{"bytes", func(p map[string]any) { p["max_aggregate_bytes"] = 2097153 }},
		{"no_roles", func(p map[string]any) { p["roles"] = []any{} }},
		{"unknown_role", func(p map[string]any) { p["roles"].([]any)[0].(map[string]any)["role"] = "auto" }},
		{"support", func(p map[string]any) { p["roles"].([]any)[0].(map[string]any)["purpose"] = "compact" }},
		{"session", func(p map[string]any) { p["roles"].([]any)[0].(map[string]any)["session_id"] = "exp201-planner" }},
		{"worker_no_intent", func(p map[string]any) {
			r := p["roles"].([]any)[0].(map[string]any)
			r["role"] = "worker"
			r["session_id"] = "exp200-worker-i0"
		}},
		{"bad_digest", func(p map[string]any) { p["roles"].([]any)[0].(map[string]any)["catalog_sha256"] = "invalid" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			d, p := rolePermitFixture(t)
			tc.mutate(p)
			writeRolePermit(t, d, p)
			_, opens, e := loadRoleFixture(t, d)
			if e == nil || opens != 0 {
				t.Fatalf("invalid phase: err=%v key_opens=%d", e, opens)
			}
		})
	}
	t.Run("nonprivate", func(t *testing.T) {
		d, p := rolePermitFixture(t)
		writeRolePermit(t, d, p)
		if e := os.Chmod(filepath.Join(d, "phase.json"), 0644); e != nil {
			t.Fatal(e)
		}
		_, n, e := loadRoleFixture(t, d)
		if e == nil || n != 0 {
			t.Fatalf("nonprivate permit: %v opens=%d", e, n)
		}
	})
	t.Run("duplicate_field", func(t *testing.T) {
		d, p := rolePermitFixture(t)
		writeRolePermit(t, d, p)
		path := filepath.Join(d, "phase.json")
		b, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		b = append([]byte(`{"task_id":999,`), b[1:]...)
		if e = os.WriteFile(path, b, 0600); e != nil {
			t.Fatal(e)
		}
		_, n, e := loadRoleFixture(t, d)
		if e == nil || n != 0 {
			t.Fatalf("duplicate: %v opens=%d", e, n)
		}
	})
}
