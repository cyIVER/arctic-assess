package intercept

import (
	"encoding/json"
	"strings"
	"testing"
	"unicode"
)

func TestEnglishGeneratedDefaultsPreserveSuppliedNames(t *testing.T) {
	for _, tc := range []struct{ action, want string }{
		{"deny", "Intercept rule [用户 supplied] prohibits this tool"},
		{"ask", "Intercept rule [用户 supplied] requires user approval; please wait"},
	} {
		if got := defaultMessage(tc.action, "用户 supplied"); got != tc.want {
			t.Fatalf("generated message or supplied name changed: %q", got)
		}
	}
	for _, prompt := range []string{JudgeContextBoundary, JudgeOutputContract, DefaultJudgePrompt} {
		if strings.IndexFunc(prompt, func(r rune) bool { return unicode.Is(unicode.Han, r) }) >= 0 {
			t.Fatal("generated built-in judge prompt is not English")
		}
	}
}
func TestEnglishVerdictStrictRejections(t *testing.T) {
	reason := "Actual operation: Read file; Consequence on success: Return content; Matched rule: A5"
	for _, action := range []string{"allow", "ask", "deny"} {
		raw, _ := json.Marshal(map[string]string{"decision": action, "comment": reason})
		got := ParseVerdict(string(raw))
		if got.Action != action || got.Reason != reason {
			t.Fatalf("valid English verdict lost: %+v", got)
		}
	}
	raw, _ := json.Marshal(map[string]string{"decision": "allow", "comment": reason})
	for _, invalid := range []string{
		string(raw) + " trailing prose", string(raw) + string(raw),
		`{"decision":"allow","decision":"deny","comment":"` + reason + `"}`,
		`{"decision":"allow","comment":"` + reason + `","extra":"ignored"}`,
		`{"decision":"allow","comment":null}`,
		`{"decision":"allow","comment":"Actual operation: Read file; 成功后的后果：Return content; Matched rule: A5"}`,
	} {
		if got := ParseVerdict(invalid); got.Action != "" {
			t.Fatalf("accepted ambiguous or incomplete English verdict: %+v", got)
		}
	}
	raw, _ = json.Marshal(map[string]string{"decision": "allow", "comment": reason + strings.Repeat("x", 2401)})
	if got := ParseVerdict(string(raw)); got.Action != "" {
		t.Fatal("English contract bypassed existing byte limit")
	}
}
