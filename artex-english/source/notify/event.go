package notify

// Snapshot is the contract of the notification_events.snapshot JSONB column. The database
// finding transaction writes it; the server delivery engine and filters read it. It belongs here
// as a notification-domain payload: db only serializes it and does not interpret its fields.
//
// Store finding fields redundantly rather than looking them up during rendering: findings can
// later be renamed or change severity/status. Notifications must reflect the conclusion at event time;
// a later downgrade to low would mislead readers. Fan-out and rendering also avoid joining findings/tasks/assets.
type Snapshot struct {
	// Event kind: finding_created / finding_status_changed
	Kind      string  `json:"kind"`
	FindingID int64   `json:"finding_id"`
	TaskID    int64   `json:"task_id"`
	VulnClass string  `json:"vulnclass"`
	Name      string  `json:"name"`
	Severity  string  `json:"severity"`
	Summary   string  `json:"summary"`
	AssetIDs  []int64 `json:"asset_ids"`
	// Nonempty only for kind=finding_status_changed.
	FromStatus string `json:"from_status,omitempty"`
	ToStatus   string `json:"to_status,omitempty"`
}

// Item is a pending finding notification for channel rendering.
type Item struct {
	FindingID int64
	Name      string
	VulnClass string
	Severity  string
	Summary   string
	// Assets contains resolved asset display names (e.g. domains/IPs), populated by the server;
	// this package does not access the database and cannot resolve names.
	Assets []string
	// DetailURL links back to finding details; empty means public_base_url is not configured, so omit it.
	DetailURL string
	// For status-change events; when both are nonempty, render e.g. Pending → Fixed.
	FromStatus string
	ToStatus   string
}

// IsStatusChange reports whether this item is a status-change event.
func (i Item) IsStatusChange() bool { return i.FromStatus != "" || i.ToStatus != "" }

// Title returns the display title: prefer the user-provided name, then vulnclass,
// then a placeholder when both are empty; never return an empty title.
func (i Item) Title() string {
	if i.Name != "" {
		return i.Name
	}
	if i.VulnClass != "" {
		return i.VulnClass
	}
	return "(Unnamed finding)"
}

// Message contains the complete content of one channel delivery.
type Message struct {
	// Length is 1 for individual delivery, or a whole batch for digest delivery.
	// An empty slice is invalid; callers must supply at least one item.
	Items []Item
	// Batch=true renders a digest with a different title, time window and item count.
	Batch bool
	// WindowMinutes is the digest period in minutes, used only with Batch=true for Last N minutes.
	// Pass it explicitly from configuration instead of using time.Since, keeping rendering deterministic and testable.
	WindowMinutes int
	// HomeURL is the dashboard address (global public_base_url); empty omits the dashboard link.
	HomeURL string
}
