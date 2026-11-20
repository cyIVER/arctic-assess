package intercept

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"testing"

	"github.com/Autumn-27/artex/db"
)

// The SQL seam is synthetic: these tests exercise production entrypoints, not PostgreSQL.
type englishConnector struct{}
type englishDriver struct{}
type englishConn struct{}
type englishRows struct{ values [][]driver.Value }

func (englishConnector) Connect(context.Context) (driver.Conn, error) { return englishConn{}, nil }
func (englishConnector) Driver() driver.Driver                        { return englishDriver{} }
func (englishDriver) Open(string) (driver.Conn, error)                { return englishConn{}, nil }
func (englishConn) Prepare(string) (driver.Stmt, error)               { return nil, fmt.Errorf("unexpected prepare") }
func (englishConn) Close() error                                      { return nil }
func (englishConn) Begin() (driver.Tx, error)                         { return nil, fmt.Errorf("unexpected transaction") }
func (englishRows) Columns() []string                                 { return []string{"value"} }
func (englishRows) Close() error                                      { return nil }
func (r *englishRows) Next(dst []driver.Value) error {
	if len(r.values) == 0 {
		return io.EOF
	}
	copy(dst, r.values[0])
	r.values = r.values[1:]
	return nil
}
func (englishConn) QueryContext(_ context.Context, q string, args []driver.NamedValue) (driver.Rows, error) {
	if strings.Contains(q, "FROM settings") {
		if args[0].Value == "llm_judge_enabled" {
			return &englishRows{values: [][]driver.Value{{"true"}}}, nil
		}
		return &englishRows{}, nil
	}
	if strings.Contains(q, "INSERT INTO intercept_pending") {
		return &englishRows{values: [][]driver.Value{{int64(42)}}}, nil
	}
	if strings.Contains(q, "FROM intercept_pending") {
		return &englishRows{}, nil
	}
	return nil, fmt.Errorf("unexpected query: %s", q)
}
func (englishConn) ExecContext(context.Context, string, []driver.NamedValue) (driver.Result, error) {
	return driver.RowsAffected(1), nil
}
func englishInterceptor(t *testing.T) *Interceptor {
	t.Helper()
	d := sql.OpenDB(englishConnector{})
	t.Cleanup(func() { d.Close() })
	return New(&db.DB{DB: d})
}

func TestEnglishJudgeGeneratedReason(t *testing.T) {
	for _, action := range []string{"allow", "ask", "deny"} {
		t.Run(action, func(t *testing.T) {
			i := englishInterceptor(t)
			calls := 0
			i.SetReviewer(func(context.Context, int64, string, ReviewInput) (Decision, error) {
				calls++
				return Decision{Action: action}, nil
			})
			got, ok := i.Judge(t.Context(), "Read", json.RawMessage(`{}`))
			labels := map[string]string{"allow": "Allowed", "ask": "Requires human approval", "deny": "Blocked"}
			if !ok || calls != 1 || got.Action != action || got.Message != "[Model] "+labels[action] {
				t.Fatalf("verdict=%+v enabled=%v calls=%d", got, ok, calls)
			}
			if action == "ask" && (!got.TimeoutEnabled || got.TimeoutAction != "deny" || got.TimeoutSeconds != 300) {
				t.Fatalf("approval timeout changed: %+v", got)
			}
		})
	}
}
func TestEnglishHandleAskSummaryAndCancellation(t *testing.T) {
	i := englishInterceptor(t)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	var emitted []db.Activity
	ctx = WithTaskContext(ctx, "synthetic-task", "worker", func(a db.Activity) { emitted = append(emitted, a); cancel() })
	if i.HandleAsk(ctx, 0, Decision{Action: "ask"}, "Bash", []byte(`{"command":"echo evidence"}`)) {
		t.Fatal("cancelled approval allowed execution")
	}
	if len(emitted) != 1 || emitted[0].Summary != "Tool Bash requests approval (#42)" {
		t.Fatalf("activities=%+v", emitted)
	}
	var detail map[string]json.RawMessage
	if json.Unmarshal([]byte(emitted[0].Detail), &detail) != nil || string(detail["input"]) != `{"command":"echo evidence"}` {
		t.Fatalf("input evidence changed: %+v", emitted)
	}
}
func TestEnglishVerdictCompatibility(t *testing.T) {
	for _, reason := range []string{"Actual operation: Read file; Consequence on success: Return content; Matched rule: A5", "实际操作：读取文件；成功后的后果：返回内容；命中规则：A5"} {
		t.Run(reason, func(t *testing.T) {
			raw, _ := json.Marshal(map[string]string{"decision": "allow", "comment": reason})
			got := ParseVerdict(string(raw))
			if got.Action != "allow" || got.Reason != reason {
				t.Fatalf("lost valid explanation: %+v", got)
			}
		})
	}
	for _, reason := range []string{"Actual operation: ; Consequence on success: Return; Matched rule: A5", "Actual operation: Read; Consequence on success: ; Matched rule: A5", "Actual operation: Read; Consequence on success: Return; Matched rule: ", "allow"} {
		raw, _ := json.Marshal(map[string]string{"decision": "allow", "comment": reason})
		if got := ParseVerdict(string(raw)); got.Action != "" {
			t.Fatalf("accepted incomplete explanation: %+v", got)
		}
	}
}
