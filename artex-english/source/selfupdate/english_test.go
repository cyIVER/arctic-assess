package selfupdate

import (
	"net/url"
	"strings"
	"testing"
)

func TestEnglishUpdateDisabled(t *testing.T) {
	if !strings.Contains(ErrDisabled.Error(), "Online updates disabled") {
		t.Fatal(ErrDisabled)
	}
	if got := orUnknown(""); got != "Unknown version" {
		t.Fatal(got)
	}
	if err := checkURL(&url.URL{Scheme: "http", Host: "github.com", Path: "/x"}); err == nil || !strings.Contains(err.Error(), "Non-HTTPS URL refused") {
		t.Fatalf("%v", err)
	}
}
