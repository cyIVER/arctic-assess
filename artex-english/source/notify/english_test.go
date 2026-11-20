package notify

import (
	"encoding/json"
	"strings"
	"testing"
	"unicode"
)

func TestEnglishNotificationRenderersPreserveUnicodeEvidence(t *testing.T) {
	m := Message{Items: []Item{{Name: "原始证据", Severity: "high", Summary: "目标摘要", VulnClass: "SQL injection", Assets: []string{"example.com"}, DetailURL: "https://example.com/f/1", FromStatus: "pending", ToStatus: "fixed"}}, HomeURL: "https://example.com"}
	md, kept := markdownBody(m, 4096)
	if kept != 1 {
		t.Fatal(kept)
	}
	tg, kept := telegramHTML(m)
	if kept != 1 {
		t.Fatal(kept)
	}
	card, kept := feishuCard(m)
	if kept != 1 {
		t.Fatal(kept)
	}
	raw, err := json.Marshal(card)
	if err != nil {
		t.Fatal(err)
	}
	for name, got := range map[string]string{"markdown": md, "telegram": tg, "html": htmlBody(m, 0), "feishu": string(raw)} {
		for _, want := range []string{"原始证据", "目标摘要", "Status change", "Pending", "Fixed", "View details"} {
			if !strings.Contains(got, want) {
				t.Errorf("%s missing %q: %s", name, want, got)
			}
		}
		prose := strings.ReplaceAll(strings.ReplaceAll(got, "原始证据", ""), "目标摘要", "")
		for _, r := range prose {
			if unicode.Is(unicode.Han, r) {
				t.Errorf("%s generated non-English text: %s", name, prose)
				break
			}
		}
	}
	for _, tc := range []struct {
		kind string
		cfg  map[string]any
	}{{KindWebhook, map[string]any{"url": "https://example.com/hook"}}, {KindEmail, map[string]any{"host": "smtp.example.com", "port": 587, "from": "a@example.com", "to": []any{"b@example.com"}}}} {
		ch, _ := Get(tc.kind)
		if err := ch.Validate(tc.cfg); err != nil {
			t.Fatalf("valid %s config rejected: %v", tc.kind, err)
		}
	}
}

func TestEnglishNotificationLabels(t *testing.T) {
	if got := SeverityLabel("high"); got != "🟠 High" {
		t.Errorf("high label = %q", got)
	}
	if got := StatusLabel("pending"); got != "Pending" {
		t.Errorf("pending label = %q", got)
	}
	if got := assetLine([]string{"one", "two", "three"}, 2); got != "one, two (3 total)" {
		t.Errorf("asset line = %q", got)
	}
	if got := (Item{}).Title(); got != "(Unnamed finding)" {
		t.Errorf("fallback title = %q", got)
	}
	for _, kind := range Kinds() {
		ch, _ := Get(kind)
		if err := ch.Validate(map[string]any{}); err == nil {
			t.Errorf("%s accepted missing fields", kind)
		} else if strings.ContainsAny(err.Error(), "缺少至少端口") {
			t.Errorf("%s error is not English: %v", kind, err)
		}
	}
}
