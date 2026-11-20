package server

import (
	"github.com/Autumn-27/artex/db"
	"strings"
	"testing"
	"unicode"
)

// Existing-behavior regression: both producer generations must pass through unchanged.
func TestRuntimeEnglishApprovalCompatibility(t *testing.T) {
	for _, summary := range []string{"Tool Bash requests approval (#42)", "工具 Bash 请求审批 (#42)"} {
		for _, reason := range []string{"[Model] review", "[模型] review"} {
			got := activityDTO(db.Activity{Kind: "intercept", Tool: "Bash", Summary: summary, Detail: reason})
			if got.Summary != summary || got.Detail != reason || got.Tool != "Bash" {
				t.Fatalf("approval evidence rewritten: %+v", got)
			}
		}
	}
}

func TestRuntimeEnglishTaskContext(t *testing.T) {
	got := finalTriggerMessage(triggeredRun{taskID: 72, taskDesc: "用户目标", taskGoal: "保留证据", message: "body"})
	if !strings.HasPrefix(got, "[Task: #72 用户目标 (goal: 保留证据)]") {
		t.Fatalf("reporter Task: # contract: %q", got)
	}
}

func TestRuntimeEnglishValidation(t *testing.T) {
	for _, tc := range []struct{ kind, pattern, want string }{
		{"exact_ip", "not-an-ip", "exact_ip is not a valid IP address: not-an-ip"},
		{"cidr", "not-a-network", "cidr is not a valid network (for example 192.168.0.0/16): not-a-network"},
		{"unknown", "example.com", "Invalid kind: unknown"},
	} {
		t.Run(tc.kind, func(t *testing.T) {
			req := assetInterceptRuleReq{Kind: tc.kind, Pattern: tc.pattern}
			err := validateAssetInterceptRuleReq(&req)
			if err == nil || err.Error() != tc.want {
				t.Fatalf("error=%v want %q", err, tc.want)
			}
		})
	}
	for _, kind := range []string{"exact_ip", "cidr", "fuzzy_domain"} {
		pattern := "例子.example"
		if kind == "exact_ip" {
			pattern = " 192.0.2.1 "
		}
		if kind == "cidr" {
			pattern = "192.0.2.0/24"
		}
		req := assetInterceptRuleReq{Kind: kind, Pattern: pattern}
		if err := validateAssetInterceptRuleReq(&req); err != nil {
			t.Fatal(err)
		}
	}
}

func TestRuntimeEnglishToolDescriptions(t *testing.T) {
	s := &Server{}
	for _, tool := range s.platformTools() {
		t.Run(tool.Name(), func(t *testing.T) {
			for _, r := range tool.Description() {
				if unicode.Is(unicode.Han, r) {
					t.Fatalf("untranslated generated description: %s", tool.Description())
				}
			}
		})
	}
}

func TestRuntimeEnglishTruncationPreservesUnicode(t *testing.T) {
	if got := trunc("证据abc", 2); got != "证据…(truncated, 5 characters total)" {
		t.Fatalf("got %q", got)
	}
	if got := trunc("证据", 2); got != "证据" {
		t.Fatalf("untruncated user evidence changed: %q", got)
	}
	if !strings.Contains(reporterToolCallMessage, "evidence_version") {
		t.Fatal("reporter version contract lost")
	}
}
