package agent

import (
	"context"
	"encoding/json"
	"github.com/Autumn-27/norma/llm"
	"io"
	"os"
	"syscall"
	"time"
)

// NativeAdmissionObservation describes configuration, never executable authority.
type NativeAdmissionObservation struct {
	SchemaVersion          int               `json:"schema_version"`
	ProviderAdmitted       bool              `json:"provider_admitted"`
	ExecutorConfigVerified bool              `json:"executor_config_verified"`
	PhaseID                string            `json:"phase_id"`
	Generation             int64             `json:"authority_generation"`
	TaskID                 int64             `json:"task_id"`
	ExplorationID          int64             `json:"exploration_id"`
	Catalogs               map[string]string `json:"role_catalog_sha256"`
	ExecutorID             string            `json:"executor_id"`
	NetworkPolicyID        string            `json:"network_policy_id"`
	FixtureOrigin          string            `json:"fixture_origin"`
	ExpiresAt              time.Time         `json:"expires_at"`
	Model                  string            `json:"model"`
	Endpoint               string            `json:"endpoint"`
}

// ObserveNativeAdmission checks the actual opaque startup provider and current
// private phase, without opening either key. Caller must qualify auth/T/E first.
func ObserveNativeAdmission(ctx context.Context, provider llm.Provider, cfg Config, taskID, explorationID int64) (*NativeAdmissionObservation, error) {
	p, ok := provider.(*nativeRPC)
	if !ok || p.policy.runtimeDir != nativeRuntimeDir {
		return nil, nativeErr
	}
	return observeNativeAdmission(ctx, provider, cfg, taskID, explorationID)
}

func observeNativeAdmission(ctx context.Context, provider llm.Provider, cfg Config, taskID, explorationID int64) (*NativeAdmissionObservation, error) {
	p, ok := provider.(*nativeRPC)
	if !ok || !p.appAdmission || !cfg.NativeCatalogSourceValid() || p.policy.runtimeDir == "" || p.policy.phase == nil || ctx.Err() != nil {
		return nil, nativeErr
	}
	phase := p.policy.phase
	if phase.TaskID != taskID || phase.ExplorationID != explorationID || phase.state == nil || !time.Now().Before(phase.ExpiresAt) || cfg.BaseURL != p.policy.Endpoint {
		return nil, nativeErr
	}
	phase.state.mu.Lock()
	stopped := phase.state.stopped
	phase.state.mu.Unlock()
	if stopped {
		return nil, nativeErr
	}
	fd, e := syscall.Open(p.policy.runtimeDir, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, nativeErr
	}
	defer syscall.Close(fd)
	var st syscall.Stat_t
	if syscall.Fstat(fd, &st) != nil || (st.Uid != 0 && st.Uid != uint32(os.Geteuid())) || st.Mode&0777 != 0700 {
		return nil, nativeErr
	}
	read := func(name string, limit int64) ([]byte, error) {
		n, e := syscall.Openat(fd, name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
		if e != nil {
			return nil, nativeErr
		}
		f := os.NewFile(uintptr(n), name)
		defer f.Close()
		info, e := f.Stat()
		if e != nil || !info.Mode().IsRegular() {
			return nil, nativeErr
		}
		fst, ok := info.Sys().(*syscall.Stat_t)
		if !ok || !privateNativeOwner(fst.Uid, info.Mode()) || fst.Nlink != 1 {
			return nil, nativeErr
		}
		raw, e := io.ReadAll(io.LimitReader(f, limit+1))
		if e != nil || int64(len(raw)) > limit {
			return nil, nativeErr
		}
		return raw, nil
	}
	policyRaw, e := read("policy.json", 4096)
	if e != nil {
		return nil, nativeErr
	}
	var policy nativePolicyDocument
	if strictNativeJSON(policyRaw, &policy) != nil || policy.Model != cfg.Model || policy.Endpoint != p.policy.Endpoint || policy.Protocol != "artex-native-v1" || policy.BudgetMode != p.policy.BudgetMode || time.Duration(policy.TimeoutSeconds)*time.Second != p.policy.Timeout || policy.MaxCalls != p.policy.MaxCalls || policy.MaxBytes != nativeCap || !policy.RolePhaseEnabled || policy.GenerationTokensEnforced == nil || *policy.GenerationTokensEnforced || policy.NativeTools == nil || *policy.NativeTools || policy.Streaming == nil || *policy.Streaming {
		return nil, nativeErr
	}
	raw, e := read("phase.json", 16384)
	if e != nil {
		return nil, nativeErr
	}
	// Do not parseNativePhase: observation must not mint a new phase state.
	var live nativePhasePermit
	if strictNativeJSON(raw, &live) != nil {
		return nil, nativeErr
	}
	a, _ := json.Marshal(phase)
	b, _ := json.Marshal(&live)
	if string(a) != string(b) {
		return nil, nativeErr
	}
	catalogs := map[string]string{}
	for _, r := range phase.Roles {
		catalogs[r.Role] = r.CatalogSHA256
	}
	if len(catalogs) != 5 {
		return nil, nativeErr
	}
	return &NativeAdmissionObservation{SchemaVersion: 1, ProviderAdmitted: true, PhaseID: phase.PhaseID, Generation: phase.Generation, TaskID: taskID, ExplorationID: explorationID, Catalogs: catalogs, ExecutorID: phase.ExecutorID, NetworkPolicyID: phase.NetworkPolicyID, FixtureOrigin: phase.FixtureOrigin, ExpiresAt: phase.ExpiresAt, Model: cfg.Model, Endpoint: p.policy.Endpoint}, nil
}

// VerifyNativeExecutorConfiguration only constructs the existing client; it
// does not dial, execute, reserve a call, or grant worker-intent membership.
func VerifyNativeExecutorConfiguration(provider llm.Provider) error {
	_, e := NativeWorkerExecutor(provider)
	return e
}
