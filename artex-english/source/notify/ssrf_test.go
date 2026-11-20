package notify

import (
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
)

// This file covers two related hardening measures:
// 1. Delivery URLs must not use the server as a relay to internal networks / cloud metadata (SSRF).
// 2. URL validation errors must not expose credentials embedded in URLs.
//
// Test environment: many tests use httptest receivers on 127.0.0.1, blocked by default.
// TestMain enables AllowLocalTargetsEnv globally, and each SSRF test below explicitly
// clears it to assert **default-deny** behavior.

func TestMain(m *testing.M) {
	// Allow regular tests to reach fake local receivers; SSRF tests temporarily clear this themselves.
	_ = os.Setenv(AllowLocalTargetsEnv, "1")
	os.Exit(m.Run())
}

// TestDialGuardRejectsLoopbackByDefault is the core SSRF assertion:
// default configuration must reject loopback delivery at the **connection layer**.
func TestDialGuardRejectsLoopbackByDefault(t *testing.T) {
	var hit bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hit = true
		_, _ = io.WriteString(w, `{"errcode":0}`)
	}))
	defer srv.Close()

	t.Setenv(AllowLocalTargetsEnv, "") // Disable the escape hatch = default behavior.
	_, err := (dingTalkChannel{}).Send(context.Background(),
		map[string]any{"webhook": srv.URL + "/robot/send"}, Message{Items: []Item{{Severity: "high"}}})
	if err == nil {
		t.Fatal("默认不应允许投递到环回地址")
	}
	if hit {
		t.Fatal("请求已经打到了本机服务——守卫没生效")
	}
	// Errors should explain how to opt in (a local SMTP relay is legitimate).
	if !strings.Contains(err.Error(), AllowLocalTargetsEnv) {
		t.Errorf("拒绝信息应说明如何显式放开: %v", err)
	}
}

// TestDialGuardAllowsLoopbackWhenOptedIn is the inverse: explicit opt-in must work,
// or legitimate local postfix / internal relay deployments would become unusable.
func TestDialGuardAllowsLoopbackWhenOptedIn(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, `{"errcode":0,"errmsg":"ok"}`)
	}))
	defer srv.Close()

	t.Setenv(AllowLocalTargetsEnv, "1")
	if _, err := (dingTalkChannel{}).Send(context.Background(),
		map[string]any{"webhook": srv.URL + "/robot/send"}, Message{Items: []Item{{Severity: "high"}}}); err != nil {
		t.Fatalf("显式放开后应可投递: %v", err)
	}
}

func TestIsBlockedDialIP(t *testing.T) {
	blocked := []string{
		"127.0.0.1", "127.1.2.3", "::1",
		"169.254.169.254", // Cloud metadata endpoint: the main reason for this function.
		"169.254.1.1", "fe80::1",
		"0.0.0.0", "::",
		"224.0.0.1", "ff02::1",
		"::ffff:127.0.0.1", // Unmap IPv4-mapped forms before checking, or they provide a bypass.
		"",
	}
	for _, s := range blocked {
		if !isBlockedDialIP(net.ParseIP(s)) {
			t.Errorf("%s 应被拒绝", s)
		}
	}
	// RFC1918 private networks are **deliberately permitted**: internal Mattermost / SMTP relays are common legitimate uses.
	// This assertion preserves that tradeoff; adding a private-network check later makes it fail,
	// requiring a conscious decision rather than silently breaking deployments.
	allowed := []string{"10.0.0.5", "172.16.3.4", "192.168.1.10", "8.8.8.8", "2606:4700::1111"}
	for _, s := range allowed {
		if isBlockedDialIP(net.ParseIP(s)) {
			t.Errorf("%s 应被放行（私网是常见的合法投递目标）", s)
		}
	}
}

// TestValidateHTTPURLRejectsLiteralPrivateTargets covers early configuration feedback:
// reject literal IPs at save time instead of waiting for the first failed delivery.
func TestValidateHTTPURLRejectsLiteralPrivateTargets(t *testing.T) {
	t.Setenv(AllowLocalTargetsEnv, "")
	for _, raw := range []string{
		"http://127.0.0.1:8080/hook",
		"http://169.254.169.254/latest/meta-data/",
		"http://[::1]:8080/hook",
	} {
		if err := validateHTTPURL(raw); err == nil {
			t.Errorf("%s 应在配置阶段被拒绝", raw)
		}
	}
	// Public and private network addresses still pass (private addresses are left to dialing, which permits them).
	for _, raw := range []string{"https://oapi.dingtalk.com/robot/send", "http://10.0.0.9/hook"} {
		if err := validateHTTPURL(raw); err != nil {
			t.Errorf("%s 应通过校验: %v", raw, err)
		}
	}
}

