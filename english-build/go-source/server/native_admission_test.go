package server

import (
	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/sidequestion"
	"testing"
)

func TestNativeExplicitChatProfileNeverFallsBack(t *testing.T) {
	f := newSideHTTPFixture(t)
	fallback := agent.NewChatAgent(&scriptedLLMProvider{}, "fixture", t.TempDir(), nil, 0)
	f.s.cfgMu.Lock()
	f.s.chatAgent = fallback
	f.s.cfgMu.Unlock()
	if f.s.chatAgentRef() == nil {
		t.Fatal("fixture needs nonnil global chat")
	}
	if f.s.resolveChatAgent(&db.Conversation{}) != fallback {
		t.Fatal("missing global positive control")
	}
	id := int64(9223372036854775807)
	if f.s.resolveChatAgent(&db.Conversation{LLMProfileID: &id}) != nil {
		t.Fatal("unavailable explicit profile fell back")
	}
	for _, tc := range []struct {
		name string
		p    db.LLMProfile
	}{
		{"malformed", db.LLMProfile{Name: "synthetic-malformed", Format: "anthropic", Model: "fixture", APIKey: ""}},
		{"construction-fail", db.LLMProfile{Name: "synthetic-construction-fail", Format: "openai", Model: "fixture", BaseURL: "http://127.0.0.1:1", Proxy: "://invalid", APIKey: "synthetic-never-used"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			id, e := f.m.pg.SaveProfile(&tc.p)
			if e != nil {
				t.Fatal(e)
			}
			defer f.m.pg.DeleteProfile(id)
			if tc.name == "construction-fail" {
				cfg, ok := f.s.loadProfileConfig(id)
				if !ok {
					t.Fatal("fixture must pass DB/config admission before constructor rejection")
				}
				if _, err := cfg.NewProvider(); err == nil {
					t.Fatal("fixture must fail construction before any network request")
				}
			}
			if f.s.resolveChatAgent(&db.Conversation{LLMProfileID: &id}) != nil {
				t.Fatal("invalid explicit profile fell back")
			}
		})
	}
}
func TestNativeSideQuestionExplicitlyUnsupported(t *testing.T) {
	s := &Server{}
	if _, e := s.sideProvider(sidequestion.Model{Format: "codex-native"}); e == nil {
		t.Fatal("native side streaming admitted")
	}
}
