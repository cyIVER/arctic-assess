package agent

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	actool "github.com/Autumn-27/norma/tool"
)

func TestEnglishDomainToolCatalog(t *testing.T) {
	seeds := BuiltinToolSeeds()
	if len(seeds) == 0 {
		t.Fatal("empty tool catalog")
	}
	for _, seed := range seeds {
		t.Run(seed.Key, func(t *testing.T) {
			assertEnglishBuiltin(t, seed.Desc)
			b, err := json.Marshal(seed.Schema)
			if err != nil {
				t.Fatal(err)
			}
			assertEnglishBuiltin(t, string(b))
		})
	}
}

func TestEnglishDomainToolErrors(t *testing.T) {
	ts := NewToolSet(nil, "")
	for _, tool := range []actool.CoreTool{ts.insertAssets(), ts.addCompanyScope(), ts.listAssets(), ts.listCompanies(), ts.addTaskScope(), ts.listUntestedAssets(), ts.setGoals(), ts.setConstraints(), ts.nodeDetail(), ts.killWorkTool(), ts.steerWorkTool()} {
		t.Run(tool.Name(), func(t *testing.T) {
			result, err := tool.Call(context.Background(), json.RawMessage(`{}`), nil)
			if err != nil {
				t.Fatal(err)
			}
			if !result.IsError {
				t.Fatal("missing dependency/context must remain an error")
			}
			b, err := json.Marshal(result)
			if err != nil {
				t.Fatal(err)
			}
			assertEnglishBuiltin(t, string(b))
		})
	}
}

func TestEnglishTerminalAndAuxiliaryGuidance(t *testing.T) {
	for _, c := range []*AbortCause{AbortPausedByUser, AbortPausedByOrchestrator, AbortTaskDeleted, AbortPausedOnReload, AbortGoalMet, AbortSettleDrainTimeout, AbortKilledByPlanner, AbortWorkPausedByUser, AbortWorkCancelledByUser, AbortWorkFinished, AbortPausedRaceGuard, AbortChatStoppedByUser, AbortChatPausedWithTask, AbortChatTurnFinished, AbortShutdown, AbortRunHardTimeout} {
		t.Run(c.Code, func(t *testing.T) {
			assertEnglishBuiltin(t, c.Short)
			assertEnglishBuiltin(t, c.Text)
			ctx, cancel := context.WithCancelCause(context.Background())
			cancel(c)
			code, short, text, ok := AbortReason(ctx)
			if !ok || code != c.Code || short != c.Short || text != c.Text {
				t.Fatal("cause identity changed")
			}
		})
	}
	for reason, hint := range reasonHint {
		t.Run(string(reason), func(t *testing.T) { assertEnglishBuiltin(t, hint) })
	}
	for _, text := range []string{RetesterDefaultPrompt, compressionSystemPrompt, findingTrafficGuidance, chatWorkDirSpec("/owned"), (WriteCounts{Facts: 1, Assets: 2, Findings: 3}).String()} {
		assertEnglishBuiltin(t, text)
	}
	if !strings.Contains(RetesterDefaultPrompt, "inconclusive") {
		t.Fatal("retest evidence threshold lost")
	}
}
