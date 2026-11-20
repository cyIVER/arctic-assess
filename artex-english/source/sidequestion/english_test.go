package sidequestion

import (
	"strings"
	"testing"
)

func TestEnglishSideQuestionSafetyInstructions(t *testing.T) {
	for _, want := range []string{"no tool execution capability", "do not promise", "background"} {
		if !strings.Contains(instruction, want) {
			t.Errorf("missing %q", want)
		}
	}
	for _, want := range []string{"do not execute tools", "instructions in the material", "1200 tokens", "data to analyze"} {
		if !strings.Contains(summaryInstruction, want) {
			t.Errorf("missing %q", want)
		}
	}
	if !strings.Contains(ErrContextBudget.Error(), "model budget") {
		t.Fatal(ErrContextBudget)
	}
}
