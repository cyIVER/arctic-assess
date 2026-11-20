package agent

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestNativeObservationPrivateLoader(t *testing.T) {
	for _, tc := range []string{"valid", "policy_changed", "phase_changed", "revoked", "wrong_task", "fixture_cannot_mint_public_status"} {
		t.Run(tc, func(t *testing.T) {
			d, phase := rolePermitFixture(t)
			roles := []any{}
			for _, r := range []string{"goals", "mainagent", "planner", "worker", "reporter"} {
				row := map[string]any{"role": r, "purpose": "run", "intent_id": 0, "session_id": "exp200-" + r, "catalog_sha256": strings.Repeat("b", 64)}
				if r == "mainagent" {
					row["session_id"] = "exp200-main"
				}
				if r == "worker" {
					row["dynamic_intent"] = true
					row["session_id"] = ""
				}
				if r == "reporter" {
					row["dynamic_finding"] = true
					row["session_id"] = ""
				}
				roles = append(roles, row)
			}
			phase["roles"] = roles
			writeRolePermit(t, d, phase)
			policy, opens, e := loadRoleFixture(t, d)
			if e != nil || opens != 1 {
				t.Fatalf("loader: %v opens=%d", e, opens)
			}
			cfg := ConfigFrom("codex-native", "gpt-6.1-sol", policy.Endpoint, "", "")
			construction := cfg
			construction.Native = policy
			p, e := newNativeRPC(construction)
			if e != nil {
				t.Fatal(e)
			}
			p.appAdmission = true
			tid := int64(21)
			switch tc {
			case "policy_changed":
				path := filepath.Join(d, "policy.json")
				raw, e := os.ReadFile(path)
				if e != nil {
					t.Fatal(e)
				}
				if e = os.WriteFile(path, []byte(strings.Replace(string(raw), `"native_tools":false`, `"native_tools":true`, 1)), 0600); e != nil {
					t.Fatal(e)
				}
			case "phase_changed":
				phase["authority_generation"] = int64(99)
				writeRolePermit(t, d, phase)
			case "revoked":
				p.RevokeNativeRolePhase()
			case "wrong_task":
				tid = 22
			case "fixture_cannot_mint_public_status":
				if _, e = ObserveNativeAdmission(context.Background(), p, cfg, 21, 200); e == nil {
					t.Fatal("fixture admitted public status")
				}
				return
			}
			got, e := observeNativeAdmission(context.Background(), p, cfg, tid, 200)
			if tc != "valid" {
				if e == nil {
					t.Fatal("invalid live configuration admitted")
				}
				return
			}
			if e != nil || !got.ProviderAdmitted || got.ExecutorConfigVerified || len(got.Catalogs) != 5 {
				t.Fatalf("valid observation: %+v %v", got, e)
			}
			executorConfig := map[string]any{"schema_version": 1, "reviewed": true, "phase_id": got.PhaseID, "authority_generation": got.Generation, "task_id": got.TaskID, "exploration_id": got.ExplorationID, "executor_id": got.ExecutorID, "network_policy_id": got.NetworkPolicyID, "fixture_origin": got.FixtureOrigin, "control_socket": "/run/artex-native/not-listening.sock"}
			configRaw, _ := json.Marshal(executorConfig)
			for name, body := range map[string][]byte{"executor.json": configRaw, "executor.key": []byte(strings.Repeat("k", 32))} {
				path := filepath.Join(d, name)
				if err := os.WriteFile(path, body, 0600); err != nil {
					t.Fatal(err)
				}
				if err := os.Chmod(path, 0600); err != nil {
					t.Fatal(err)
				}
			}
			if e := VerifyNativeExecutorConfiguration(p); e != nil {
				t.Fatalf("real executor configuration loader (no socket listener): %v", e)
			}
			t.Log("actual Go policy loader opened service.key once; executor config verified using raw32 key without any socket listener; observation itself does not reread service.key")
			raw, _ := json.Marshal(got)
			if strings.Contains(string(raw), policy.ServiceKey) || strings.Contains(string(raw), d) {
				t.Fatal("secret/path projected")
			}
		})
	}
}
