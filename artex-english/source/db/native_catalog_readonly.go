package db

import (
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
)

// OpenReadOnlyCatalog opens an existing database without migrations, seeds,
// database creation or background work. One pinned session owns one read-only
// repeatable-read snapshot until Close. No ORM writes are possible in that session.
func OpenReadOnlyCatalog(ctx context.Context, dsn string) (*DB, error) {
	cfg, e := pgx.ParseConfig(dsn)
	if e != nil {
		return nil, fmt.Errorf("catalog connection configuration invalid")
	}
	cfg.RuntimeParams["default_transaction_read_only"] = "on"
	cfg.RuntimeParams["default_transaction_isolation"] = "repeatable read"
	cfg.RuntimeParams["statement_timeout"] = "5000"
	cfg.RuntimeParams["idle_in_transaction_session_timeout"] = "30000"
	pool := stdlib.OpenDB(*cfg)
	pool.SetMaxOpenConns(1)
	pool.SetMaxIdleConns(1)
	fail := func() (*DB, error) { pool.Close(); return nil, fmt.Errorf("read-only catalog database unavailable") }
	if _, e = pool.ExecContext(ctx, `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`); e != nil {
		return fail()
	}
	var ro string
	if e = pool.QueryRowContext(ctx, `SHOW transaction_read_only`).Scan(&ro); e != nil || ro != "on" {
		return fail()
	}
	return &DB{pool}, nil
}
