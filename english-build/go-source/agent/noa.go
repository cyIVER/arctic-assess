package agent

import (
	"log"
	"path/filepath"

	"github.com/Autumn-27/norma/agentcore"
	"github.com/Autumn-27/norma/noaadapter"
)

// noaWarn returns a diagnostics sink tagging non-fatal noa messages with the
// session, routed through the package logger (agents have no per-instance one).
func noaWarn(session string) func(string) {
	return func(msg string) { log.Printf("[noa] %s: %s", session, msg) }
}

// noa is norma v0.4.0's model-driven context compression, exposed as an experimental toggle
// in system settings. It is mutually exclusive with built-in compaction. noaadapter.Enable is
// the sole entrypoint, installing the Compactor, Compress tool and three persistent prompts.
// Without Enable, built-in compaction remains active. Each agent's injected noaEnabledFn is read
// once per run, so toggling affects later runs without rebuilding the agent.

// enableNoa wires noa into opts when enabled by the resolver. archiveRoot is the persistent base
// directory for original compressed content (global workDir; all agents use <workDir>/noa rather than
// separate task/intent directories). Globally unique sessionID names the archive subdirectory.
//
// Experimental noa failures must not interrupt real tasks: report via onWarn and fall back to built-in compression.
// On success clear opts.Compaction to avoid agentcore's two-context-managers warning.
func enableNoa(opts *agentcore.Options, enabled func() bool, archiveRoot, sessionID string, onWarn func(string)) {
	if enabled == nil || !enabled() {
		return
	}
	if opts.OnWarn == nil {
		opts.OnWarn = onWarn
	}
	if err := noaadapter.Enable(opts, noaadapter.Options{
		ArchiveBaseDir: filepath.Join(archiveRoot, "noa"),
		SessionID:      sessionID,
		OnWarn:         onWarn,
	}); err != nil {
		if onWarn != nil {
			onWarn("Failed to enable noa compression; falling back to built-in compression: " + err.Error())
		}
		return
	}
	// Compactor overrides Compaction, but coexistence warns every run; explicitly clear it.
	opts.Compaction = nil
}
