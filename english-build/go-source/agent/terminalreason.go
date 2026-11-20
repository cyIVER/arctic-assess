package agent

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/Autumn-27/norma/harness"
)

// runTrace retains the latest tool call so an interrupted run can identify the
// operation that was still in flight.
type runTrace struct {
	startedAt time.Time
	id        string
	name      string
	input     string
	at        time.Time
	pending   bool
}

func (t *runTrace) start(id, name, input string) {
	t.id, t.name, t.input, t.at, t.pending = id, name, input, time.Now(), true
}

func (t *runTrace) done(id string) {
	if id == t.id {
		t.pending = false
	}
}

var reasonHint = map[harness.TerminalReason]string{
	harness.ReasonCompleted:         "The model completed this round normally without a text summary; use this round's tool-call records for facts and assets",
	harness.ReasonMaxTurns:          "MaxTurns reached: the SDK wrapped up and wrote facts/assets; the intent becomes exhausted so the planner can continue in another direction, not failed",
	harness.ReasonTimeout:           "Per-run wall-clock budget MaxDuration reached: running tools are interrupted and wrap-up begins in place to write identified facts/assets; the intent becomes exhausted",
	harness.ReasonModelError:        "Model/API call failed (network, authentication, rate limiting, provider 5xx, etc.); after retries the intent becomes blocked because transport failure prevented meaningful exploration. Inspect get_worker_trace before redispatching or changing approach",
	harness.ReasonBlockingLimit:     "Context hard limit reached; request blocked before sending. Narrow the intent or compress tool output",
	harness.ReasonPromptTooLong:     "Prompt too long and compression retries exhausted; cannot continue",
	harness.ReasonImageError:        "Current model does not support this round's multimodal content; use a vision-capable model or avoid tool images",
	harness.ReasonStopHookPrevented: "Stop hook prevented ending this round, then continuation failed; check whether task Guard rules are too strict",
	harness.ReasonHookStopped:       "A tool/hook stopped execution, e.g. out-of-scope target or disabled command; inspect the final tool_result denial explanation",
	harness.ReasonAbortedStreaming:  "Run canceled during model output streaming",
	harness.ReasonAbortedTools:      "Run canceled during tool execution",
}

// terminalText renders a terminal event with no final text into a compact summary
// and a Markdown detail block.
func terminalText(ctx context.Context, term *harness.Terminal, tr *runTrace) (string, string) {
	reason := term.Reason
	aborted := reason == harness.ReasonAbortedStreaming || reason == harness.ReasonAbortedTools
	// Prompt may return ctx.Err directly without a terminal event. Preserve the
	// cancellation cause instead of falling back to an empty/unknown terminal reason.
	if reason == "" && ctx.Err() != nil {
		aborted = true
	}

	var sum string
	if aborted {
		_, short, _, ok := AbortReason(ctx)
		if !ok {
			short = "Cancellation reason unavailable"
		}
		stage := "execution"
		switch reason {
		case harness.ReasonAbortedStreaming:
			stage = "model output"
		case harness.ReasonAbortedTools:
			stage = "tool execution"
		}
		sum = "(Run interrupted: " + short + "; stopped during " + stage + progressSuffix(term, tr) + "; incomplete)"
	} else if reason == harness.ReasonMaxTurns || reason == harness.ReasonTimeout {
		sum = "(Run budget reached (" + string(reason) + "); facts written during wrap-up" + progressSuffix(term, tr) + "; no text summary)"
	} else {
		hint := terminalReasonHint(reason)
		sum = "(No text summary; terminal state " + terminalReasonLabel(reason) + ": " + firstLine(hint, 80) + ")"
	}

	var b strings.Builder
	b.WriteString(sum)
	b.WriteString("\n\n")
	displayReason := terminalReasonLabel(reason)
	fmt.Fprintf(&b, "- **Terminal state**: `%s` - %s\n", displayReason, terminalReasonHint(reason))
	if aborted {
		code, _, why, ok := AbortReason(ctx)
		if ok {
			fmt.Fprintf(&b, "- **Interruption reason** (`%s`): %s\n", code, why)
		} else {
			b.WriteString("- **Interruption reason**: unavailable; canceling caller may not have attached a named cause with context.WithCancelCause\n")
		}
	}
	if term.Err != nil {
		fmt.Fprintf(&b, "- **Underlying error**: `%v`\n", term.Err)
	}
	if aborted && strings.TrimSpace(term.Text) != "" {
		b.WriteString("- **Partial output generated before cancellation**:\n\n")
		b.WriteString(term.Text)
		b.WriteString("\n\n")
	}
	if term.Turns > 0 {
		fmt.Fprintf(&b, "- **Executed**: %d model turns\n", term.Turns)
	}
	if !tr.startedAt.IsZero() {
		fmt.Fprintf(&b, "- **Run elapsed**: %s\n", roundDur(time.Since(tr.startedAt)))
	}
	if u := term.Usage; u.InputTokens+u.OutputTokens+u.CacheReadTokens+u.CacheWriteTokens > 0 {
		fmt.Fprintf(&b, "- **Total tokens**: input %d / output %d / cache read %d / cache write %d\n",
			u.InputTokens, u.OutputTokens, u.CacheReadTokens, u.CacheWriteTokens)
	}
	if tr.name == "" {
		b.WriteString("- **Tool calls**: run ended before any tool call was issued\n")
	} else if tr.pending {
		fmt.Fprintf(&b, "- **Tool executing at interruption**: `%s` (ran for %s, **NO RESULT RETURNED**)\n\n  ```json\n  %s\n  ```\n",
			tr.name, roundDur(time.Since(tr.at)), firstLine(tr.input, 300))
	} else {
		fmt.Fprintf(&b, "- **Last tool before interruption**: `%s` (returned normally)\n", tr.name)
	}
	return sum, b.String()
}

func terminalReasonLabel(reason harness.TerminalReason) string {
	if reason == "" {
		return "context_canceled"
	}
	return string(reason)
}

func terminalReasonHint(reason harness.TerminalReason) string {
	if hint := reasonHint[reason]; hint != "" {
		return hint
	}
	if reason == "" {
		return "Run context canceled, but no underlying Terminal event was emitted"
	}
	return "Unknown terminal state; harness may have added a TerminalReason. Update reasonHint"
}

func progressSuffix(term *harness.Terminal, tr *runTrace) string {
	var parts []string
	if term.Turns > 0 {
		parts = append(parts, fmt.Sprintf("%d turns", term.Turns))
	}
	if !tr.startedAt.IsZero() {
		parts = append(parts, roundDur(time.Since(tr.startedAt)))
	}
	if len(parts) == 0 {
		return ""
	}
	return "; elapsed " + strings.Join(parts, " / ")
}

func roundDur(d time.Duration) string {
	switch {
	case d < time.Minute:
		return d.Round(100 * time.Millisecond).String()
	case d < time.Hour:
		return d.Round(time.Second).String()
	default:
		return d.Round(time.Minute).String()
	}
}
