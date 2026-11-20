package server

import (
	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	actool "github.com/Autumn-27/norma/tool"
)

func resolveNativeTools(pg *db.DB, key string, tools []actool.CoreTool) []actool.CoreTool {
	return agent.ResolveNativeTools(pg, key, tools)
}
