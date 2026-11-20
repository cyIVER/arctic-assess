package notify

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"
)

// Filter is the contract for notification_channels.filter, a JSONB column containing channel-instance filters.
// All fields are optional; omitted means no filtering, also the fallback for malformed configuration; see ParseFilter.
type Filter struct {
	// MinSeverity is the minimum severity threshold (low/medium/high/critical); empty means no threshold.
	MinSeverity string `json:"min_severity"`
	// Empty TaskIDs / AssetIDs arrays mean unrestricted; otherwise the event must intersect them.
	TaskIDs  []int64 `json:"task_ids"`
	AssetIDs []int64 `json:"asset_ids"`
	// Empty VulnClassInclude accepts all; otherwise vulnclass must match at least one keyword.
	// VulnClassExclude rejects any keyword match (exclusion takes precedence over inclusion).
	// Matching uses case-insensitive substrings, safer than regex: invalid user regex cannot silently disable the channel.
	VulnClassInclude []string `json:"vulnclass_include"`
	VulnClassExclude []string `json:"vulnclass_exclude"`
	// OnStatusChange controls whether the channel receives vulnerability status-change events (meaningful only in realtime mode).
	OnStatusChange bool `json:"on_status_change"`
}

// ParseFilter parses channel filter configuration.
//
// **Never returns an error.** This is deliberate: malformed filter configuration falls back to a zero-value
// Filter (= no filtering = match all), because in a vulnerability notification system **an extra notification is better than
// silently missing a critical one**. Treating parse failure as no delivery gives users a channel that looks configured
// but sends nothing, the worst failure mode.
func ParseFilter(raw []byte) Filter {
	var f Filter
	if len(raw) == 0 {
		return f
	}
	// On parse failure, f remains zero-valued, meaning no filtering.
	_ = json.Unmarshal(raw, &f)
	return f
}

// ValidMinSeverity reports whether s is a valid severity threshold (empty means no threshold).
func ValidMinSeverity(s string) bool {
	if s == "" {
		return true
	}
	_, ok := severityRank[s]
	return ok
}

// Validate checks fields with **restricted values** when saving a channel.
//
// Why reject at write time: Match evaluates unknown thresholds as `rank >= 0`, always true;
// thus a typo in min_severity ("hgih") **silently disables filtering** and
// pushes everything. This aligns with the package's preference for extra delivery over missed delivery,
// but users believe severity filtering is active while every vulnerability floods the group,
// with no indication of misconfiguration. Reject such silent degradation at the input boundary.
//
// Validate is used **only for writes**. Reads retain ParseFilter's tolerant semantics,
// so existing invalid values do not prevent loading the entire channel.
func (f Filter) Validate() error {
	if !ValidMinSeverity(f.MinSeverity) {
		return fmt.Errorf("Invalid minimum severity %q; choose low / medium / high / critical, or leave empty for no limit", f.MinSeverity)
	}
	return nil
}

// Match decides whether an event should be delivered to a channel with this filter.
//
// **Never returns an error**, for the same reason as ParseFilter: internal anomalies count as matches.
// Evaluation order: event type -> severity threshold -> task/asset scope -> vulnerability-class keywords.
func Match(f Filter, s Snapshot) bool {
	// Only explicitly enabled channels receive status-change events. Disabled by default because most users
	// expect notifications about newly discovered vulnerabilities, not a log of every status transition.
	if s.Kind == EventFindingStatusChanged && !f.OnStatusChange {
		return false
	}
	if !AtLeast(s.Severity, f.MinSeverity) {
		return false
	}
	if len(f.TaskIDs) > 0 && !slices.Contains(f.TaskIDs, s.TaskID) {
		return false
	}
	if len(f.AssetIDs) > 0 && !intersectsInt(f.AssetIDs, s.AssetIDs) {
		return false
	}
	// Exclusion first: any excluded keyword rejects the event even if it also matches the include list.
	if len(f.VulnClassExclude) > 0 && containsAnyFold(s.VulnClass, f.VulnClassExclude) {
		return false
	}
	if len(f.VulnClassInclude) > 0 && !containsAnyFold(s.VulnClass, f.VulnClassInclude) {
		return false
	}
	return true
}

func intersectsInt(a, b []int64) bool {
	// Linear scans suffice for these small sets, each typically a few dozen manually selected values;
	// building a map costs more than it saves.
	for _, v := range b {
		if slices.Contains(a, v) {
			return true
		}
	}
	return false
}

// containsAnyFold reports whether s contains any keyword, case-insensitively.
func containsAnyFold(s string, keywords []string) bool {
	lower := strings.ToLower(s)
	for _, kw := range keywords {
		kw = strings.ToLower(strings.TrimSpace(kw))
		if kw != "" && strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}
