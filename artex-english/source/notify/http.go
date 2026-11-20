package notify

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"syscall"
	"time"
)

// allowLocalTargets controls delivery to loopback / link-local addresses.
//
// Denied by default. IM bots and public mail servers should not use these ranges, while they can reach
// sensitive destinations: management ports of colocated services and cloud metadata endpoints
// (169.254.169.254, which can expose instance credentials). Administrators configure delivery URLs, but XSS/CSRF
// hijacking an admin session, or another person sharing the JWT, could alter configuration to read responses:
// doJSON stores the first 200 response-body bytes from 4xx/5xx responses in last_error, and delivery history
// echoes it back, providing a semi-blind read primitive.
//
// However, a local SMTP relay (postfix on 127.0.0.1:25) is common for self-hosted mail,
// so a blanket ban would block legitimate users. Provide an explicit escape hatch rather than hardcoded access:
// set ARTEX_NOTIFY_ALLOW_LOCAL=1 to allow it.
//
// Export AllowLocalTargetsEnv so tests can explicitly enable this: tests in this package and server
// frequently use httptest receivers on 127.0.0.1, which the guard otherwise blocks.
const AllowLocalTargetsEnv = "ARTEX_NOTIFY_ALLOW_LOCAL"

func allowLocalTargets() bool {
	v := strings.TrimSpace(os.Getenv(AllowLocalTargetsEnv))
	return v == "1" || strings.EqualFold(v, "true")
}

// isBlockedDialIP reports whether a destination IP is in a range denied for delivery by default.
//
// Reject only loopback, link-local (including cloud metadata 169.254.169.254), unspecified, and multicast addresses.
// **Do not reject** RFC1918 private networks: internal Mattermost / SMTP relays are common legitimate deployments;
// blocking them would make the feature unusable in real environments. This tradeoff is deliberate:
// block genuinely sensitive destinations without disabling normal deployments.
func isBlockedDialIP(ip net.IP) bool {
	if ip == nil {
		return true
	}
	// Unmap IPv4-mapped IPv6 (::ffff:127.0.0.1) before checking, or it can bypass validation.
	if v4 := ip.To4(); v4 != nil {
		ip = v4
	}
	return ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsInterfaceLocalMulticast() || ip.IsUnspecified() || ip.IsMulticast()
}

// blockInternalDial is the http.Transport dialer's Control hook; it checks the destination
// **when establishing the connection**.
//
// Why enforce at dial time rather than only when saving configuration: this is the final enforcement point.
// It covers two ways around configuration validation: DNS rebinding (resolving to a public IP at validation,
// then an internal IP at connection time) and redirects (cross-host redirects are already denied, but same-host redirects
// may still target another path).
func blockInternalDial(_, address string, _ syscall.RawConn) error {
	if allowLocalTargets() {
		return nil
	}
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return err
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return fmt.Errorf("Cannot resolve destination address %q", host)
	}
	if isBlockedDialIP(ip) {
		return fmt.Errorf("Delivery to local/link-local address %s refused (if delivery to a local service is required, set %s=1)", ip, AllowLocalTargetsEnv)
	}
	return nil
}

// notifyTransport adds only a dial guard to the default Transport.
// Clone preserves all default tuning (connection pooling, HTTP/2, timeouts, proxy, etc.),
// avoiding unrelated behavior changes just to add one check.
var notifyTransport = func() *http.Transport {
	t, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		return &http.Transport{}
	}
	clone := t.Clone()
	clone.DialContext = (&net.Dialer{Timeout: 10 * time.Second, Control: blockInternalDial}).DialContext
	return clone
}()

// httpClient is shared by all channel deliveries.
//
// Deliberately **do not** reuse the project's global outbound proxy (GlobalProxy on the server side): it carries penetration
// test target traffic, often through unstable tunnels. Notification availability must not depend on target-network instability.
// IM notifications connect directly. Use a 15-second timeout; a slower peer is effectively failing.
//
// Reject cross-host redirects: delivery URLs are fixed endpoints and normally do not
// redirect to another host. Provider credentials (DingTalk access_token, WeCom key, Telegram
// bot token) are **in the URL**, so following cross-host redirects hands them to the destination. Same-host
// redirects, such as adding a trailing slash, remain allowed.
var httpClient = &http.Client{
	Timeout:   15 * time.Second,
	Transport: notifyTransport,
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return errors.New("Too many redirects")
		}
		if len(via) > 0 && req.URL.Host != via[0].URL.Host {
			return fmt.Errorf("Cross-host redirect refused (%s → %s)", via[0].URL.Host, req.URL.Host)
		}
		return nil
	},
}

// respBodyLimit bounds response-body reads. A malfunctioning peer may return huge content; we need only
// an error code and a short description for delivery history.
const respBodyLimit = 8 << 10

