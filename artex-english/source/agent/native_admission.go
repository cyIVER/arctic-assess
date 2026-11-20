package agent

// Initial private owned-sink lab only; ARTEX/Norma remain the agent and executor.
import (
	"bytes"
	"context"
	"encoding/json"
	actool "github.com/Autumn-27/norma/tool"
	"io"
	"net/url"
	"os"
	"regexp"
	"syscall"
	"time"
)

type nativePolicyDocument struct {
	Model                    string `json:"model"`
	Protocol                 string `json:"protocol"`
	Endpoint                 string `json:"endpoint"`
	BudgetMode               string `json:"budget_mode"`
	TimeoutSeconds           int    `json:"timeout_seconds"`
	MaxCalls                 int    `json:"max_calls"`
	MaxBytes                 int    `json:"max_bytes"`
	GenerationTokensEnforced *bool  `json:"generation_tokens_enforced"`
	NativeTools              *bool  `json:"native_tools"`
	Streaming                *bool  `json:"streaming"`
	RolePhaseEnabled         bool   `json:"role_phase_enabled"`
}

const nativeRuntimeDir = "/run/artex-native"
const nativeCurl = "/usr/bin/curl -q --noproxy '*' --proxy '' --fail --silent --show-error --max-time 10 --max-filesize 4096 --proto '=http' -- http://artex-owned-sink:8080/nonce"

func nativeEndpoint(endpoint string) bool {
	u, e := url.Parse(endpoint)
	return e == nil && u.Scheme == "http" && u.User == nil && u.RawQuery == "" && !u.ForceQuery && u.Fragment == "" && u.RawPath == "" && u.Path == "/artex/native/v1/complete" && ((u.Hostname() == "127.0.0.1" && regexp.MustCompile(`^[1-9][0-9]{0,4}$`).MatchString(u.Port())) || u.Host == "172.29.88.1:18761")
}
func privateNativeOwner(uid uint32, mode os.FileMode) bool {
	return (uid == 0 || uid == uint32(os.Geteuid())) && mode.Perm() == 0600
}

// The fixed /run parent is trusted root-owned runtime storage. No API/env path selection.
func loadNativePolicy(dir string) (*NativeRPCPolicy, error) {
	return loadNativePolicyForConfig(dir, Config{Model: "gpt-6.1-sol"}, syscall.Openat)
}

