package selfupdate

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"strings"
	"time"
)

// smokeEnv makes subprocesses started by smoke tests skip Bootstrap directly.
//
// Strictly, omission would be harmless: os.Executable() is artex.new in the child, so all derived
// paths carry the .new prefix and cannot touch actual update files. Relying on this coincidence is fragile;
// an explicit short circuit is clear and avoids a needless filesystem probe in the child.
const smokeEnv = "ARTEX_SELFUPDATE_SMOKE"

// Action is Bootstrap's instruction to main.
type Action int

const (
	// Continue: start the server normally.
	Continue Action = iota
	// Restart: exit immediately with ExitRestart so the supervisor script relaunches the process.
	Restart
)

// State describes update status at this startup so /api/update/check can accurately tell the frontend
// whether the last update succeeded or was rolled back.
type State struct {
	Pending     bool   // Not yet confirmed stable after replacement
	RolledBack  bool   // Automatic rollback performed during this startup
	FailedStage bool   // Staged binary failed verification/smoke test and was discarded
	Detail      string // One-line user-facing explanation
}

// Bootstrap runs at the very start of main, before listening on any port or opening a database.
//
// Three cases:
//
//  1. Staged artex.new exists -> verify and smoke-test; swap and request restart on success, otherwise discard and keep the old version.
//  2. Only the marker remains -> swap just completed; count an attempt and roll back after enough consecutive failures.
//  3. Neither exists -> normal startup.
func Bootstrap() (Action, State) {
	if os.Getenv(smokeEnv) != "" {
		return Continue, State{}
	}
	p, err := ResolvePaths()
	if err != nil {
		log.Printf("[update] Bootstrap skipped: %v", err)
		return Continue, State{}
	}

	if _, err := os.Stat(p.New); err == nil {
		return applyStaged(p)
	}

	m, ok := readMarker(p.Marker)
	if !ok {
		return Continue, State{}
	}
	return confirmOrRollback(p, m)
}

// applyStaged handles a staged binary: swap after successful verification, otherwise discard it.
//
// This is the only update path that overwrites the executable and the final gate: smoke tests catch
// corrupt downloads, wrong architectures, and missing dynamic libraries. If an unrunnable binary passes,
// the supervisor endlessly relaunches it while Go code never runs, so automatic rollback cannot execute.
func applyStaged(p Paths) (Action, State) {
	m, _ := readMarker(p.Marker)

	if err := verifyStaged(p); err != nil {
		log.Printf("[update] Staged version failed verification and was discarded; continuing with current version: %v", err)
		cleanStaged(p)
		_ = os.Remove(p.Marker)
		return Continue, State{FailedStage: true, Detail: "New version failed verification and was discarded: " + err.Error()}
	}

	if err := swap(p); err != nil {
		log.Printf("[update] Replacement failed; continuing with current version: %v", err)
		cleanStaged(p)
		_ = os.Remove(p.Marker)
		return Continue, State{FailedStage: true, Detail: "Replacement failed: " + err.Error()}
	}

	// Swap succeeded. Keep the marker for the next startup, running the new version, to confirm stability.
	m.Attempts = 0
	if m.StagedAt == 0 {
		m.StagedAt = time.Now().Unix()
	}
	if err := writeMarker(p.Marker, m); err != nil {
		log.Printf("[update] Failed to write upgrade marker (automatic rollback unavailable): %v", err)
	}
	log.Printf("[update] Replaced with %s; exiting to restart (exit %d)", orUnknown(m.To), ExitRestart)
	return Restart, State{Pending: true}
}

// confirmOrRollback handles startup after a swap: count attempts and restore the old version above the limit.
//
// The counter increments only after Go code starts, covering executable binaries that crash during initialization
// (incompatible configuration, occupied ports, failed DB migrations). Pre-swap smoke tests catch binaries that
// cannot execute at all; both checks are needed for complete coverage.
func confirmOrRollback(p Paths, m marker) (Action, State) {
	m.Attempts++
	if m.Attempts > maxAttempts {
		if err := rollback(p); err != nil {
			// If even rollback fails, stop requesting restarts to avoid an infinite loop. Clear the marker
			// and start in the current state; if startup fails, users can at least see the reason in logs.
			log.Printf("[update] New version failed to start %d times consecutively, and rollback failed: %v", maxAttempts, err)
			_ = os.Remove(p.Marker)
			return Continue, State{Detail: "New version failed to start and rollback failed: " + err.Error()}
		}
		log.Printf("[update] New version failed to start %d times consecutively; rolled back to %s and exiting to restart (exit %d)",
			maxAttempts, orUnknown(m.From), ExitRestart)
		_ = os.Remove(p.Marker)
		return Restart, State{RolledBack: true, Detail: fmt.Sprintf("New version failed to start; rolled back to %s", orUnknown(m.From))}
	}
	if err := writeMarker(p.Marker, m); err != nil {
		log.Printf("[update] Failed to update upgrade marker: %v", err)
	}
	log.Printf("[update] Starting new version (attempt %d/%d); the upgrade will be confirmed after stable operation",
		m.Attempts, maxAttempts)
	return Continue, State{Pending: true}
}

// Settle confirms the new version is stable and removes the update marker.
//
// main calls it after a delay once HTTP is listening. The process must survive that interval; otherwise retain the marker,
// count attempts at subsequent startups, and eventually roll back.
func Settle() {
	p, err := ResolvePaths()
	if err != nil {
		return
	}
	settle(p)
}

