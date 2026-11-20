// artex-native-preflight derives catalogs, never native admission or inference.
package main

import (
	"context"
	"fmt"
	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"os"
	"time"
)

func run() error {
	// Refuse before calling the normal config reader's non-native key branches.
	if os.Getenv("ARTEX_LLM_PROVIDER") != "codex-native" {
		return fmt.Errorf("native global environment source required")
	}
	cfg, ok := agent.FromEnv()
	if !ok {
		return fmt.Errorf("native global configuration unavailable")
	}
	dsn := os.Getenv("ARTEX_PG_DSN")
	if dsn == "" {
		return fmt.Errorf("existing catalog database required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	pg, e := db.OpenReadOnlyCatalog(ctx, dsn)
	if e != nil {
		return e
	}
	defer pg.Close()
	return agent.RunNativeCatalogPreflight(ctx, pg, cfg, os.Stdin, os.Stdout)
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