// Keep a verified directory descriptor through policy admission and key open.
// openAt is a private test seam; production always passes syscall.Openat.
func loadNativePolicyForConfig(dir string, c Config, openAt func(int, string, int, uint32) (int, error)) (*NativeRPCPolicy, error) {
	if c.Native != nil || c.Stream || c.MaxTokens != 0 || c.MaxTokensField != "" || c.APIKey != "" || c.Proxy != "" || c.Model != "gpt-6.1-sol" || c.ThinkingType != "" || c.ReasoningEffort != "" || c.SessionHeaderKey != "" {
		return nil, nativeErr
	}
	if c.BaseURL != "" && !nativeEndpoint(c.BaseURL) {
		return nil, nativeErr
	}
	fd, e := syscall.Open(dir, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, nativeErr
	}
	defer syscall.Close(fd)
	var st syscall.Stat_t
	if syscall.Fstat(fd, &st) != nil || (st.Uid != 0 && st.Uid != uint32(os.Geteuid())) || st.Mode&0077 != 0 {
		return nil, nativeErr
	}
	read := func(name string, limit int64) ([]byte, error) {
		n, e := openAt(fd, name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
		if e != nil {
			return nil, nativeErr
		}
		f := os.NewFile(uintptr(n), name)
		defer f.Close()
		info, e := f.Stat()
		if e != nil || !info.Mode().IsRegular() {
			return nil, nativeErr
		}
		s, ok := info.Sys().(*syscall.Stat_t)
		if !ok || !privateNativeOwner(s.Uid, info.Mode()) {
			return nil, nativeErr
		}
		b, e := io.ReadAll(io.LimitReader(f, limit+1))
		if e != nil || int64(len(b)) > limit {
			return nil, nativeErr
		}
		return b, nil
	}
	b, e := read("policy.json", 4096)
	if e != nil {
		return nil, nativeErr
	}
	var p nativePolicyDocument
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.DisallowUnknownFields()
	if dec.Decode(&p) != nil || dec.Decode(new(any)) != io.EOF || p.Model != "gpt-6.1-sol" || p.Protocol != "artex-native-v1" || p.BudgetMode != "time/bytes/calls" || p.TimeoutSeconds < 1 || p.TimeoutSeconds > 90 || p.MaxCalls < 1 || p.MaxCalls > 16 || p.MaxBytes != nativeCap || p.GenerationTokensEnforced == nil || *p.GenerationTokensEnforced || p.NativeTools == nil || *p.NativeTools || p.Streaming == nil || *p.Streaming || !nativeEndpoint(p.Endpoint) {
		return nil, nativeErr
	}
	if c.BaseURL != "" && c.BaseURL != p.Endpoint {
		return nil, nativeErr
	}
	var phase *nativePhasePermit
	if p.RolePhaseEnabled {
		raw, err := read("phase.json", 16384)
		if err != nil {
			return nil, nativeErr
		}
		phase, err = parseNativePhase(raw)
		if err != nil {
			return nil, nativeErr
		}
	}
	// Dedicated broker key is read ONLY after all settings and the policy match.
	key, e := read("service.key", 64)
	if e != nil || !regexp.MustCompile(`^[a-f0-9]{64}$`).Match(key) {
		return nil, nativeErr
	}
	return &NativeRPCPolicy{runtimeDir: dir, phase: phase, Endpoint: p.Endpoint, ServiceKey: string(key), BudgetMode: p.BudgetMode, Timeout: time.Duration(p.TimeoutSeconds) * time.Second, MaxCalls: p.MaxCalls}, nil
}

func (c Config) admittedNativeProvider() (*nativeRPC, error) {
	// In-memory/JSON/DB policy is never authority. Production always uses fixed runtime storage.
	p, e := loadNativePolicyForConfig(nativeRuntimeDir, c, syscall.Openat)
	if e != nil {
		return nil, nativeErr
	}
	c.Native = p
	c.BaseURL = p.Endpoint
	pRPC, e := newNativeRPC(c)
	if e != nil {
		return nil, e
	}
	pRPC.appAdmission = true
	return pRPC, nil
}

type nativeChatContextKey struct{}

type nativeBashTool struct {
	actool.CoreTool
	dir string
}

func nativeBash(t actool.CoreTool, dir string) actool.CoreTool { return &nativeBashTool{t, dir} }
func nativeLabTools(dir string) []actool.CoreTool {
	return []actool.CoreTool{nativeBash(actool.NewBash(), dir)}
}
func (t *nativeBashTool) Description() string {
	return "Limited owned-sink lab: fetch the public nonce using the one exact permitted command."
}
func (t *nativeBashTool) Prompt() string {
	return "Only accepted arguments: command = " + nativeCurl + "; timeout_ms = 10000. No other fields."
}
func (t *nativeBashTool) InputSchema() map[string]any {
	return map[string]any{"type": "object", "properties": map[string]any{"command": map[string]any{"type": "string", "enum": []string{nativeCurl}}, "timeout_ms": map[string]any{"type": "integer", "enum": []int{10000}}}, "required": []string{"command", "timeout_ms"}, "additionalProperties": false}
}
func (t *nativeBashTool) Call(ctx context.Context, raw json.RawMessage, tc *actool.ToolContext) (actool.Result, error) {
	// Byte-exact canonical JSON prevents duplicate keys, coercions, and additional execution fields.
	canonical, _ := json.Marshal(map[string]any{"command": nativeCurl, "timeout_ms": 10000})
	var compact bytes.Buffer
	if json.Compact(&compact, raw) != nil || !bytes.Equal(compact.Bytes(), canonical) || tc == nil || tc.WorkingDir != t.dir {
		return actool.Result{}, nativeErr
	}
	info, e := os.Lstat(t.dir)
	if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0077 != 0 {
		return actool.Result{}, nativeErr
	}
	s, ok := info.Sys().(*syscall.Stat_t)
	if !ok || (s.Uid != 0 && s.Uid != uint32(os.Geteuid())) {
		return actool.Result{}, nativeErr
	}
	local := *tc
	local.Tasks = nil
	local.Env = nil
	local.OutputDir = ""
	return t.CoreTool.Call(ctx, raw, &local)
}
