package agent

import (
	"encoding/json"
	"github.com/Autumn-27/artex/db"
	actool "github.com/Autumn-27/norma/tool"
	"slices"
)

// resolveNativeTools is shared by normal runtime assembly and read-only preflight.
func ResolveNativeTools(pg *db.DB, agentKey string, tools []actool.CoreTool) []actool.CoreTool {
	a, err := pg.GetAgentByKey(agentKey)
	if err != nil || a == nil || !a.Enabled {
		return []actool.CoreTool{}
	}
	rows, err := pg.ListTools()
	if err != nil {
		return []actool.CoreTool{}
	}
	byKey := map[string]*db.Tool{}
	for _, row := range rows {
		byKey[row.Key] = row
	}
	out := make([]actool.CoreTool, 0, len(tools))
	for _, t := range tools {
		// The SDK six are code-owned and already executor-wrapped by agent assembly.
		if t.Name() == "Read" || t.Name() == "Write" || t.Name() == "Edit" || t.Name() == "LS" || t.Name() == "Bash" || t.Name() == "sleep" {
			out = append(out, t)
			continue
		}
		row, ok := byKey[t.Name()]
		if !ok || !row.Enabled || !slices.Contains(row.Agents, agentKey) || row.Kind == "shell" {
			continue
		}
		var schema map[string]any
		if len(row.Schema) > 0 && json.Unmarshal(row.Schema, &schema) != nil {
			return []actool.CoreTool{}
		}
		out = append(out, DecorateTool(t, row.Description, schema))
	}
	return out
}
