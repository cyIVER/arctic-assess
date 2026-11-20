package guard

import (
	"strings"
	"testing"
	"unicode"
)

func TestEnglishPlatformBlockPreservesReason(t *testing.T) {
	const reason = "用户 supplied policy reason"
	got := systemBlockMessage(reason)
	if !strings.Contains(got, "ARTEX platform control") || !strings.Contains(got, "not target defense") || !strings.Contains(got, "operation is forbidden") {
		t.Fatalf("missing English platform attribution or prohibition: %s", got)
	}
	if !strings.Contains(got, reason) {
		t.Fatal("policy/user reason was altered")
	}
	generated := strings.ReplaceAll(got, reason, "")
	for _, r := range generated {
		if unicode.Is(unicode.Han, r) {
			t.Fatalf("untranslated generated block text: %s", got)
		}
	}
}
