package server

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"github.com/Autumn-27/artex/db"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestNativePreflightProductionCLI(t *testing.T) {
	dsn := os.Getenv("ARTEX_TEST_PG_DSN")
	if dsn == "" {
		t.Fatal("approved private PG required")
	}
	admin, e := sql.Open("pgx", dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer admin.Close()
	name := fmt.Sprintf("native_preflight_%d", time.Now().UnixNano())
	if _, e = admin.Exec(`CREATE DATABASE ` + name); e != nil {
		t.Fatal(e)
	}
	defer func() {
		if _, e := admin.Exec(`DROP DATABASE ` + name + ` WITH (FORCE)`); e != nil {
			t.Error(e)
		}
	}()
	// Wrapper supplies a keyword DSN. Only replace its database name, never print it.
	parent := os.Getenv("ARTEX_PRIVATE_PARENT_DB")
	if parent == "" {
		parent = "artex_fixture"
	}
	fresh := strings.Replace(dsn, "dbname="+parent, "dbname="+name, 1)
	if fresh == dsn {
		t.Fatal("expected private wrapper database")
	}
	t.Setenv("ARTEX_PG_DSN", fresh)
	m, e := NewManager(t.TempDir(), "")
	if e != nil {
		t.Fatal(e)
	}
	defer m.Close()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	s := New(ctx, m, t.TempDir(), t.TempDir(), t.TempDir())
	s.archiveWG.Wait()
	<-s.side.done
	// Normal API accepts only the assessment goal and authorized base URL. No
	// intent/model proposal/discovery path is seeded, and no provider is installed.
	api := httptest.NewRequest("POST", "/api/tasks", strings.NewReader(`{"description":"Synthetic preflight bootstrap","goal":"Review the authorized local fixture http://owned-assessment-fixture:8080","seed_first_intent":false}`))
	w := httptest.NewRecorder()
	s.createTask(w, api)
	if w.Code != 201 {
		t.Fatalf("normal API creation: %d %s", w.Code, w.Body)
	}
	var created struct {
		ID string `json:"id"`
	}
	if e = json.Unmarshal(w.Body.Bytes(), &created); e != nil {
		t.Fatal(e)
	}
	task := s.m.ResolveTask(created.ID)
	tid, e := strconv.ParseInt(task.ID, 10, 64)
	if e != nil {
		t.Fatal(e)
	}
	if e = s.m.SetTaskStatus(task.ID, "running"); e != nil {
		t.Fatal(e)
	}
	for _, kind := range []string{"intent", "finding"} {
		nodes, e := task.Store.ListByKind(kind, 100)
		if e != nil || len(nodes) != 0 {
			t.Fatalf("bootstrap seeded %s: %d %v", kind, len(nodes), e)
		}
	}
	t.Run("native_admission_route", func(t *testing.T) {
		token, err := signJWT(s.jwtKey)
		if err != nil {
			t.Fatal(err)
		}
		live := httptest.NewServer(s.Handler())
		defer live.Close()
		for _, authorized := range []bool{false, true} {
			req, err := http.NewRequest("GET", live.URL+"/api/tasks/"+task.ID+"/native-admission", nil)
			if err != nil {
				t.Fatal(err)
			}
			if authorized {
				req.Header.Set("Authorization", "Bearer "+token)
			}
			response, err := live.Client().Do(req)
			if err != nil {
				t.Fatal(err)
			}
			response.Body.Close()
			want := 401
			if authorized {
				want = 503
			}
			if response.StatusCode != want {
				t.Fatalf("auth=%v code=%d want=%d", authorized, response.StatusCode, want)
			}
		}
	})
	if os.Getenv("ARTEX_STATUS_TRACE_ONLY") == "1" {
		return
	} // test harness only; never compiled into application
	binary := filepath.Join(t.TempDir(), "catalog")
	build := exec.Command(os.Getenv("GOROOT")+"/bin/go", "build", "-o", binary, "../cmd/artex-native-preflight")
	if out, e := build.CombinedOutput(); e != nil {
		t.Fatalf("standard production CLI build: %v %s", e, out)
	}
	// Positive syscall-spy control: demonstrate a synthetic secret open is visible.
	canary := filepath.Join(t.TempDir(), "service.key")
	if e = os.WriteFile(canary, []byte("synthetic-preflight-open-control"), 0600); e != nil {
		t.Fatal(e)
	}
	controlTrace := filepath.Join(t.TempDir(), "control.trace")
	control := exec.Command("/usr/bin/strace", "-qq", "-e", "trace=openat", "-o", controlTrace, "/bin/cat", canary)
	if _, e = control.Output(); e != nil {
		t.Fatal(e)
	}
	ct, e := os.ReadFile(controlTrace)
	if e != nil || !bytes.Contains(ct, []byte(canary)) {
		t.Fatal("secret-open spy positive control failed")
	}
	ro, e := db.OpenReadOnlyCatalog(t.Context(), fresh)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = ro.Exec(`UPDATE agents SET enabled=enabled`); e == nil || !strings.Contains(e.Error(), "read-only") {
		t.Fatalf("PG did not enforce read-only: %v", e)
	}
	ro.Close()
	input := map[string]any{"task_id": tid, "exploration_id": task.ExpID, "executor_id": "synthetic-executor", "network_policy_id": "synthetic-get-head", "fixture_origin": "http://owned-assessment-fixture:8080", "expected_global": map[string]string{"format": "codex-native", "model": "gpt-6.1-sol", "endpoint": "http://127.0.0.1:19999/artex/native/v1/complete"}}
	raw, _ := json.Marshal(input)
	sourceProvider := "codex-native"
	run := func() ([]byte, error) {
		ctx, cancel := context.WithTimeout(t.Context(), 30*time.Second)
		defer cancel()
		trace := filepath.Join(t.TempDir(), "catalog.trace")
		cmd := exec.CommandContext(ctx, "/usr/bin/strace", "-f", "-qq", "-e", "trace=openat,connect", "-o", trace, binary)
		cmd.Env = append(os.Environ(), "ARTEX_LLM_PROVIDER="+sourceProvider, "ARTEX_LLM_MODEL=gpt-6.1-sol", "ARTEX_LLM_BASE_URL=http://127.0.0.1:19999/artex/native/v1/complete")
		cmd.Stdin = bytes.NewReader(raw)
		var stderr bytes.Buffer
		cmd.Stderr = &stderr
		out, e := cmd.Output()
		traced, te := os.ReadFile(trace)
		if dest := os.Getenv("ARTEX_PREFLIGHT_RECEIPTS"); dest != "" && te == nil {
			if err := os.WriteFile(filepath.Join(dest, fmt.Sprintf("catalog-syscalls-%d.trace", time.Now().UnixNano())), traced, 0600); err != nil {
				t.Fatal(err)
			}
		}
		if te != nil {
			t.Fatal(te)
		}
		for _, forbidden := range []string{"service.key", "executor.key", "/run/artex-native", "AF_INET", "AF_INET6"} {
			if bytes.Contains(traced, []byte(forbidden)) {
				t.Fatalf("preflight forbidden syscall %s: %s", forbidden, traced)
			}
		}
		if e == nil && !bytes.Contains(traced, []byte("AF_UNIX")) {
			t.Fatal("preflight never reached real PG")
		}
		if e != nil {
			return stderr.Bytes(), e
		}
		return out, nil
	}
	out, e := run()
	if e != nil {
		t.Fatalf("production CLI must derive all five normal DB-bound catalogs: %v %s", e, out)
	}
	var got struct {
		Roles []struct {
			Role    string            `json:"role"`
			Catalog string            `json:"catalog_sha256"`
			Tools   []json.RawMessage `json:"tools"`
		} `json:"roles"`
		ReadOnly bool `json:"read_only"`
	}
	if e = json.Unmarshal(out, &got); e != nil || len(got.Roles) != 5 || !got.ReadOnly {
		t.Fatalf("invalid preflight: %v %s", e, out)
	}
	for _, r := range got.Roles {
		if len(r.Catalog) != 64 || len(r.Tools) == 0 {
			t.Fatalf("empty %s", r.Role)
		}
	}
	t.Logf("PREFLIGHT %s", out)
	t.Run("global_default_keyed_overrides_env", func(t *testing.T) {
		id, err := s.m.pg.SaveProfile(&db.LLMProfile{Name: "global-source-canary", Format: "openai", Model: "synthetic", APIKey: "synthetic-global-secret-canary"})
		if err != nil {
			t.Fatal(err)
		}
		defer s.m.pg.Exec(`DELETE FROM llm_profiles WHERE id=$1`, id)
		if _, err = s.m.pg.Exec(`UPDATE llm_profiles SET is_default=(id=$1)`, id); err != nil {
			t.Fatal(err)
		}
		output, err := run()
		if bytes.Contains(output, []byte("synthetic-global-secret-canary")) {
			t.Fatal("secret projected")
		}
		if err == nil {
			t.Fatal("keyed DB global falsely qualified native ENV")
		}
		if _, err = s.m.pg.Exec(`UPDATE llm_profiles SET is_default=false WHERE id=$1`, id); err != nil {
			t.Fatal(err)
		}
		if output, err = run(); err != nil {
			t.Fatalf("inactive keyed profile must not override ENV: %v %s", err, output)
		}
		if _, err = s.m.pg.Exec(`UPDATE llm_profiles SET is_default=true,api_key='' WHERE id=$1`, id); err != nil {
			t.Fatal(err)
		}
		if output, err = run(); err != nil {
			t.Fatalf("keyless default must fall back to ENV: %v %s", err, output)
		}
	})
	t.Run("global_source_query_error", func(t *testing.T) {
		if _, err := s.m.pg.Exec(`ALTER TABLE llm_profiles RENAME TO hidden_global_profiles`); err != nil {
			t.Fatal(err)
		}
		defer s.m.pg.Exec(`ALTER TABLE hidden_global_profiles RENAME TO llm_profiles`)
		if output, err := run(); err == nil {
			t.Fatalf("global source query error admitted: %s", output)
		}
	})
	t.Run("missing_global_configuration", func(t *testing.T) {
		sourceProvider = ""
		defer func() { sourceProvider = "codex-native" }()
		if output, e := run(); e == nil {
			t.Fatalf("missing global config admitted: %s", output)
		}
	})

	t.Run("sql_description_override", func(t *testing.T) {
		old, e := s.m.pg.GetTool("set_goals")
		if e != nil {
			t.Fatal(e)
		}
		s.m.pg.Exec(`UPDATE tools SET description='SQL-owned preflight override' WHERE key='set_goals'`)
		defer s.m.pg.Exec(`UPDATE tools SET description=$1 WHERE key='set_goals'`, old.Description)
		changed, e := run()
		if e != nil || !bytes.Contains(changed, []byte("SQL-owned preflight override")) {
			t.Fatalf("normal binding metadata not applied: %v %s", e, changed)
		}
	})
	t.Run("explicit_role_profile_denies_without_secret_read", func(t *testing.T) {
		profile, e := s.m.pg.SaveProfile(&db.LLMProfile{Name: "preflight-canary", Format: "openai", Model: "synthetic", APIKey: "synthetic-profile-secret-canary"})
		if e != nil {
			t.Fatal(e)
		}
		defer s.m.pg.DeleteProfile(profile)
		s.m.pg.SetAgentLLMProfile("worker", &profile)
		defer s.m.pg.SetAgentLLMProfile("worker", nil)
		if output, e := run(); e == nil || bytes.Contains(output, []byte("synthetic-profile-secret-canary")) {
			t.Fatalf("explicit source override leaked/admitted: %v %s", e, output)
		}
	})
	t.Run("expected_config_mismatch", func(t *testing.T) {
		saved := raw
		defer func() { raw = saved }()
		raw = bytes.Replace(raw, []byte("gpt-6.1-sol"), []byte("wrong-model"), 1)
		if out, e := run(); e == nil {
			t.Fatalf("expected config mismatch admitted: %s", out)
		}
	})
	t.Run("row_query_error", func(t *testing.T) {
		s.m.pg.Exec(`ALTER TABLE tools RENAME TO preflight_hidden_tools`)
		defer s.m.pg.Exec(`ALTER TABLE preflight_hidden_tools RENAME TO tools`)
		if out, e := run(); e == nil {
			t.Fatalf("row error admitted: %s", out)
		}
	})
	t.Run("missing_role_row", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE agents SET key='preflight_hidden_goals' WHERE key='goals'`)
		defer s.m.pg.Exec(`UPDATE agents SET key='goals' WHERE key='preflight_hidden_goals'`)
		if out, e := run(); e == nil {
			t.Fatalf("missing row admitted: %s", out)
		}
	})
	t.Run("paused", func(t *testing.T) {
		s.m.pg.SetPaused(tid, true)
		defer s.m.pg.SetPaused(tid, false)
		if out, e := run(); e == nil {
			t.Fatalf("paused admitted: %s", out)
		}
	})
	t.Run("disabled_role", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE agents SET enabled=false WHERE key='reporter'`)
		defer s.m.pg.Exec(`UPDATE agents SET enabled=true WHERE key='reporter'`)
		if out, e := run(); e == nil {
			t.Fatalf("disabled admitted: %s", out)
		}
	})
	t.Run("missing_binding", func(t *testing.T) {
		s.m.pg.Exec(`UPDATE tools SET enabled=false WHERE key='set_goals'`)
		defer s.m.pg.Exec(`UPDATE tools SET enabled=true WHERE key='set_goals'`)
		if out, e := run(); e == nil {
			t.Fatalf("binding admitted: %s", out)
		}
	})
}
