package server

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
)

// Fixture was emitted by the real web/src/lib/chat-mentions.ts mentionToken.
func TestChatMentionFrontendGeneratedTokens(t *testing.T) {
	blob, err := os.ReadFile("testdata/english_mentions.json")
	if err != nil {
		t.Fatal(err)
	}
	var rows []struct {
		Kind  string `json:"kind"`
		Token string `json:"token"`
	}
	if err := json.Unmarshal(blob, &rows); err != nil {
		t.Fatal(err)
	}
	if len(rows) != 9 {
		t.Fatalf("frontend category count = %d", len(rows))
	}
	for _, row := range rows {
		t.Run(row.Kind, func(t *testing.T) {
			refs, err := parseChatMentions(row.Token)
			if err != nil || len(refs) != 1 || refs[0].Kind != row.Kind || refs[0].ID != 42 {
				t.Fatalf("frontend token %q: %+v %v", row.Token, refs, err)
			}
			if !strings.Contains(row.Token, "用户 supplied evidence") {
				t.Fatal("user label was changed")
			}
		})
	}
}

// Frontend category labels are wire tokens, not trusted record labels.
func TestChatMentionEnglishLegacyCompatibility(t *testing.T) {
	cases := []struct{ english, legacy, kind string }{
		{"Finding", "漏洞", "finding"}, {"Asset", "资产", "asset"},
		{"Company", "企业", "company"}, {"Endpoint", "接口", "endpoint"},
		{"IP", "IP", "ip"}, {"App", "应用", "app"},
		{"Domain", "域名", "root_domain"}, {"Subdomain", "子域名", "subdomain"},
		{"Service", "服务", "service"},
	}
	for _, c := range cases {
		t.Run(c.english, func(t *testing.T) {
			for _, label := range []string{c.english, c.legacy} {
				refs, err := parseChatMentions(fmt.Sprintf("@[%s#42 用户 supplied evidence]", label))
				if err != nil || len(refs) != 1 || refs[0].Kind != c.kind || refs[0].ID != 42 {
					t.Fatalf("token %s: refs=%+v err=%v", label, refs, err)
				}
				for _, id := range []string{"0", "999999999999999999999999"} {
					if _, err := parseChatMentions(fmt.Sprintf("@[%s#%s]", label, id)); err == nil {
						t.Errorf("accepted invalid ID for %s: %s", label, id)
					}
				}
				var many strings.Builder
				for i := 1; i <= 11; i++ {
					fmt.Fprintf(&many, "@[%s#%d] ", label, i)
				}
				if _, err := parseChatMentions(many.String()); err == nil {
					t.Errorf("accepted 11 references for %s", label)
				}
				if _, err := composeChatMentionMessage(nil, fmt.Sprintf("@[%s#42]", label)); err == nil {
					t.Errorf("recognized reference bypassed unavailable record data: %s", label)
				}
			}
			refs, err := parseChatMentions(fmt.Sprintf("@[%s#42 first] @[%s#42 second]", c.english, c.legacy))
			if err != nil || len(refs) != 1 {
				t.Fatalf("alias deduplication: %+v %v", refs, err)
			}
		})
	}
	const plain = "用户 content user@example.com @Finding @[Unknown#42]"
	if got, err := composeChatMentionMessage(nil, plain); err != nil || got != plain {
		t.Fatalf("plain user content changed: %q %v", got, err)
	}
}
