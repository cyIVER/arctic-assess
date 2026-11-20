package notify

import (
	"context"
	"errors"
	"sort"
	"strconv"
	"strings"
)

// Channel adapts a notification channel. Implementations must be stateless: multiple channel
// configurations reuse one instance concurrently; all credentials come from cfg.
type Channel interface {
	// Kind returns the channel kind identifier, which must match the registry key.
	Kind() string
	// Validate checks required fields and formats when saving configuration. Errors are shown directly to
	// the administrator, so name the missing field rather than saying only that configuration is invalid.
	Validate(cfg map[string]any) error
	// Send delivers one message and returns the number of items actually delivered and an error.
	//
	// Platforms limit message length; digests are truncated when the whole batch does not fit.
	// If callers mark the entire batch delivered unconditionally, truncated items disappear from messages
	// while delivery history reports success, hiding undelivered findings. With kept,
	// callers mark only the first kept items delivered and leave the rest for the next batch.
	//
	// An error means delivery failed; *PermanentError means it must not be retried.
	// On failure kept is meaningless and callers must ignore it.
	Send(ctx context.Context, cfg map[string]any, m Message) (int, error)
	// DefaultRatePerMin returns the officially recommended per-minute limit, used as the default rate
	// for newly created channel instances. Zero means no known limit.
	DefaultRatePerMin() int
	// SecretKeys names credential fields. The API masks their values on readback;
	// masked incoming values retain the original stored values on update. Only the implementation knows
	// which fields are credentials (the whole WeCom Webhook URL, versus DingTalk signing secret),
	// so channels must declare this knowledge rather than requiring higher layers to guess.
	SecretKeys() []string
	// DestinationKeys names configuration fields determining where messages are sent.
	//
	// Like SecretKeys this is security-sensitive: destinations and credentials are separate fields.
	// Allowing destination changes while retaining credentials would let anyone who can edit channel settings
	// send stored credentials to a server they control, defeating configuration masking.
	// See PrepareConfigUpdate.
	DestinationKeys() []string
}

// registry is explicit rather than self-registering via init(), so all supported channels are visible
// in one place and adding channels exposes omissions at compile time rather than relying on runtime side effects.
var registry = map[string]Channel{
	KindDingTalk: dingTalkChannel{},
	KindFeishu:   feishuChannel{},
	KindWeCom:    weComChannel{},
	KindWebhook:  webhookChannel{},
	KindTelegram: telegramChannel{},
	KindEmail:    emailChannel{},
}

// Get returns the implementation for a channel kind.
func Get(kind string) (Channel, bool) {
	c, ok := registry[kind]
	return c, ok
}

// ValidKind reports whether a channel kind is supported.
func ValidKind(kind string) bool {
	_, ok := registry[kind]
	return ok
}

// Kinds returns all supported channel kinds in lexical order for stable UI dropdowns.
func Kinds() []string {
	out := make([]string, 0, len(registry))
	for k := range registry {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// PermanentError marks a nonretryable delivery failure: bad credentials, destination rejection, invalid body, etc.
// Retries only help transient failures (network instability, rate limits, remote 5xx); repeated backoff on
// permanent failures cannot succeed and buries the actual error in retry logs.
type PermanentError struct{ Err error }

func (e *PermanentError) Error() string { return e.Err.Error() }
func (e *PermanentError) Unwrap() error { return e.Err }

// Permanent marks err as a permanent failure. It returns nil for nil err,
// allowing `return Permanent(someCheck())`.
func Permanent(err error) error {
	if err == nil {
		return nil
	}
	return &PermanentError{Err: err}
}

// IsPermanent reports whether the error chain contains a permanent-failure marker.
func IsPermanent(err error) bool {
	var pe *PermanentError
	return errors.As(err, &pe)
}

// ---- Configuration reading helpers ----
//
// Channel configuration comes from a JSONB column, decoded by encoding/json as map[string]any;
// numbers are float64 and arrays are []any. These helpers centralize conversion and tolerate
// type differences caused by empty UI inputs (e.g. a string-valued port).

// cfgString reads a string and trims whitespace often introduced by copying from web forms.
func cfgString(cfg map[string]any, key string) string {
	v, ok := cfg[key]
	if !ok {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(s)
}

// cfgInt reads an integer from float64 (the JSON default) or a string.
func cfgInt(cfg map[string]any, key string) int {
	switch v := cfg[key].(type) {
	case float64:
		return int(v)
	case int:
		return v
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(v))
		if err != nil {
			return 0
		}
		return n
	default:
		return 0
	}
}

// cfgBool reads a boolean, accepting strings "true"/"1".
func cfgBool(cfg map[string]any, key string) bool {
	switch v := cfg[key].(type) {
	case bool:
		return v
	case string:
		s := strings.ToLower(strings.TrimSpace(v))
		return s == "true" || s == "1" || s == "yes"
	default:
		return false
	}
}

// cfgStrings reads a string array, trims whitespace and drops empty values.
func cfgStrings(cfg map[string]any, key string) []string {
	raw, ok := cfg[key].([]any)
	if !ok {
		// Also accept a single string for forms submitting one value.
		if s := cfgString(cfg, key); s != "" {
			return []string{s}
		}
		return nil
	}
	out := make([]string, 0, len(raw))
	for _, v := range raw {
		s, ok := v.(string)
		if !ok {
			continue
		}
		if s = strings.TrimSpace(s); s != "" {
			out = append(out, s)
		}
	}
	return out
}

// cfgMap reads a string map (e.g. custom HTTP headers), trims keys/values and drops empty keys.
func cfgMap(cfg map[string]any, key string) map[string]string {
	raw, ok := cfg[key].(map[string]any)
	if !ok {
		return nil
	}
	out := make(map[string]string, len(raw))
	for k, v := range raw {
		k = strings.TrimSpace(k)
		if k == "" {
			continue
		}
		s, ok := v.(string)
		if !ok {
			continue
		}
		out[k] = s
	}
	return out
}