func settle(p Paths) {
	if _, ok := readMarker(p.Marker); !ok {
		return // Not an upgrade startup; nothing to do
	}
	if err := os.Remove(p.Marker); err != nil && !errors.Is(err, os.ErrNotExist) {
		log.Printf("[update] Failed to clear upgrade marker: %v", err)
		return
	}
	log.Printf("[update] New version is stable; upgrade complete (previous version retained as %s)", p.Old)
}

// SettleDelay is the runtime required to consider the new version alive.
const SettleDelay = 30 * time.Second

// verifyStaged checks the staged binary: compare SHA256, then actually launch it once.
func verifyStaged(p Paths) error {
	want, err := os.ReadFile(p.Sum)
	if err != nil {
		return fmt.Errorf("Read checksum: %w", err)
	}
	got, err := fileSHA256(p.New)
	if err != nil {
		return fmt.Errorf("Compute checksum: %w", err)
	}
	if !strings.EqualFold(strings.TrimSpace(string(want)), got) {
		return errors.New("SHA256 mismatch (download corrupted or tampered with)")
	}
	return smokeTest(p.New)
}

// smokeTest launches the new binary with -h to confirm it can execute on this system.
// This catches truncated downloads, wrong architectures (exec format error), missing dependencies, and similar failures.
func smokeTest(bin string) error {
	if err := os.Chmod(bin, 0o755); err != nil {
		return fmt.Errorf("Set executable permissions: %w", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, bin, "-h")
	cmd.Env = append(os.Environ(), smokeEnv+"=1")
	out, err := cmd.CombinedOutput()
	if ctx.Err() != nil {
		return errors.New("Smoke test timed out (new binary unresponsive)")
	}
	if err != nil {
		snippet := strings.TrimSpace(string(out))
		if len(snippet) > 300 {
			snippet = snippet[:300] + "…"
		}
		return fmt.Errorf("Smoke test failed: %v: %s", err, snippet)
	}
	return nil
}

// swap replaces the current binary with the staged new version.
//
// Unix and Windows both permit renaming a running executable (Windows prohibits deletion and
// overwriting, not renaming), so no platform branch or prior self-shutdown is required.
func swap(p Paths) error {
	// Windows rename cannot replace an existing destination; remove the previous update's .old first.
	if err := os.Remove(p.Old); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("Clean up old backup %s: %w", p.Old, err)
	}
	if err := os.Rename(p.Current, p.Old); err != nil {
		return fmt.Errorf("Back up current version: %w", err)
	}
	if err := os.Rename(p.New, p.Current); err != nil {
		// If swapping fails after moving the current version aside, restore it unchanged or the next startup has no executable.
		if rerr := os.Rename(p.Old, p.Current); rerr != nil {
			return fmt.Errorf("Failed to install new version (%v), and failed to restore current version: %w", err, rerr)
		}
		return fmt.Errorf("Install new version: %w", err)
	}
	_ = os.Remove(p.Sum)
	return nil
}

// rollback restores the old version backed up by swap.
func rollback(p Paths) error {
	if _, err := os.Stat(p.Old); err != nil {
		return fmt.Errorf("No backup available for rollback %s: %w", p.Old, err)
	}
	// Move the unstartable new version to .failed for diagnosis rather than deleting it.
	failed := p.Current + ".failed"
	_ = os.Remove(failed)
	if err := os.Rename(p.Current, failed); err != nil {
		return fmt.Errorf("Move failed version aside: %w", err)
	}
	if err := os.Rename(p.Old, p.Current); err != nil {
		return fmt.Errorf("Restore old version: %w", err)
	}
	return nil
}

// Rollback implements /api/update/rollback: explicitly return to the preceding version.
// Only swap files; the supervisor script handles restart (the caller then exits with ExitRestart).
func Rollback() error {
	p, err := ResolvePaths()
	if err != nil {
		return err
	}
	if _, err := os.Stat(p.Old); err != nil {
		return errors.New("No previous version available for rollback (" + p.Old + " does not exist)")
	}
	cleanStaged(p)
	if err := smokeTest(p.Old); err != nil {
		return fmt.Errorf("Previous version cannot execute; refusing rollback: %w", err)
	}
	// Exchange current and backup so rollback can itself be reversed.
	tmp := p.Current + ".swap"
	_ = os.Remove(tmp)
	if err := os.Rename(p.Current, tmp); err != nil {
		return fmt.Errorf("Move current version aside: %w", err)
	}
	if err := os.Rename(p.Old, p.Current); err != nil {
		_ = os.Rename(tmp, p.Current)
		return fmt.Errorf("Install previous version: %w", err)
	}
	if err := os.Rename(tmp, p.Old); err != nil {
		log.Printf("[update] Failed to organize backup after rollback (operation unaffected): %v", err)
	}
	_ = os.Remove(p.Marker)
	return nil
}

// HasBackup reports whether a previous version is available, allowing the frontend to show the rollback button.
func HasBackup() bool {
	p, err := ResolvePaths()
	if err != nil {
		return false
	}
	_, err = os.Stat(p.Old)
	return err == nil
}

func fileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func orUnknown(s string) string {
	if strings.TrimSpace(s) == "" {
		return "Unknown version"
	}
	return s
}
