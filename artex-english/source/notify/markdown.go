package notify

import (
	"fmt"
	"strings"
)

// Shared message rendering for Markdown-based channels (DingTalk and WeCom).
// Feishu uses card JSON; Telegram and email use HTML, rendered in their adapters.

// maxAssetsShown limits displayed assets. A vulnerability can anchor dozens of assets;
// listing all would overflow the message without adding value. Few readers inspect domains beyond the fourth in IM.
const maxAssetsShown = 3

// maxSummaryRunes limits summary length. IM messages prompt readers to view details;
// they are not the report itself. Full content lives on the platform.
const maxSummaryRunes = 120

// markdownReservedBytes reserves room for the header (batch summary, severity distribution, and possible truncation notice)
// and footer (platform link). Deduct this from the whole-item packing budget to prevent truncation of either;
// otherwise readers cannot identify the batch or how many items are missing.
const markdownReservedBytes = 320

// markdownEscape escapes markdown metacharacters.
//
// Why this is necessary: vulnerability title, summary, class, and asset display name all come from **untrusted sources**.
// Titles and summaries come from model output informed by target responses; asset URLs are full scanned
// URLs, including target-controlled query strings. Without escaping, a title such as
//
//	Login SQL injection\n[Urgent: verify your account here](http://attacker.tld)
//
// would render as a **clickable external link** in the security engineer's DingTalk/Feishu client;
// `![](http://attacker.tld/beacon)` is fetched by the client during rendering, indicating
// that the vulnerability was viewed and exposing the reader's IP. Even benign injected bold text or
// blockquotes can push serious vulnerabilities below the fold.
//
// The escape set covers headings, links, emphasis, lists, blockquotes, and strikethrough: characters that change structure or create clickable
// elements. Process `\` first to avoid escaping newly inserted backslashes again.
func markdownEscape(s string) string {
	replacer := strings.NewReplacer(
		`\`, `\\`,
		"`", "\\`",
		"*", `\*`,
		"_", `\_`,
		"[", `\[`,
		"]", `\]`,
		"(", `\(`,
		")", `\)`,
		"!", `\!`,
		"#", `\#`,
		">", `\>`,
		"|", `\|`,
		"~", `\~`,
	)
	return replacer.Replace(s)
}

// markdownText compresses untrusted text to one line and escapes it for markdown bodies.
// Single-line conversion complements escaping: newlines alone can forge list items or blockquotes,
// which character escaping cannot stop.
func markdownText(s string, maxRunes int) string {
	return markdownEscape(OneLine(s, maxRunes))
}

// markdownTitle returns the message title (IM title bar/card title) as **unescaped original text**.
//
// Deliberately do not escape here: this title is shared across rendering contexts: markdown bodies, Telegram
// HTML, Feishu card plain_text, generic Webhook JSON, and email subjects. Each context has
// different escaping rules (markdown escapes leave visible backslashes in HTML and contaminate JSON
// data), so each output sink must perform its own escaping; see writeItem / feishuItemLines /
// telegramEscape. Previously adding markdown escaping in the shared function caused Telegram messages
// to show literal backslashes such as `\(1\)`.
func markdownTitle(m Message) string {
	if m.Batch {
		return fmt.Sprintf("Finding digest · %d total", len(m.Items))
	}
	if len(m.Items) == 0 {
		return "Finding notification"
	}
	it := m.Items[0]
	return fmt.Sprintf("[%s] %s", SeverityLabel(it.Severity), OneLine(it.Title(), 0))
}

// markdownBody renders the message body and returns it with **the number of items actually included**.
//
// kept counts items actually delivered. Callers mark only the first kept entries
// delivered; entries excluded by channel limits must remain for the next batch, not be
// marked successful. Otherwise truncation causes silent loss: delivery records claim all items succeeded,
// with no indication that the latter part was never sent.
//
// maxBytes<=0 means unlimited.
func markdownBody(m Message, maxBytes int) (string, int) {
	if !m.Batch {
		if len(m.Items) == 0 {
			return "", 0
		}
		var b strings.Builder
		writeItem(&b, m.Items[0], "", true)
		// Send even an oversized single item, with final truncation as fallback: partial vulnerability information
		// is better than no notification.
		return TruncateBytes(b.String(), maxBytes), 1
	}

	footer := ""
	if m.HomeURL != "" {
		footer = fmt.Sprintf("\n[View all in platform](%s)\n", m.HomeURL)
	}
	kept := packItemCount(m.Items, maxBytes, markdownReservedBytes, footer, byteSize, func(it Item, idx int) string {
		var b strings.Builder
		writeItem(&b, it, fmt.Sprintf("%d. ", idx+1), false)
		return b.String()
	})

	items := m.Items[:kept]
	var b strings.Builder
	b.WriteString(markdownBatchIntro(m, items, len(m.Items)))
	for i, it := range items {
		writeItem(&b, it, fmt.Sprintf("%d. ", i+1), false)
	}
	b.WriteString(footer)
	return TruncateBytes(b.String(), maxBytes), kept
}

