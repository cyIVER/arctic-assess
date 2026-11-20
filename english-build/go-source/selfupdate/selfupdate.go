// Package selfupdate implements ARTEX's one-click web update: fetch a new binary from GitHub Release,
// verify and stage it, then atomically swap it at the next startup.
//
// Responsibilities (see start.sh / start.bat):
//
//	Startup script = simple supervisor loop, deciding whether to relaunch after exit based only on the exit code.
//	This package = all error-prone logic (download / SHA256 verification / smoke test / swap / failure rollback).
//
// Swapping belongs in Go rather than scripts because checksum verification and smoke tests otherwise need separate
// sh and bat implementations (sha256sum / shasum / certutil). This is the least tolerable point for error: installing
// an unrunnable binary makes the supervisor relaunch endlessly and requires manual host recovery.
//
// A complete update spans three process startups:
//
//  1. Old server receives /api/update/apply -> download and verify -> stage artex.new -> exit 75.
//  2. Script relaunches old version -> Bootstrap finds artex.new -> verify and smoke-test -> swap -> exit 75.
//  3. Script relaunches the new version -> Bootstrap counts an attempt -> clear marker after successful startup.
//
// Any failure falls back to the old version: at step 2, failed verification deletes staging and keeps running old code; at step 3,
// three consecutive failures before marker removal (startup crashes) automatically restore artex.old.
package selfupdate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// ExitRestart requests supervisor relaunch (EX_TEMPFAIL). Startup scripts immediately restart on this code,
// without crash backoff. 0 means normal user shutdown (leave the loop); all other codes count as crashes.
const ExitRestart = 75

// maxAttempts is the allowed number of post-swap startup attempts. Each new-version startup increments the count;
// surviving settleDelay removes the marker. maxAttempts consecutive crashes trigger automatic rollback.
const maxAttempts = 3

// Paths contains all files for an update, consistently located under the **Executable directory**.
// Deliberately avoid CWD: service working directories may be / or any other path; staging there would
// break the swap logic.
type Paths struct {
	Dir     string // Executable directory
	Current string // Currently running binary        artex      / artex.exe
	New     string // Staged new version            artex.new  / artex.new.exe
	Sum     string // New version SHA256 (hex)  artex.new.sha256 / artex.new.exe.sha256
	Old     string // Previous version backed up before replacement      artex.old  / artex.old.exe
	Marker  string // Upgrade state marker            artex.upgrade.json
}

// ResolvePaths derives all update paths from the current executable.
//
// On Windows, .new/.old must retain the .exe suffix or smoke tests and post-swap execution fail;
// strip the suffix before constructing names to keep naming symmetric across platforms.
func ResolvePaths() (Paths, error) {
	exe, err := os.Executable()
	if err != nil {
		return Paths{}, fmt.Errorf("Locate executable: %w", err)
	}
	if resolved, err := filepath.EvalSymlinks(exe); err == nil {
		exe = resolved
	}
	dir := filepath.Dir(exe)
	name := filepath.Base(exe)
	ext := filepath.Ext(name) // ".exe" on Windows; usually empty on Unix
	stem := strings.TrimSuffix(name, ext)

	join := func(suffix string) string { return filepath.Join(dir, stem+suffix+ext) }
	return Paths{
		Dir:     dir,
		Current: exe,
		New:     join(".new"),
		Sum:     join(".new") + ".sha256",
		Old:     join(".old"),
		Marker:  filepath.Join(dir, stem+".upgrade.json"),
	}, nil
}

// marker records swap progress to trigger automatic rollback if the new version cannot start.
type marker struct {
	From     string `json:"from"`     // Version before upgrade
	To       string `json:"to"`       // Target version
	Attempts int    `json:"attempts"` // Startup attempts since replacement
	StagedAt int64  `json:"staged_at"`
}

func readMarker(path string) (marker, bool) {
	b, err := os.ReadFile(path)
	if err != nil {
		return marker{}, false
	}
	var m marker
	if json.Unmarshal(b, &m) != nil {
		return marker{}, false
	}
	return m, true
}

func writeMarker(path string, m marker) error {
	b, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o644)
}

// cleanStaged removes staged files after successful swap, failed verification, or user cancellation, preventing leftover
// artex.new from being retried at the next startup.
func cleanStaged(p Paths) {
	_ = os.Remove(p.New)
	_ = os.Remove(p.Sum)
}

// CompareVersions compares versions, returning -1/0/1 for a<b / a==b / a>b.
// ok=false means at least one version is not comparable, such as a local development build "dev" or
// git describe output "0.3.7-2-gabc1234-dirty". Callers should disable one-click update in that case,
// or a development build could be overwritten by a stable release, losing uncommitted changes.
func CompareVersions(a, b string) (int, bool) {
	av, aok := parseVersion(a)
	bv, bok := parseVersion(b)
	if !aok || !bok {
		return 0, false
	}
	for i := range 3 {
		if av[i] != bv[i] {
			if av[i] < bv[i] {
				return -1, true
			}
			return 1, true
		}
	}
	return 0, true
}

// parseVersion parses "v0.3.7" / "0.3.7" into [3]int.
//
// Accept only clean three-component versions: build.sh uses git describe for untagged builds,
// producing suffixed versions such as "0.3.7-2-gabc1234". These must be noncomparable, not interpreted as
// 0.3.7, or development builds could be incorrectly considered current or overwritten by stable releases.
func parseVersion(s string) ([3]int, bool) {
	s = strings.TrimSpace(s)
	s = strings.TrimPrefix(s, "v")
	if s == "" {
		return [3]int{}, false
	}
	parts := strings.Split(s, ".")
	if len(parts) != 3 {
		return [3]int{}, false
	}
	var out [3]int
	for i, p := range parts {
		n, err := strconv.Atoi(p)
		if err != nil || n < 0 {
			return [3]int{}, false
		}
		out[i] = n
	}
	return out, true
}

// InDocker reports whether the process runs in a container. A Docker swap writes the container's writable layer;
// `docker compose up -d` recreating the container restores the image version. This is expected
// (the user is pulling a new image then), but the frontend must explain it clearly.
func InDocker() bool {
	if _, err := os.Stat("/.dockerenv"); err == nil {
		return true
	}
	b, err := os.ReadFile("/proc/1/cgroup")
	if err != nil {
		return false
	}
	s := string(b)
	return strings.Contains(s, "docker") || strings.Contains(s, "containerd")
}
