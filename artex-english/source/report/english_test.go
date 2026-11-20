package report

import (
	"encoding/csv"
	"encoding/json"
	"github.com/Autumn-27/artex/db"
	"strings"
	"testing"
	"time"
)

func TestEnglishFindingExportsRetainUnicodeData(t *testing.T) {
	stamp := time.Unix(0, 0).UTC()
	f := &db.DBFinding{ID: 12, Name: "原始证据", Severity: "high", Status: "pending", Summary: "原始摘要", Evidence: "原始流量", Report: "原始报告", EvidenceVersion: 2, ReportEvidenceVersion: 1, CreatedAt: stamp}
	for name, got := range map[string]string{"summary": FindingsMarkdown([]*db.DBFinding{f}, stamp), "single": SingleFindingMarkdown(f, stamp)} {
		for _, want := range []string{f.Name, f.Summary, f.Evidence, f.Report, "Evidence has changed; the detailed report needs updating.", "## Linked traffic evidence"} {
			if !strings.Contains(got, want) {
				t.Errorf("%s missing %q", name, want)
			}
		}
	}
	data := FindingsCSV([]*db.DBFinding{f})
	if !strings.HasPrefix(string(data), "\xEF\xBB\xBF") {
		t.Fatal("missing UTF-8 BOM")
	}
	rows, err := csv.NewReader(strings.NewReader(strings.TrimPrefix(string(data), "\xEF\xBB\xBF"))).ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 || len(rows[0]) != 10 || rows[0][1] != "Name" || rows[0][8] != "Traffic evidence count" || rows[1][1] != f.Name {
		t.Fatalf("CSV mismatch: %#v", rows)
	}
	if got := FindingFilename(f); !strings.Contains(got, f.Name) || !strings.HasSuffix(got, "__12.md") {
		t.Fatalf("filename lost evidence: %q", got)
	}
}
func TestEnglishReportPreservesEvidence(t *testing.T) {
	evidence := "用户原始证据 <tag>"
	payload, _ := json.Marshal(map[string]any{"name": "Finding", "severity": "high", "evidence": map[string]any{"poc": evidence}})
	got := Markdown(Input{GeneratedAt: time.Unix(0, 0).UTC(), Findings: []*db.Node{{Payload: payload}}})
	for _, want := range []string{"# Penetration Test Report", "**Task goal**", "## Summary", "## Findings", "**PoC / Evidence:**", evidence} {
		if !strings.Contains(got, want) {
			t.Errorf("missing %q in %s", want, got)
		}
	}
}
