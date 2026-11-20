package agent

import (
	"io"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/llm"
)

// NativeWorkerExecutor accepts only the opaque provider produced by private
// runtime admission. No model, API, DB profile or environment chooses a path.
func NativeWorkerExecutor(provider llm.Provider) (nativeexec.Executor, error) {
	p, ok := provider.(*nativeRPC)
	if !ok || !p.appAdmission || p.policy.runtimeDir == "" || p.policy.phase == nil {
		return nil, nativeErr
	}
	hasWorker := false
	for _, role := range p.policy.phase.Roles {
		if role.Role == "worker" {
			hasWorker = true
		}
	}
	if !hasWorker {
		return nil, nativeErr
	}
	return loadNativeExecutor(p.policy.runtimeDir, p.policy.phase, syscall.Openat)
}

func loadNativeExecutor(dir string, phase *nativePhasePermit, openAt func(int, string, int, uint32) (int, error)) (nativeexec.Executor, error) {
	if phase == nil || phase.state == nil || !time.Now().Before(phase.ExpiresAt) {
		return nil, nativeErr
	}
	phase.state.mu.Lock()
	stopped := phase.state.stopped
	phase.state.mu.Unlock()
	if stopped {
		return nil, nativeErr
	}
	fd, e := syscall.Open(dir, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, nativeErr
	}
	defer syscall.Close(fd)
	var st syscall.Stat_t
	if syscall.Fstat(fd, &st) != nil || (st.Uid != 0 && st.Uid != uint32(os.Geteuid())) || st.Mode&0777 != 0700 {
		return nil, nativeErr
	}
	read := func(name string, max int64) ([]byte, error) {
		n, e := openAt(fd, name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
		if e != nil {
			return nil, nativeErr
		}
		f := os.NewFile(uintptr(n), name)
		defer f.Close()
		i, e := f.Stat()
		if e != nil || !i.Mode().IsRegular() {
			return nil, nativeErr
		}
		st, ok := i.Sys().(*syscall.Stat_t)
		if !ok || !privateNativeOwner(st.Uid, i.Mode()) || st.Nlink != 1 {
			return nil, nativeErr
		}
		b, e := io.ReadAll(io.LimitReader(f, max+1))
		if e != nil || int64(len(b)) > max {
			return nil, nativeErr
		}
		return b, nil
	}
	raw, e := read("executor.json", 4096)
	if e != nil {
		return nil, nativeErr
	}
	var c struct {
		SchemaVersion   int    `json:"schema_version"`
		Reviewed        bool   `json:"reviewed"`
		PhaseID         string `json:"phase_id"`
		Generation      int64  `json:"authority_generation"`
		TaskID          int64  `json:"task_id"`
		ExplorationID   int64  `json:"exploration_id"`
		ExecutorID      string `json:"executor_id"`
		NetworkPolicyID string `json:"network_policy_id"`
		FixtureOrigin   string `json:"fixture_origin"`
		ControlSocket   string `json:"control_socket"`
	}
	if strictNativeJSON(raw, &c) != nil || c.SchemaVersion != 1 || !c.Reviewed || c.PhaseID != phase.PhaseID || c.Generation != phase.Generation || c.TaskID != phase.TaskID || c.ExplorationID != phase.ExplorationID || c.ExecutorID != phase.ExecutorID || c.NetworkPolicyID != phase.NetworkPolicyID || c.FixtureOrigin != phase.FixtureOrigin || !filepath.IsAbs(c.ControlSocket) || filepath.Clean(c.ControlSocket) != c.ControlSocket || len(c.ControlSocket) > 107 {
		return nil, nativeErr
	}
	// All nonsecret identity/configuration checks precede even opening the key.
	key, e := read("executor.key", 32)
	if e != nil || len(key) != 32 {
		return nil, nativeErr
	}
	return nativeexec.NewClient(c.ControlSocket, key)
}