// doJSON sends one request and returns the bounded response body.
//
// A nil payload sends an empty body (for GET or platforms requiring no body).
// headers are appended unchanged for generic Webhook custom headers.
//
// Error classification is central: network failures and 5xx/408/429 are retryable;
// other 4xx are permanent. Retrying a 403 merely logs the same error three times.
func doJSON(ctx context.Context, method, url string, headers map[string]string, payload any) ([]byte, error) {
	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload)
		if err != nil {
			// Serialization failure is a local bug (incorrect configuration field type); retries cannot repair it.
			return nil, Permanent(fmt.Errorf("Failed to build request body: %w", err))
		}
		body = bytes.NewReader(raw)
	}
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		// An invalid URL is usually a user input mistake and is a permanent failure.
		// Again, do not pass err through: url.Parse errors include the complete URL.
		return nil, Permanent(fmt.Errorf("Invalid request URL: %s", redactRequestTarget(url)))
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json; charset=utf-8")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		// Connection refusal, DNS failure, and timeouts are usually transient; retry with backoff.
		//
		// Redact error text before exposing it. http.Client.Do returns *url.Error,
		// whose Error() is `Op "complete URL": underlying error`; provider credentials are **in the URL**
		// (DingTalk access_token, WeCom key, Feishu hook id, Telegram /bot<token>/).
		// Without redaction, credentials flow to four places: notification_deliveries
		// last_error (plaintext storage), delivery-history responses (**bypassing channel configuration masking**),
		// server logs, and the test-send endpoint's 502 text returned to the frontend.
		return nil, fmt.Errorf("Request failed: %s", redactTransportError(err))
	}
	defer resp.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(resp.Body, respBodyLimit))
	if readErr != nil {
		return nil, fmt.Errorf("Failed to read response: %w", readErr)
	}
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return raw, nil
	}
	// 429 (rate limiting) and 408 (timeout) merit retries; other 4xx indicate configuration or permission errors.
	if resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode == http.StatusRequestTimeout {
		return nil, fmt.Errorf("Remote rate limit or timeout (HTTP %d): %s", resp.StatusCode, snippet(raw))
	}
	if resp.StatusCode >= 500 {
		return nil, fmt.Errorf("Remote server error (HTTP %d): %s", resp.StatusCode, snippet(raw))
	}
	return nil, Permanent(fmt.Errorf("Remote request rejected (HTTP %d): %s", resp.StatusCode, snippet(raw)))
}

// snippet compresses a response body to a short single line for error messages. Responses may contain newlines and whitespace;
// putting them directly in last_error would break delivery-history layout.
func snippet(raw []byte) string {
	return OneLine(string(raw), 200)
}

// redactRequestTarget reduces delivery URLs to "scheme://host/…" for error messages.
//
// This is the package's sole URL-redaction policy, deliberately **coarse**: retain only scheme and host,
// discard everything else. There is no universal safe way to identify which URL component is a credential:
//
//	DingTalk credentials in query      /robot/send?access_token=xxx
//	WeCom credentials in query         /cgi-bin/webhook/send?key=xxx
//	Feishu credentials in **last path segment** /open-apis/bot/v2/hook/<hook_id>
//	Telegram credentials in **middle path segment** /bot<token>/sendMessage
//
// Keeping only useful parts would require channel-specific patches; missing any provider would leak credentials.
// The host suffices for troubleshooting DNS, connection, and certificate problems;
// identify the specific bot using the masked suffix in channel configuration.
//
// Return a fixed placeholder on parse failure; never echo the original string.
func redactRequestTarget(raw string) string {
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return "(Unparseable address)"
	}
	return u.Scheme + "://" + u.Host + "/…"
}

// redactTransportError removes URLs from transport errors, preserving only the underlying cause.
//
// *url.Error has {Op, URL, Err}; its Error() prints the URL too.
// Explicitly extract Err to bypass Error(), which is more reliable than subsequent string replacement:
// replacement must handle all URL-encoded and escaped variants and can miss some.
func redactTransportError(err error) string {
	var uerr *url.Error
	if errors.As(err, &uerr) {
		host := ""
		if u, parseErr := url.Parse(uerr.URL); parseErr == nil {
			host = u.Host
		}
		if uerr.Err != nil {
			return fmt.Sprintf("%s %s: %s", uerr.Op, host, uerr.Err)
		}
		return fmt.Sprintf("%s %s: Unknown error", uerr.Op, host)
	}
	// Non-*url.Error values (such as redirect-policy errors) may also contain URLs; redact them consistently.
	return redactURLsInText(err.Error())
}

// redactURLsInText replaces http(s) URLs in text with redacted forms.
//
// This is a fallback for errors without structured fields (redirect-policy errors and custom third-party errors).
// Recognize only http/https prefixes; split at whitespace and quotes, which cannot occur in URLs.
func redactURLsInText(s string) string {
	var b strings.Builder
	for i := 0; i < len(s); {
		rest := s[i:]
		if strings.HasPrefix(rest, "http://") || strings.HasPrefix(rest, "https://") {
			end := len(rest)
			if j := strings.IndexAny(rest, " \t\n\"'"); j >= 0 {
				end = j
			}
			b.WriteString(redactRequestTarget(rest[:end]))
			i += end
			continue
		}
		b.WriteByte(s[i])
		i++
	}
	return b.String()
}
