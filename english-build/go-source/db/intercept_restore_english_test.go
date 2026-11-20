package db

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
)

// Capture the actual restore helper's SQL payload without connecting to PostgreSQL.
type restoreCapture struct{ payload string }
type restoreConnector struct{ capture *restoreCapture }
type restoreDriver struct{}
type restoreConn struct{ capture *restoreCapture }
type restoreTx struct{}

func (c restoreConnector) Connect(context.Context) (driver.Conn, error) {
	return restoreConn{c.capture}, nil
}
func (restoreConnector) Driver() driver.Driver          { return restoreDriver{} }
func (restoreDriver) Open(string) (driver.Conn, error)  { return nil, fmt.Errorf("connector required") }
func (restoreConn) Prepare(string) (driver.Stmt, error) { return nil, fmt.Errorf("unexpected prepare") }
func (restoreConn) Close() error                        { return nil }
func (restoreConn) Begin() (driver.Tx, error)           { return restoreTx{}, nil }
func (restoreTx) Commit() error                         { return nil }
func (restoreTx) Rollback() error                       { return nil }
func (c restoreConn) ExecContext(_ context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
	if !strings.Contains(q, "INSERT INTO intercept_pending SELECT * FROM json_populate_recordset") {
		return nil, fmt.Errorf("unexpected SQL: %s", q)
	}
	c.capture.payload = args[0].Value.(string)
	return driver.RowsAffected(1), nil
}
func TestRestoreApprovalEnglishLegacyEvidence(t *testing.T) {
	for _, tc := range []struct {
		name, reason, source string
		rule                 any
	}{
		{"english", "[Model] Original 用户 evidence", "model", nil},
		{"legacy", "[模型] Original 用户 evidence", "model", nil},
		{"rule", "[Model] Original 用户 evidence", "rule", float64(7)},
		{"unknown", "Original 用户 evidence", "unknown", nil},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c := &restoreCapture{}
			d := sql.OpenDB(restoreConnector{c})
			defer d.Close()
			tx, err := d.Begin()
			if err != nil {
				t.Fatal(err)
			}
			defer tx.Rollback()
			row := map[string]any{"id": 42, "rule_id": tc.rule, "status": "allowed", "reason": tc.reason, "created_at": "2020-01-02T03:04:05Z", "decided_at": "2020-01-02T03:05:06Z"}
			raw, _ := json.Marshal([]any{row})
			if err := restoreInterceptRows(tx, raw); err != nil {
				t.Fatal(err)
			}
			var saved []map[string]any
			if err := json.Unmarshal([]byte(c.payload), &saved); err != nil {
				t.Fatal(err)
			}
			if len(saved) != 1 || saved[0]["decision_source"] != tc.source || saved[0]["reason"] != tc.reason || saved[0]["id"] != float64(42) || saved[0]["created_at"] != row["created_at"] || saved[0]["decided_at"] != row["decided_at"] {
				t.Fatalf("restore changed original evidence or source: %+v", saved)
			}
		})
	}
}
