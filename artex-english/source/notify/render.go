package notify

import (
	"strings"
	"unicode/utf8"
)

const ellipsis = "…"

// TruncateBytes truncates s to at most max bytes, preserving valid UTF-8 and whole characters.
//
// Why character boundaries matter: WeCom group bot markdown has a hard 4096 **byte** limit, not
// a character limit; Chinese characters take 3 bytes. Direct byte slicing can split a character and produce invalid
// UTF-8, causing rejection or garbled squares. Starting at the budget position,
// backtrack to the nearest rune start (utf8.RuneStart identifies continuation bytes 0b10xxxxxx).
//
// max<=0 means unlimited. Append an ellipsis after truncation unless max cannot fit it.
func TruncateBytes(s string, max int) string {
	if max <= 0 || len(s) <= max {
		return s
	}
	budget := max - len(ellipsis)
	suffix := ellipsis
	if budget < 0 {
		// If max is shorter than the ellipsis, omit it and truncate directly to avoid exceeding max.
		budget = max
		suffix = ""
	}
	cut := budget
	for cut > 0 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut] + suffix
}

// OneLine compresses multiline text to a single line: collapse all whitespace, then truncate by character count.
// Used for IM title lines; summaries often contain newlines that would disrupt tables or titles.
// max<=0 means no length limit.
func OneLine(s string, max int) string {
	s = strings.Join(strings.Fields(s), " ")
	return TruncateRunes(s, max)
}

// TruncateRunes truncates s to at most max characters, not bytes, appending an ellipsis when exceeded.
// max<=0 means unlimited.
//
// Unlike TruncateBytes, this follows platform character limits: WeCom counts bytes, Telegram counts characters.
// Using the wrong unit causes no error, only unexpectedly short messages (one Chinese character takes 3 bytes;
// a 4096-byte cut retains about 1365 characters), so retain both functions and select by channel.
func TruncateRunes(s string, max int) string {
	if max <= 0 {
		return s
	}
	runes := []rune(s)
	if len(runes) <= max {
		return s
	}
	if max <= 1 {
		return string(runes[:max])
	}
	return string(runes[:max-1]) + ellipsis
}

// TruncateHTML truncates an HTML fragment by character count without leaving partial tags.
//
// Direct character truncation can produce a partial tag such as `<a href="htt`; the platform parser may
// reject the whole message or swallow following text as an attribute. First truncate by characters,
// then check for an unclosed trailing `<` and backtrack before it.
//
// Do not balance tags (such as adding </b>): Telegram's HTML parser closes open tags automatically;
// implementing balancing would require handling quoted attributes, comments, and self-closing tags for little benefit.
func TruncateHTML(s string, max int) string {
	if max <= 0 || len([]rune(s)) <= max {
		return s
	}
	cut := TruncateRunes(s, max)
	// If the tail starts with a partial `<` (no `>` after the last `<`), backtrack before it.
	if lt := strings.LastIndex(cut, "<"); lt >= 0 && !strings.Contains(cut[lt:], ">") {
		cut = cut[:lt]
	}
	// Likewise, backtrack before a partial HTML entity (such as `&amp;` cut to `&amp`).
	// An entity-only parser may reject the **entire message** for a partial entity. Oversized
	// batch messages are common and should not cause the whole notification to be lost.
	if amp := strings.LastIndex(cut, "&"); amp >= 0 && !strings.Contains(cut[amp:], ";") {
		cut = cut[:amp]
	}
	return cut
}

// packItemCount calculates how many **whole** items fit the budget for batch-message packing.
//
// Why pack whole items instead of rendering everything then truncating: truncation makes later entries disappear,
// while delivery records still mark them delivered. Neither the message nor history reveals the loss,
// so vulnerabilities silently vanish. Whole-item packing keeps excluded entries in the database for the next batch;
// kept tells the caller how many items this message actually delivered.
//
// Parameters: maxSize<=0 means unlimited; reserve allows for message headers and footers;
// size supplies platform-specific measurement (WeCom/DingTalk count bytes, Telegram counts characters;
// using the wrong unit silently compresses Chinese messages far below the limit);
// render produces the actual text of item idx, whose content-dependent length cannot be estimated.
//
// Return at least 1 when items remain. Even an extremely long single item must be sent, relying on the caller's
// final truncation, or it could block the entire batch forever.
func packItemCount(items []Item, maxSize, reserve int, footer string, size func(string) int, render func(Item, int) string) int {
	if maxSize <= 0 {
		return len(items)
	}
	budget := maxSize - reserve - size(footer)
	if budget < 0 {
		budget = 0
	}
	used := 0
	for i, it := range items {
		used += size(render(it, i))
		if used > budget && i > 0 {
			return i
		}
	}
	return len(items)
}

// byteSize / runeSize name packItemCount's measurement units, avoiding anonymous
// func(s string) int closures that obscure which unit the call uses.
func byteSize(s string) int { return len(s) }
func runeSize(s string) int { return utf8.RuneCountInString(s) }

// assetLine renders assets as one display line, omitting those beyond limit and showing the total count.
// One vulnerability may anchor dozens of assets; listing all would overflow the message.
func assetLine(assets []string, limit int) string {
	if len(assets) == 0 {
		return ""
	}
	if limit <= 0 || len(assets) <= limit {
		return strings.Join(assets, ", ")
	}
	return strings.Join(assets[:limit], ", ") + " (" + itoa(len(assets)) + " total)"
}

// itoa is a short alias for strconv.Itoa, used only in display text to avoid importing strconv everywhere.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
