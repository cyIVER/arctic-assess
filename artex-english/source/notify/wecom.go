package notify

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
)

// weComMarkdownLimit is the WeCom group bot markdown content hard limit in bytes, not characters.
// It is the strictest limit among all six channels and the primary reason for TruncateBytes.
const weComMarkdownLimit = 4096

// weComChannel implements WeCom group bots.
//
// Platform characteristics:
//   - Authentication uses only the URL key; signing is unsupported, so the webhook URL is the entire credential.
//   - markdown content is limited to 4096 **bytes**; oversized messages are rejected, not truncated. Chinese uses 3 bytes per character,
//     leaving room for only a little over a thousand characters; client-side truncation is required.
//   - Rate limit is 20 messages/minute, also enforced client-side.
type weComChannel struct{}

func (weComChannel) Kind() string { return KindWeCom }

func (weComChannel) DefaultRatePerMin() int { return 20 }

// WeCom has only one credential: the Webhook URL key. Signing is unsupported;
// the entire URL is the credential and no other fields need masking.
func (weComChannel) SecretKeys() []string { return []string{"webhook"} }

// WeCom's sole Webhook field is both destination and credential, so no old credential remains after changing the URL.
func (weComChannel) DestinationKeys() []string { return []string{"webhook"} }

func (weComChannel) Validate(cfg map[string]any) error {
	hook := cfgString(cfg, "webhook")
	if hook == "" {
		return errors.New("Missing Webhook URL")
	}
	if err := validateHTTPURL(hook); err != nil {
		return fmt.Errorf("Invalid Webhook URL: %w", err)
	}
	return nil
}

func (c weComChannel) Send(ctx context.Context, cfg map[string]any, m Message) (int, error) {
	if err := c.Validate(cfg); err != nil {
		return 0, Permanent(err)
	}
	// Batch messages can be long (50 one-line items plus prefix), easily exceeding 4096 bytes.
	// Truncate here rather than relying on platform rejection: rejection loses the whole batch, while truncation delivers some entries.
	content, kept := markdownBody(m, weComMarkdownLimit)
	payload := map[string]any{
		"msgtype":  "markdown",
		"markdown": map[string]any{"content": content},
	}
	raw, err := doJSON(ctx, "POST", cfgString(cfg, "webhook"), nil, payload)
	if err != nil {
		return 0, err
	}
	var res struct {
		ErrCode int    `json:"errcode"`
		ErrMsg  string `json:"errmsg"`
	}
	if err := json.Unmarshal(raw, &res); err != nil {
		return 0, fmt.Errorf("Failed to parse WeCom response: %w (%s)", err, snippet(raw))
	}
	if res.ErrCode != 0 {
		// 45009 means the API limit was exceeded. The platform's rate window rolls, so retry after backoff can work;
		// classify it explicitly as retryable. Reaching this means client rate_per_min is too aggressive;
		// retrying is only a fallback. The real fix is lowering this channel's rate limit.
		if res.ErrCode == 45009 {
			return 0, fmt.Errorf("WeCom rate limit %d: %s", res.ErrCode, res.ErrMsg)
		}
		// 93000 means an invalid webhook key: permanent failure, not repairable by retry.
		return 0, Permanent(fmt.Errorf("WeCom returned error %d: %s", res.ErrCode, res.ErrMsg))
	}
	return kept, nil
}
