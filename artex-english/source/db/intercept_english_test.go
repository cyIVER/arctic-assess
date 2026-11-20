package db

import (
	"strings"
	"testing"
)

func TestInterceptSourceEnglishLegacy(t *testing.T) {
	for _, tc := range []struct {
		name         string
		rule         int64
		reason, want string
	}{
		{"english", 0, "[Model] Allowed", "model"},
		{"legacy", 0, "[模型] historical 用户 evidence", "model"},
		{"rule_precedes_english", 7, "[Model] reason", "rule"},
		{"rule_precedes_legacy", 7, "[模型] reason", "rule"},
		{"unknown", 0, "original 用户 evidence", "unknown"},
		{"embedded_not_prefix", 0, "evidence [Model]", "unknown"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			before := tc.reason
			if got := interceptSource(tc.rule, tc.reason); got != tc.want {
				t.Fatalf("source=%q want=%q", got, tc.want)
			}
			if tc.reason != before {
				t.Fatal("original evidence changed")
			}
		})
	}
}
func TestApprovalSQLRecognizesEnglishLegacy(t *testing.T) {
	for _, marker := range []string{"[Model]%", "[模型]%"} {
		if !strings.Contains(approvalDecisionSource, marker) {
			t.Errorf("approval query missing marker %q", marker)
		}
	}
	if !strings.Contains(approvalDecisionSource, "COALESCE(NULLIF(ip.decision_source,''), CASE") || strings.Index(approvalDecisionSource, "ip.rule_id IS NOT NULL") > strings.Index(approvalDecisionSource, "ip.reason LIKE") {
		t.Fatal("persisted source or rule precedence changed")
	}
}
