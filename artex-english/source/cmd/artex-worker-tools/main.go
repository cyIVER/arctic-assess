// artex-worker-tools is a one-call credential-free helper. NEVER launch it on
// the controller for model-selected input. /work is supplied by the trusted broker.
package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"github.com/Autumn-27/artex/nativeexec"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/tool"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"os"
	"path/filepath"
	"regexp"
	"syscall"
	"time"
	"unicode/utf8"
)

type wireRequest struct {
	Version   int             `json:"version"`
	Tool      string          `json:"tool"`
	Input     json.RawMessage `json:"input"`
	ToolUseID string          `json:"tool_use_id,omitempty"`
}
type wireResult struct {
	Content []llm.ContentBlock
	IsError bool
}
type wireResponse struct {
	Version int        `json:"version"`
	Result  wireResult `json:"result"`
	Error   string     `json:"error,omitempty"`
}

func cleanEnvironment() {
	os.Clearenv()
	for k, v := range map[string]string{"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "TMPDIR": "/tmp", "LANG": "C.UTF-8", "HTTP_PROXY": "http://127.0.0.1:18080", "http_proxy": "http://127.0.0.1:18080"} {
		_ = os.Setenv(k, v)
	}
}
func helperContext(work, id string) *tool.ToolContext {
	return &tool.ToolContext{WorkingDir: work, ToolUseID: id, MaxOutputChars: 16384}
}
func serveTool(ctx context.Context, r io.Reader, w io.Writer, work string) error {
	b, e := io.ReadAll(io.LimitReader(r, 32769))
	if e != nil || len(b) > 32768 || !utf8.Valid(b) {
		return errors.New("invalid request bytes")
	}
	// Strict envelope keys including duplicates; the nested tool input is separately validated.
	d := json.NewDecoder(bytes.NewReader(b))
	tok, e := d.Token()
	if e != nil || tok != json.Delim('{') {
		return errors.New("invalid envelope")
	}
	seen := map[string]bool{}
	for d.More() {
		tok, e = d.Token()
		if e != nil {
			return errors.New("invalid envelope")
		}
		key, ok := tok.(string)
		if !ok || seen[key] || (key != "version" && key != "tool" && key != "input" && key != "tool_use_id") {
			return errors.New("invalid envelope field")
		}
		seen[key] = true
		var raw json.RawMessage
		if e = d.Decode(&raw); e != nil {
			return errors.New("invalid envelope value")
		}
	}
	if _, e = d.Token(); e != nil {
		return errors.New("invalid envelope")
	}
	if _, e = d.Token(); e != io.EOF {
		return errors.New("trailing envelope")
	}
	var req wireRequest
	if e = json.Unmarshal(b, &req); e != nil || req.Version != 1 || len(req.ToolUseID) > 128 {
		return errors.New("unsupported envelope")
	}
	t, e := nativeexec.Select(req.Tool)
	if e != nil {
		return e
	}
	if e = nativeexec.Validate(ctx, t, req.Input); e != nil {
		return e
	}
	result, e := t.Call(ctx, req.Input, helperContext(work, req.ToolUseID))
	if e != nil {
		return errors.New("SDK core execution failed")
	}
	if len(result.Extra) != 0 || len(result.Content) > 64 {
		return errors.New("unexpected SDK result")
	}
	for _, c := range result.Content {
		if c.Type != llm.BlockText || c.Thinking != "" || c.Signature != "" || c.ID != "" || c.Name != "" || len(c.Input) > 0 || c.ToolUseID != "" || len(c.Content) > 0 || c.IsError {
			return errors.New("unexpected SDK content")
		}
	}
	payload, e := json.Marshal(wireResponse{Version: 1, Result: wireResult{Content: result.Content, IsError: result.IsError}})
	if e != nil || len(payload) > 65536 {
		return errors.New("helper output limit")
	}
	_, e = w.Write(append(payload, '\n'))
	return e
}

// Convenience only. An arbitrary Bash client can speak directly to the UDS;
// only the independent host gateway owns origin/method/budget policy.
func startProxy() (func(), error) {
	l, e := net.Listen("tcp", "127.0.0.1:18080")
	if e != nil {
		return nil, e
	}
	tr := &http.Transport{Proxy: nil, DisableKeepAlives: true, ResponseHeaderTimeout: 2 * time.Second, DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
		return (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, "unix", "/fixture/gateway.sock")
	}}
	p := &httputil.ReverseProxy{Director: func(r *http.Request) {
		r.URL.Scheme = "http"
		if r.URL.Host == "" {
			r.URL.Host = r.Host
		}
	}, Transport: tr, ErrorHandler: func(w http.ResponseWriter, r *http.Request, e error) {
		http.Error(w, "fixture gateway unavailable", 502)
	}}
	s := &http.Server{Handler: p, ReadHeaderTimeout: 2 * time.Second, ReadTimeout: 3 * time.Second, WriteTimeout: 3 * time.Second, MaxHeaderBytes: 8192}
	go s.Serve(l)
	return func() { s.Close(); tr.CloseIdleConnections() }, nil
}

