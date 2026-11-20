package main

import (
	"bytes"
	"context"
	"encoding/json"
	"github.com/Autumn-27/artex/nativeexec"
	"os"
	"os/exec"
	"strings"
	"testing"
)

func TestRealSDKFileRoundtrip(t *testing.T) {
	dir := t.TempDir()
	ctx := context.Background()
	cases := []struct{ name, input, want string }{{"Write", `{"file_path":"note.txt","content":"literal alpha"}`, "Created"}, {"Read", `{"file_path":"note.txt"}`, "literal alpha"}, {"Edit", `{"file_path":"note.txt","old_string":"alpha","new_string":"beta"}`, "Edited"}, {"Read", `{"file_path":"note.txt"}`, "literal beta"}, {"LS", `{}`, "note.txt"}}
	for _, c := range cases {
		b, _ := json.Marshal(wireRequest{Version: 1, Tool: c.name, Input: json.RawMessage(c.input)})
		var out bytes.Buffer
		if e := serveTool(ctx, bytes.NewReader(b), &out, dir); e != nil {
			t.Fatal(e)
		}
		var r wireResponse
		if e := json.Unmarshal(out.Bytes(), &r); e != nil || r.Version != 1 || r.Error != "" || r.Result.IsError {
			t.Fatalf("%s %s %v", c.name, out.String(), e)
		}
		if !strings.Contains(r.Result.Content[0].Text, c.want) {
			t.Fatal(out.String())
		}
	}
}
func TestHelperRejectsUntrustedEnvelopeAndInput(t *testing.T) {
	for _, s := range []string{`{"version":1,"tool":"Bash","input":{"command":"true"},"env":["KEY=x"]}`, `{"version":1,"version":1,"tool":"LS","input":{}}`, `{"version":2,"tool":"LS","input":{}}`, `{"version":1,"tool":"Read","input":{"file_path":"x","file_path":"y"}}`, `{"version":1,"tool":"TaskList","input":{}}`} {
		var b bytes.Buffer
		if e := serveTool(context.Background(), strings.NewReader(s), &b, t.TempDir()); e == nil {
			t.Errorf("admitted %s", s)
		}
	}
}
func TestCredentialFreeEnvironment(t *testing.T) {
	if os.Getenv("ENV_TEST_CHILD") == "yes" {
		cleanEnvironment()
		for _, k := range []string{"CONTROLLER_CANARY", "BASH_ENV", "PGPASSWORD", "DOCKER_HOST", "ENV_TEST_CHILD"} {
			if os.Getenv(k) != "" {
				os.Exit(7)
			}
		}
		if os.Getenv("PATH") != "/usr/local/bin:/usr/bin:/bin" || os.Getenv("HOME") != "/tmp" {
			os.Exit(8)
		}
		os.Exit(0)
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCredentialFreeEnvironment$")
	cmd.Env = append(os.Environ(), "ENV_TEST_CHILD=yes", "CONTROLLER_CANARY=synthetic", "BASH_ENV=/forbidden", "PGPASSWORD=synthetic", "DOCKER_HOST=bad")
	if out, e := cmd.CombinedOutput(); e != nil {
		t.Fatalf("env: %s %v", out, e)
	}
}
func TestContextHasNoControllerState(t *testing.T) {
	tc := helperContext("/work", "id")
	if tc.WorkingDir != "/work" || tc.Tasks != nil || tc.Env != nil || tc.OutputDir != "" || tc.Emit != nil || tc.AgentID != "" || tc.MaxOutputChars <= 0 {
		t.Fatalf("unsafe context %+v", tc)
	}
	_ = nativeexec.Six()
}
