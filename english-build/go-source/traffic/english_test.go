package traffic

import (
	"strings"
	"testing"
)

func TestEnglishTrafficSearchContract(t *testing.T) {
	for _, want := range []string{"host is required", "traffic_get", "bind_finding_traffic", "3", "10", "Chinese"} {
		if !strings.Contains(TrafficSearchDescription, want) {
			t.Errorf("missing %q", want)
		}
	}
	if _, _, err := normalizeSearchHost(""); err == nil || err.Error() != "host is required" {
		t.Fatalf("empty host: %v", err)
	}
}
