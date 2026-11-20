// Package notify adapts IM and email channels for finding notifications.
//
// This is a leaf package depending only on the standard library, not the database
// or server. Channel configuration is passed as map[string]any (the JSONB column
// notification_channels.config); content is passed as Message. Signature generation,
// UTF-8 truncation and filter matching can therefore be tested without PostgreSQL;
// the server only orchestrates delivery.
//
// Channel implementations must be stateless: multiple channel configurations,
// including multiple bots of one kind, reuse an instance concurrently. All credentials
// come from cfg; never cache webhook URLs or similar configuration in instance fields.
package notify

// Channel kind identifiers also define the valid notification_channels.kind values.
// The server validates an allowlist, like findings.status, rather than a DB CHECK,
// making it easier to add channels later.
const (
	KindDingTalk = "dingtalk" // DingTalk custom bot
	KindFeishu   = "feishu"   // Feishu (including Lark) custom bot
	KindWeCom    = "wecom"    // WeCom group bot
	KindWebhook  = "webhook"  // Generic Webhook: custom method/headers/JSON template
	KindTelegram = "telegram" // Telegram Bot API
	KindEmail    = "email"    // SMTP email
)

// Event kinds corresponding to notification_events.kind.
const (
	EventFindingCreated       = "finding_created"
	EventFindingStatusChanged = "finding_status_changed"
)

// InitKind is the fallback when kind is empty in configuration.
const InitKind = KindDingTalk

// severityRank maps severity to an ordinal. Unknown severities return 0, so any
// min_severity setting excludes them: do not notify when uncertain, avoiding spam.
var severityRank = map[string]int{
	"low":      1,
	"medium":   2,
	"high":     3,
	"critical": 4,
}

// SeverityRank returns the severity ordinal, or 0 for unknown values.
func SeverityRank(severity string) int { return severityRank[severity] }

// SeverityLabel returns an English severity label with an emoji for message titles
// and card colors. Unknown values are returned verbatim, never invented.
func SeverityLabel(severity string) string {
	switch severity {
	case "critical":
		return "🔴 Critical"
	case "high":
		return "🟠 High"
	case "medium":
		return "🟡 Medium"
	case "low":
		return "🔵 Low"
	default:
		return severity
	}
}

// StatusLabel renders an English disposition label for status-change messages.
func StatusLabel(status string) string {
	switch status {
	case "pending":
		return "Pending"
	case "in_progress":
		return "In progress"
	case "confirmed":
		return "Confirmed"
	case "resolved":
		return "Resolved"
	case "fixed":
		return "Fixed"
	case "false_positive":
		return "False positive"
	case "ignored":
		return "Ignored"
	case "duplicate":
		return "Duplicate"
	case "risk_accepted":
		return "Risk accepted"
	default:
		return status
	}
}

// AtLeast reports whether severity reaches min. Empty min admits all severities.
// Unknown severity has ordinal 0 and is rejected by any valid nonempty min (see severityRank).
func AtLeast(severity, min string) bool {
	if min == "" {
		return true
	}
	return SeverityRank(severity) >= SeverityRank(min)
}
