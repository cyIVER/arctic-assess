package server

import (
	"context"
	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"io"
)

type NativeCatalogRequest = agent.NativeCatalogRequest
type NativeCatalogGlobal = agent.NativeCatalogGlobal
type NativeCatalogResult = agent.NativeCatalogResult

func RunNativeCatalogPreflight(ctx context.Context, pg *db.DB, cfg agent.Config, in io.Reader, out io.Writer) error {
	return agent.RunNativeCatalogPreflight(ctx, pg, cfg, in, out)
}
