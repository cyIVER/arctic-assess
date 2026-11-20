package agent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func TestNativeExecutorPrivateConfigBeforeKey(t *testing.T) {
	for _, tc := range []string{"valid", "unreviewed", "task", "exploration", "phase", "generation", "executor", "network", "origin", "relative_socket", "unclean_socket", "unknown", "nonprivate_config", "config_symlink", "nonprivate_key", "key_symlink", "short_key", "long_key", "hardlink_key", "nonprivate_dir"} {
		t.Run(tc, func(t *testing.T) {
			dir, rawPhase := rolePermitFixture(t)
			rawPhase["roles"] = []any{map[string]any{"role": "worker", "purpose": "run", "dynamic_intent": true, "intent_id": 0, "session_id": "", "catalog_sha256": strings.Repeat("a", 64)}}
			raw, _ := json.Marshal(rawPhase)
			phase, e := parseNativePhase(raw)
			if e != nil {
				t.Fatal(e)
			}
			c := map[string]any{"schema_version": 1, "reviewed": true, "phase_id": phase.PhaseID, "authority_generation": phase.Generation, "task_id": phase.TaskID, "exploration_id": phase.ExplorationID, "executor_id": phase.ExecutorID, "network_policy_id": phase.NetworkPolicyID, "fixture_origin": phase.FixtureOrigin, "control_socket": "/run/artex-native/control.sock"}
			switch tc {
			case "unreviewed":
				c["reviewed"] = false
			case "task":
				c["task_id"] = 22
			case "exploration":
				c["exploration_id"] = 201
			case "phase":
				c["phase_id"] = "wrong"
			case "generation":
				c["authority_generation"] = 2
			case "executor":
				c["executor_id"] = "wrong"
			case "network":
				c["network_policy_id"] = "wrong"
			case "origin":
				c["fixture_origin"] = "http://wrong:8080"
			case "relative_socket":
				c["control_socket"] = "x.sock"
			case "unclean_socket":
				c["control_socket"] = "/run/artex-native/../x.sock"
			case "unknown":
				c["extra"] = true
			}
			raw, _ = json.Marshal(c)
			config := filepath.Join(dir, "executor.json")
			key := filepath.Join(dir, "executor.key")
			for p, b := range map[string][]byte{config: raw, key: []byte(strings.Repeat("k", 32))} {
				if e = os.WriteFile(p, b, 0600); e != nil {
					t.Fatal(e)
				}
				if e = os.Chmod(p, 0600); e != nil {
					t.Fatal(e)
				}
			}
			switch tc {
			case "nonprivate_config":
				e = os.Chmod(config, 0644)
			case "nonprivate_key":
				e = os.Chmod(key, 0644)
			case "nonprivate_dir":
				e = os.Chmod(dir, 0755)
			case "config_symlink":
				e = os.Rename(config, config+".real")
				if e == nil {
					e = os.Symlink("executor.json.real", config)
				}
			case "key_symlink":
				e = os.Rename(key, key+".real")
				if e == nil {
					e = os.Symlink("executor.key.real", key)
				}
			case "short_key":
				e = os.WriteFile(key, []byte(strings.Repeat("k", 31)), 0600)
			case "long_key":
				e = os.WriteFile(key, []byte(strings.Repeat("k", 33)), 0600)
			case "hardlink_key":
				e = os.Link(key, key+".link")
			}
			if e != nil {
				t.Fatal(e)
			}
			opens := 0
			executor, e := loadNativeExecutor(dir, phase, func(fd int, name string, flags int, mode uint32) (int, error) {
				if name == "executor.key" {
					opens++
				}
				return syscall.Openat(fd, name, flags, mode)
			})
			if tc == "valid" {
				if e != nil || executor == nil || opens != 1 {
					t.Fatalf("valid private config rejected: opens=%d err=%v", opens, e)
				}
				return
			}
			if e == nil || executor != nil {
				t.Fatal("invalid config admitted")
			}
			keyCase := strings.Contains(tc, "key")
			if !keyCase && opens != 0 {
				t.Fatalf("invalid nonsecret config opened key %d times", opens)
			}
		})
	}
}
