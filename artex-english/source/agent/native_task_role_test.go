package agent

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestNativeWorkerTaskTemplate(t *testing.T) {
	_, phase := rolePermitFixture(t)
	raw, _ := json.Marshal(phase)
	if _, err := parseNativePhase(raw); err != nil {
		t.Fatalf("positive exact planner permit rejected: %v", err)
	}
	role := map[string]any{"role": "worker", "purpose": "run", "intent_id": 0, "session_id": "", "dynamic_intent": true, "catalog_sha256": strings.Repeat("c", 64)}
	phase["roles"] = []any{role}
	phase["phase_id"] = phase["phase_id"].(string) + "-worker"
	// A template authorizes no intent by itself: only the DB-backed launcher may bind it.
	raw, _ = json.Marshal(phase)
	if _, err := parseNativePhase(raw); err != nil {
		t.Fatalf("explicit task-bound worker template rejected: %v", err)
	}
	for _, mutate := range []func(){func() { role["intent_id"] = 5 }, func() { role["intent_id"] = 0; role["session_id"] = "exp200-worker-i5" }, func() { role["session_id"] = ""; role["role"] = "reporter" }} {
		mutate()
		raw, _ = json.Marshal(phase)
		if _, err := parseNativePhase(raw); err == nil {
			t.Fatal("ambiguous or unsupported template accepted")
		}
	}
}