// TestValidateHTTPURLErrorNeverLeaksCredentials covers the branch missed in the previous audit pass.
//
// Failed url.Parse returns *url.Error containing the complete original URL. The earlier pass only
// redacted http.Client.Do errors, missing this branch. Its permanent-failure tests
// (file://, gopher://, ftp://) all parsed successfully and exercised scheme validation instead,
// so green tests provided false assurance about this branch.
func TestValidateHTTPURLErrorNeverLeaksCredentials(t *testing.T) {
	cases := []string{
		"http://127.0.0.1/%zz?access_token=" + leakProbeToken,         // Invalid percent escape.
		"https://a.example.com:port/x?access_token=" + leakProbeToken, // Nonnumeric port.
		"http://[::1?access_token=" + leakProbeToken,                  // Unbalanced bracket.
	}
	for _, raw := range cases {
		// First verify that this input **actually** makes url.Parse fail; otherwise it could unknowingly
		// exercise another branch, recreating the earlier false assurance.
		if _, err := url.Parse(raw); err == nil {
			t.Errorf("%q 本应解析失败，否则这条用例没有覆盖到目标分支", raw)
			continue
		}
		err := validateHTTPURL(raw)
		if err == nil {
			t.Errorf("%q 应校验失败", raw)
			continue
		}
		assertNoSecret(t, err.Error(), leakProbeToken)
	}
	// Ensure channel-level wrapping does not expose the URL either.
	t.Setenv(AllowLocalTargetsEnv, "")
	err := (dingTalkChannel{}).Validate(map[string]any{"webhook": cases[0]})
	if err == nil {
		t.Fatal("非法地址应校验失败")
	}
	assertNoSecret(t, err.Error(), leakProbeToken)
}

// TestEmailDialGuardRejectsLoopbackByDefault covers the SMTP dial guard.
//
// Email previously used bare net.Dialer, the sole SSRF gap: host values
// 169.254.169.254 or 127.0.0.1 could connect directly, and failed smtp.NewClient handshakes included
// the peer's response line in errors echoed through last_error and delivery history, providing the same
// semi-blind read primitive already closed in other channels. Refusal-versus-timeout timing also enabled port probing.
//
// TestMain globally enables AllowLocalTargetsEnv because many tests use fake receivers on 127.0.0.1,
// so this test must clear it; otherwise it passes whether or not the guard exists,
// which is why the original gap went undetected.
func TestEmailDialGuardRejectsLoopbackByDefault(t *testing.T) {
	f := newFakeSMTP(t)
	cfg := emailCfg(t, f, nil)

	t.Setenv(AllowLocalTargetsEnv, "") // Disable the escape hatch = default behavior.
	_, err := (emailChannel{}).Send(context.Background(), cfg, singleMsg())
	if err == nil {
		t.Fatal("默认不应允许把邮件投递到环回地址")
	}
	// No connection should be established: the Control hook rejects it before EHLO can be sent.
	if f.sawCommand("EHLO") || f.sawCommand("HELO") {
		t.Fatal("SMTP 会话已经建立——守卫没生效")
	}
	// Errors must explain how to opt in (a local postfix relay is legitimate).
	if !strings.Contains(err.Error(), AllowLocalTargetsEnv) {
		t.Errorf("拒绝信息应说明如何显式放开: %v", err)
	}
}

// TestEmailDialGuardAllowsLoopbackWhenOptedIn is the paired inverse: explicit opt-in
// must permit normal delivery. Internal SMTP / local relays are common, legitimate deployments and must not be blanket-blocked.
func TestEmailDialGuardAllowsLoopbackWhenOptedIn(t *testing.T) {
	f := newFakeSMTP(t)
	cfg := emailCfg(t, f, nil)

	t.Setenv(AllowLocalTargetsEnv, "1")
	if _, err := (emailChannel{}).Send(context.Background(), cfg, singleMsg()); err != nil {
		t.Fatalf("显式放开后本机 SMTP 应可投递: %v", err)
	}
	if !f.sawCommand("EHLO") {
		t.Fatal("未看到 EHLO——会话没真正建立")
	}
}