// H2 is a trusted transport prologue, never model input or a tool override.
// The image/entrypoint must be independently pinned by the host.
type mountIdentity struct {
	Device  uint64 `json:"device"`
	Inode   uint64 `json:"inode"`
	FSBytes uint64 `json:"fs_bytes,omitempty"`
}
type mountHello struct {
	Version int           `json:"version"`
	Nonce   string        `json:"nonce"`
	Work    mountIdentity `json:"work"`
	Fixture mountIdentity `json:"fixture"`
	Gateway mountIdentity `json:"gateway"`
}

func handshakeFrame(r *bufio.Reader, field string) (string, error) {
	b, e := r.ReadSlice('\n')
	if e != nil || len(b) > 1024 {
		return "", errors.New("handshake frame")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	tok, e := d.Token()
	if e != nil || tok != json.Delim('{') {
		return "", errors.New("handshake object")
	}
	seen := map[string]bool{}
	version := 0
	value := ""
	for d.More() {
		tok, e = d.Token()
		if e != nil {
			return "", e
		}
		k, ok := tok.(string)
		if !ok || seen[k] || (k != "version" && k != field) {
			return "", errors.New("handshake fields")
		}
		seen[k] = true
		if k == "version" {
			e = d.Decode(&version)
		} else {
			e = d.Decode(&value)
		}
		if e != nil {
			return "", errors.New("handshake value")
		}
	}
	if _, e = d.Token(); e != nil {
		return "", e
	}
	if _, e = d.Token(); e != io.EOF || len(seen) != 2 || version != 2 || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(value) {
		return "", errors.New("handshake identity")
	}
	return value, nil
}

func openMounted(path string, socket bool) (*os.File, mountIdentity, error) {
	flags := syscall.O_RDONLY | syscall.O_DIRECTORY | syscall.O_NOFOLLOW
	if socket {
		flags = 0x200000 | syscall.O_NOFOLLOW
	} // Linux O_PATH: inspect UDS without connecting.
	fd, e := syscall.Open(path, flags, 0)
	if e != nil {
		return nil, mountIdentity{}, e
	}
	f := os.NewFile(uintptr(fd), path)
	fail := func() (*os.File, mountIdentity, error) {
		f.Close()
		return nil, mountIdentity{}, errors.New("mounted object")
	}
	info, e := f.Stat()
	if e != nil {
		return fail()
	}
	if socket && info.Mode()&os.ModeSocket == 0 {
		return fail()
	}
	st, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return fail()
	}
	id := mountIdentity{Device: uint64(st.Dev), Inode: st.Ino}
	if !socket {
		var fs syscall.Statfs_t
		if syscall.Fstatfs(fd, &fs) != nil {
			return fail()
		}
		id.FSBytes = fs.Blocks * uint64(fs.Bsize)
	}
	return f, id, nil
}

func attest(ctx context.Context, r io.Reader, w io.Writer, work, fixture string) (*bufio.Reader, func(), error) {
	reader := bufio.NewReaderSize(r, 1024)
	nonce, e := handshakeFrame(reader, "nonce")
	if e != nil {
		return nil, nil, e
	}
	files := []*os.File{}
	closeFiles := func() {
		for _, f := range files {
			f.Close()
		}
	}
	hello := mountHello{Version: 2, Nonce: nonce}
	for i, path := range []string{work, fixture, filepath.Join(fixture, "gateway.sock")} {
		f, id, e := openMounted(path, i == 2)
		if e != nil {
			closeFiles()
			return nil, nil, errors.New("mounted object unavailable")
		}
		files = append(files, f)
		switch i {
		case 0:
			hello.Work = id
		case 1:
			hello.Fixture = id
		case 2:
			hello.Gateway = id
		}
	}
	if ctx.Err() != nil {
		closeFiles()
		return nil, nil, ctx.Err()
	}
	if e = json.NewEncoder(w).Encode(hello); e != nil {
		closeFiles()
		return nil, nil, e
	}
	ack, e := handshakeFrame(reader, "ack")
	if e != nil || ack != nonce || ctx.Err() != nil {
		closeFiles()
		return nil, nil, errors.New("mount ACK refused")
	}
	return reader, closeFiles, nil
}

func serve(ctx context.Context, r io.Reader, w io.Writer, work string) error {
	reader, closeFiles, e := attest(ctx, r, w, work, "/fixture")
	if e != nil {
		return e
	}
	defer closeFiles()
	closeProxy, e := startProxy()
	if e != nil {
		return e
	}
	defer closeProxy()
	return serveTool(ctx, reader, w, work)
}

func main() {
	cleanEnvironment()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	go func() { <-ctx.Done(); _ = os.Stdin.Close(); _ = os.Stdout.Close() }()
	if e := serve(ctx, os.Stdin, os.Stdout, "/work"); e != nil {
		_ = json.NewEncoder(os.Stdout).Encode(wireResponse{Version: 1, Error: "worker helper rejected or failed"})
		os.Exit(2)
	}
}
