package notify

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"time"
)

// dingTalkChannel implements a DingTalk custom bot.
//
// Platform constraints that shape this implementation:
//   - Each bot is limited to 20 messages/minute; excess messages may be silently dropped (even with HTTP 200),
//     so rate limiting must be client-side; see DefaultRatePerMin.
//   - Security supports signing, custom keywords, or an IP allowlist. Signing is the only option independent of
//     message content, so only signing is supported (as are bare webhooks with all three options disabled).
//   - Both success and failure return HTTP 200; inspect errcode in the body, or failed deliveries
//     will be recorded as successful.
type dingTalkChannel struct{}

func (dingTalkChannel) Kind() string { return KindDingTalk }

func (dingTalkChannel) DefaultRatePerMin() int { return 20 }

// The DingTalk Webhook URL contains access_token and is itself a credential; mask it entirely.
func (dingTalkChannel) SecretKeys() []string { return []string{"webhook", "secret"} }

// The destination is the DingTalk Webhook URL itself; changing it requires explicitly resupplying the signing key for the new URL.
func (dingTalkChannel) DestinationKeys() []string { return []string{"webhook"} }

func (dingTalkChannel) Validate(cfg map[string]any) error {
	hook := cfgString(cfg, "webhook")
	if hook == "" {
		return errors.New("Missing Webhook URL")
	}
	if err := validateHTTPURL(hook); err != nil {
		return fmt.Errorf("Invalid Webhook URL: %w", err)
	}
	return nil
}

// Send delivers one message. Use ActionCard with a button for a single item with a backlink; otherwise use markdown.
func (c dingTalkChannel) Send(ctx context.Context, cfg map[string]any, m Message) (int, error) {
	hook := cfgString(cfg, "webhook")
	if err := c.Validate(cfg); err != nil {
		return 0, Permanent(err)
	}
	endpoint, err := dingTalkSignedURL(hook, cfgString(cfg, "secret"), time.Now())
	if err != nil {
		return 0, Permanent(err)
	}

	title := markdownTitle(m)
	// DingTalk markdown has no explicit byte limit, but cap it defensively against oversized evidence fields.
	text, kept := markdownBody(m, 20000)

	var payload any
	if !m.Batch && len(m.Items) == 1 && m.Items[0].DetailURL != "" {
		payload = map[string]any{
			"msgtype": "actionCard",
			"actionCard": map[string]any{
				"title":          title,
				"text":           text,
				"btnOrientation": "0",
				"singleTitle":    "View details",
				"singleURL":      m.Items[0].DetailURL,
			},
		}
	} else {
		payload = map[string]any{
			"msgtype":  "markdown",
			"markdown": map[string]any{"title": title, "text": text},
		}
	}

	raw, err := doJSON(ctx, "POST", endpoint, nil, payload)
	if err != nil {
		return 0, err
	}
	// DingTalk embeds business errors in HTTP 200 responses.
	var res struct {
		ErrCode int    `json:"errcode"`
		ErrMsg  string `json:"errmsg"`
	}
	if err := json.Unmarshal(raw, &res); err != nil {
		return 0, fmt.Errorf("Failed to parse DingTalk response: %w (%s)", err, snippet(raw))
	}
	if res.ErrCode != 0 {
		// 301000 means signature verification failed; 310000 means keyword mismatch. Both are configuration errors
		// that retries cannot repair.
		return 0, Permanent(fmt.Errorf("DingTalk returned error %d: %s", res.ErrCode, res.ErrMsg))
	}
	return kept, nil
}

// dingTalkSignedURL appends timestamp and sign to the webhook using the official signing rules.
//
// Rule: string to sign = timestamp + "\n" + secret; the HMAC-SHA256 **key is also secret**.
// Base64-encode the result, then URL-encode it. timestamp is in milliseconds. Return unchanged when secret is empty,
// to support bots without signing enabled.
func dingTalkSignedURL(hook, secret string, now time.Time) (string, error) {
	if secret == "" {
		return hook, nil
	}
	ts := strconv.FormatInt(now.UnixMilli(), 10)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(ts + "\n" + secret))
	sign := base64.StdEncoding.EncodeToString(mac.Sum(nil))

	u, err := url.Parse(hook)
	if err != nil {
		// Do not pass err through: url.Parse error text includes the full URL, including access_token.
		return "", fmt.Errorf("Failed to parse Webhook URL: %s", redactRequestTarget(hook))
	}
	q := u.Query()
	q.Set("timestamp", ts)
	q.Set("sign", sign)
	u.RawQuery = q.Encode()
	return u.String(), nil
}

// validateHTTPURL checks URL validity and supported schemes, and checks literal IP destinations for internal addresses.
//
// Two important details:
//
//  1. **Errors must be redacted.** url.Parse returns *url.Error, whose Error() includes
//     **the complete original URL**. These providers embed credentials in URLs (DingTalk access_token,
//     WeCom key, Telegram bot token, Feishu hook id). Previously a direct `return err`
//     leaked credentials through the invalid-URL error into the test endpoint's 400 response,
//     delivery last_error records, server logs, and delivery-history responses.
//
//  2. **Check literal IPs immediately**; defer domain checks to dialing (blockInternalDial is the final
//     enforcement point and also handles DNS rebinding). This early check provides feedback when saving configuration,
//     rather than waiting for the first failed delivery.
//
// Scheme restrictions are defensive: file:///gopher:// and similar schemes can produce unexpected http.Client
// behavior (already blocked by the scheme check, with no reason to expose this surface).
func validateHTTPURL(raw string) error {
	u, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("Cannot parse URL (%s)", redactRequestTarget(raw))
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return fmt.Errorf("Only http/https are supported, got %q", u.Scheme)
	}
	if u.Host == "" {
		return errors.New("Missing hostname")
	}
	if ip := net.ParseIP(u.Hostname()); ip != nil && isBlockedDialIP(ip) && !allowLocalTargets() {
		return fmt.Errorf("Delivery to local/link-local address %s refused (if delivery to a local service is required, set %s=1)", ip, AllowLocalTargetsEnv)
	}
	return nil
}