// markdownBatchIntro renders the batch introduction: time window, item count, and severity distribution.
// This lets recipients decide whether immediate action is needed without opening the platform.
//
// items are **actually included** entries; total is the intended batch size. If they differ, explicitly state
// how many continue in the next message; otherwise readers assume the header count covers everything,
// while unsent items are entirely absent from the interface.
func markdownBatchIntro(m Message, items []Item, total int) string {
	var b strings.Builder
	if m.WindowMinutes > 0 {
		fmt.Fprintf(&b, "**%d minutes: %d new findings**", m.WindowMinutes, total)
	} else {
		fmt.Fprintf(&b, "**%d new findings**", total)
	}
	if extra := total - len(items); extra > 0 {
		fmt.Fprintf(&b, " (showing the first %d; the remaining %d will follow in the next message)", len(items), extra)
	}
	// Show severity distribution so readers can spot serious entries. Count only entries **actually included**
	// in this message so the critical count matches the entries visible below.
	counts := map[string]int{}
	for _, it := range items {
		counts[it.Severity]++
	}
	var parts []string
	for _, sev := range []string{"critical", "high", "medium", "low"} {
		if n := counts[sev]; n > 0 {
			parts = append(parts, fmt.Sprintf("%s %d", SeverityLabel(sev), n))
		}
	}
	if len(parts) > 0 {
		b.WriteString("\n" + strings.Join(parts, " · "))
	}
	b.WriteString("\n\n")
	return b.String()
}

// writeItem renders one vulnerability entry.
//
// prefix is the batch sequence number; single=true renders full details (summary and backlink).
// Batch lists show a one-line summary, or a 50-item batch would become a long document.
//
// All external content (title/class/assets/summary) passes through markdownText:
// single-line conversion plus escaping. The backlink comes from administrator-configured public_base_url, not untrusted content,
// and must remain clickable, so output it unchanged.
func writeItem(b *strings.Builder, it Item, prefix string, single bool) {
	line := fmt.Sprintf("%s**%s · %s**", prefix, SeverityLabel(it.Severity), markdownText(it.Title(), 0))
	if !single {
		// Batch mode: one line with compressed assets and summary appended.
		var extras []string
		if a := assetLine(it.Assets, maxAssetsShown); a != "" {
			extras = append(extras, markdownText(a, 0))
		}
		if it.Summary != "" {
			extras = append(extras, markdownText(it.Summary, 60))
		}
		if len(extras) > 0 {
			line += " — " + strings.Join(extras, " · ")
		}
		b.WriteString(line + "\n")
		return
	}
	b.WriteString(line + "\n")
	if it.IsStatusChange() {
		fmt.Fprintf(b, "**Status change**: %s → %s\n",
			markdownText(StatusLabel(it.FromStatus), 0), markdownText(StatusLabel(it.ToStatus), 0))
	}
	if it.VulnClass != "" && it.VulnClass != it.Title() {
		fmt.Fprintf(b, "**Type**: %s\n", markdownText(it.VulnClass, 0))
	}
	if a := assetLine(it.Assets, maxAssetsShown); a != "" {
		fmt.Fprintf(b, "**Assets**: %s\n", markdownText(a, 0))
	}
	if it.Summary != "" {
		if s := markdownText(it.Summary, maxSummaryRunes); s != "" {
			fmt.Fprintf(b, "**Summary**: %s\n", s)
		}
	}
	if it.DetailURL != "" {
		fmt.Fprintf(b, "[View details](%s)\n", it.DetailURL)
	}
}
