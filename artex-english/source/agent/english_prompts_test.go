package agent

import (
	"encoding/json"
	"github.com/Autumn-27/artex/db"
	actool "github.com/Autumn-27/norma/tool"
	"strings"
	"testing"
	"unicode"

	"github.com/Autumn-27/norma/harness"
)

func assertEnglishBuiltin(t *testing.T, text string) {
	t.Helper()
	if strings.TrimSpace(text) == "" {
		t.Fatal("empty built-in prompt")
	}
	for _, r := range text {
		if unicode.Is(unicode.Han, r) {
			t.Fatalf("built-in prompt contains untranslated prose: %q", text)
		}
	}
}

func TestEnglishStandalonePrompts(t *testing.T) {
	for name, text := range map[string]string{"auto": autoDefaultTmpl, "pentest": pentestDefaultTmpl, "assistant": DefaultAssistantPrompt, "reporter": ReporterDefaultPrompt} {
		t.Run(name, func(t *testing.T) { assertEnglishBuiltin(t, text) })
	}
	for _, token := range []string{"finding_id", "finding_node_id", "get_finding_traffic", "update_finding_report", "evidence_version", "version", "binding_id"} {
		if !strings.Contains(ReporterDefaultPrompt, token) {
			t.Errorf("reporter lost protocol guidance %q", token)
		}
	}
	if !strings.Contains(DefaultAssistantPrompt, "English") || !strings.Contains(ReporterDefaultPrompt, "English") {
		t.Fatal("built-in assistant and reporter must request English, not merely have English UI text")
	}
}

func TestEnglishWrapupPolicies(t *testing.T) {
	for name, text := range map[string]string{"planner": plannerWrapUpDefault, "mainagent": mainAgentWrapUpDefault, "generic": genericWrapUpDefault, "worker_task": workerTaskTimeoutDefault, "planner_task": plannerTaskTimeoutDefault} {
		t.Run(name, func(t *testing.T) { assertEnglishBuiltin(t, text) })
	}
	for _, key := range []string{"worker", "planner", "mainagent", "custom"} {
		if WrapupTurnsDefault(key) != 10 {
			t.Fatalf("%s wrap-up turn budget changed", key)
		}
	}
	st := wrapupSettlementForTask("planner", []string{"Bash"}, true)
	if st.PromptByReason[harness.ReasonTimeout] != plannerTaskTimeoutDefault || st.PromptByReason[harness.ReasonMaxTurns] != plannerWrapUpDefault || len(st.DisabledTools) != 1 || st.DisabledTools[0] != "Bash" {
		t.Fatal("deadline/reason/tool policy changed")
	}
}

func TestUnicodePromptOverridePreserved(t *testing.T) {
	old := WrapupOverride
	defer func() { WrapupOverride = old }()
	const userText = "用户原文 — preserve supplied content"
	WrapupOverride = func(string) (string, bool) { return userText, true }
	if got := resolveWrapup("planner"); got != userText {
		t.Fatalf("modified user override: %q", got)
	}
}

func TestEnglishOrchestrationBodies(t *testing.T) {
	for name, text := range BuiltinPromptSeeds() {
		t.Run(name, func(t *testing.T) { assertEnglishBuiltin(t, text) })
	}
	for name, text := range map[string]string{"goals_scope": goalsScopeTail, "worker_wrapup": settleWrapUpPrompt, "traffic": workerTrafficBlock(true), "artifacts": artifactSpec("/owned"), "worker_artifacts": workerArtifactSpec("/owned/i1")} {
		t.Run(name, func(t *testing.T) { assertEnglishBuiltin(t, text) })
	}
	if workerTrafficBlock(false) != "" {
		t.Fatal("traffic guidance must remain disabled when capture is off")
	}
	for _, text := range []string{artifactSpec("/owned"), workerArtifactSpec("/owned/i1")} {
		if !strings.Contains(text, "/owned") || !strings.Contains(text, "/tmp") {
			t.Fatal("artifact directory boundary lost")
		}
	}
}

func TestEnglishReporterToolMetadata(t *testing.T) {
	for _, tool := range []interface {
		Description() string
		InputSchema() map[string]any
	}{ReporterNodeTool(nil), ReporterUpdateTool(nil), ReporterTrafficTool(nil)} {
		assertEnglishBuiltin(t, tool.Description())
	}
}

func TestEnglishRuntimeGuidancePreservesUnicode(t *testing.T) {
	const original = "用户 evidence"
	intent := &db.Node{ID: 11, Payload: json.RawMessage(`{"summary":"用户 evidence"}`)}
	rendered := renderIntentTask(intent)
	if !strings.Contains(rendered, original) || !strings.Contains(rendered, "11") {
		t.Fatal("intent evidence/id modified")
	}
	assertEnglishBuiltin(t, strings.ReplaceAll(rendered, original, "evidence"))
	assertEnglishBuiltin(t, renderWorkerGraphOverview(map[string]any{"fact": "evidence"}))
	old := FindingTrafficBindingEnabled
	defer func() { FindingTrafficBindingEnabled = old }()
	FindingTrafficBindingEnabled = func() bool { return true }
	for _, tools := range [][]actool.CoreTool{{ReporterUpdateTool(nil), ReporterTrafficTool(nil)}, {NewToolSet(nil, "").addHint()}} {
		_, guidance := findingWorkflowTools("reporter", tools)
		assertEnglishBuiltin(t, guidance)
	}
}
