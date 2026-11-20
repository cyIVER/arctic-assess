package agent

import (
	"context"
	"errors"
	"fmt"
)

// AbortCause names why an agent run's context was cancelled. Every cancellation
// site should attach one so the activity trace can report the real initiator.
type AbortCause struct {
	Code  string
	Short string
	Text  string
}

func (c *AbortCause) Error() string { return c.Text }

func cause(code, short, text string) *AbortCause {
	return &AbortCause{Code: code, Short: short, Text: text}
}

// Causef builds a cause that includes runtime-specific detail.
func Causef(code, short, format string, args ...any) *AbortCause {
	return &AbortCause{Code: code, Short: short, Text: fmt.Sprintf(format, args...)}
}

var (
	// Task-level execution context.
	AbortPausedByUser = cause("paused_by_user", "User paused the task",
		"The user paused the task via POST /api/tasks/{id}/control, action=pause. This Planner/Worker run was actively canceled; running intents return to frontier(open), to be reclaimed and restarted from the beginning after task resume")
	AbortPausedByOrchestrator = cause("paused_by_orchestrator", "Orchestrator paused the task",
		"The orchestrator Agent called pause_task to pause this task. This Planner/Worker run was actively canceled; running intents return to frontier(open) and restart after resume")
	AbortTaskDeleted = cause("task_deleted", "Task deleted",
		"The task is being deleted (DELETE /api/tasks/{id}); the deletion barrier canceled its running Planner, Workers and main Agent. This run's results will no longer be used")
	AbortPausedOnReload = cause("paused_on_reload", "Backend restored task pause",
		"At startup the backend restored the persisted paused task state. This run was canceled; normally no Agent is running during recovery")
	AbortGoalMet = cause("goal_met", "Planner confirmed task goals met",
		"The planner determined task goals were met and set the task to done, then canceled remaining Workers. These intents are marked stopped, not failed")
	AbortSettleDrainTimeout = cause("settle_drain_timeout", "Task wrap-up wait exhausted",
		"After task timeout, running Workers were allowed to wrap up gracefully, but the 90-second drain grace expired, triggering hard cancellation. Intents are marked exhausted; facts and assets already written during wrap-up are retained")

	// Per-work context.
	AbortKilledByPlanner = cause("killed_by_planner", "Planner terminated this intent",
		"The planner called kill_work to terminate this intent, usually because it was off-track or no longer useful. The intent is marked stopped and will not be automatically reclaimed")
	AbortWorkPausedByUser = cause("work_paused_by_user", "User paused this Worker intent",
		"The user paused a running Worker. This call was canceled and the intent becomes paused; registered intents, facts, findings and activities are retained. It restarts from the beginning after resume")
	AbortWorkCancelledByUser = cause("work_cancelled_by_user", "User deleted this Worker intent",
		"The user deleted a running Worker. This call was canceled; after the Worker leaves the write region, the server applies the selected deletion mode: soft deletion marks it deleted and retains all output, while hard deletion cascades to the intent and downstream nodes supported only by it")
	AbortWorkFinished = cause("work_finished", "Worker finished; context released",
		"The Worker finished normally; the engine releases context resources in detachWork. This is not an interruption; if shown as one, cancellation raced with finalization events")
	AbortPausedRaceGuard = cause("paused_race_guard", "Task paused; new run rejected",
		"The engine refuses new execution contexts while the task is paused, preventing a claim/pause race from starting a Worker. Claimed intents return to the frontier")

	// Main Agent and standalone conversation contexts.
	AbortChatStoppedByUser = cause("chat_stopped_by_user", "User stopped this conversation turn",
		"The user clicked Stop to abort this main Agent or conversation Agent run. Existing activities are retained; another message can be sent")
	AbortChatPausedWithTask = cause("chat_paused_with_task", "Task pause stopped main Agent chat",
		"When the user paused the task, its running main Agent conversation was canceled too. Existing activities are retained; this message will not automatically replay after task resume")
	AbortChatTurnFinished = cause("chat_turn_finished", "Turn finished; context released",
		"This conversation turn finished normally; the server is releasing its context resources. This is not an interruption; if shown as one, cancellation raced with finalization events")

	// Process-level and per-run hard backstop.
	AbortShutdown = cause("shutdown", "Backend process is shutting down",
		"The backend received SIGINT or SIGTERM and is restarting, updating or shutting down. All running Agents are canceled; after restart, leftover running intents reset to open and execute again")
	AbortRunHardTimeout = cause("run_hard_timeout", "Per-run hard timeout triggered",
		"The run exceeded its soft wall-clock budget and extra grace, indicating a model request or tool did not return for too long and normal turn-boundary wrap-up could not execute. Inspect the last tool call that had not returned before interruption")
)

// AbortReason resolves the named cause attached to a cancelled run context.
func AbortReason(ctx context.Context) (code, short, text string, ok bool) {
	c := context.Cause(ctx)
	if c == nil {
		return "", "", "", false
	}
	var ac *AbortCause
	if errors.As(c, &ac) {
		return ac.Code, ac.Short, ac.Text, true
	}
	switch {
	case errors.Is(c, context.DeadlineExceeded):
		return "deadline_exceeded", "Upstream context reached its deadline",
			"Upstream context reached its deadline, but its creator did not attach a named cause via WithTimeoutCause: " + c.Error(), true
	case errors.Is(c, context.Canceled):
		return "canceled_no_cause", "Canceling caller supplied no named cause",
			"Upstream context was canceled without a named cause via context.WithCancelCause; register a cause in agent/cancelcause.go and wire it into the cancellation site", true
	default:
		return "other", firstLine(c.Error(), 80), c.Error(), true
	}
}
