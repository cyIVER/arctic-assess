// Package nativeexec redirects the real SDK CoreTool contract to a trusted executor.
// It is not a host sandbox; only the separately admitted container broker may execute effects.
package nativeexec

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/Autumn-27/norma/permission"
	"github.com/Autumn-27/norma/tool"
	"io"
	"regexp"
	"unicode/utf8"
)

type Binding struct {
	PhaseID                                      string
	Generation                                   int64
	TaskID, ExplorationID, IntentID              int64
	Role, SessionID, ExecutorID, NetworkPolicyID string
}
type Request struct {
	Binding   Binding
	Tool      string
	Input     json.RawMessage
	ToolUseID string
}
type Executor interface {
	Execute(context.Context, Request) (tool.Result, error)
}
type ResolveBinding func(context.Context) (Binding, error)
type wrapped struct {
	tool.CoreTool
	resolve  ResolveBinding
	executor Executor
}

func Wrap(t tool.CoreTool, r ResolveBinding, e Executor) tool.CoreTool { return &wrapped{t, r, e} }

var identifier = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`)

func validID(s string) bool { return identifier.MatchString(s) }
func (b Binding) Validate() error {
	if !validID(b.PhaseID) || b.Generation <= 0 || b.TaskID <= 0 || b.ExplorationID <= 0 || b.IntentID <= 0 || b.Role != "worker" || !validID(b.SessionID) || !validID(b.ExecutorID) || !validID(b.NetworkPolicyID) {
		return errors.New("invalid trusted worker binding")
	}
	return nil
}
func (w *wrapped) Call(ctx context.Context, in json.RawMessage, tc *tool.ToolContext) (tool.Result, error) {
	if w.CoreTool == nil || w.resolve == nil || w.executor == nil {
		return tool.Result{}, errors.New("isolated executor unavailable")
	}
	if err := Validate(ctx, w.CoreTool, in); err != nil {
		return tool.Result{}, err
	}
	if err := ctx.Err(); err != nil {
		return tool.Result{}, err
	}
	b, err := w.resolve(ctx)
	if err != nil {
		return tool.Result{}, err
	}
	if err = b.Validate(); err != nil {
		return tool.Result{}, err
	}
	id := ""
	if tc != nil {
		id = tc.ToolUseID
	}
	if len(id) > 128 || (!validID(id) && id != "") {
		return tool.Result{}, errors.New("invalid tool use ID")
	}
	return w.executor.Execute(ctx, Request{Binding: b, Tool: w.Name(), Input: append(json.RawMessage(nil), in...), ToolUseID: id})
}

// Six returns fresh actual pinned SDK constructors, never controller-specific tools.
func Six() []tool.CoreTool {
	return []tool.CoreTool{tool.NewRead(), tool.NewWrite(), tool.NewEdit(), tool.NewLS(), tool.NewBash(), tool.NewSleep()}
}
func Select(name string) (tool.CoreTool, error) {
	for _, t := range Six() {
		if t.Name() == name {
			return t, nil
		}
	}
	return nil, errors.New("unsupported core tool")
}

// Validate rechecks post-hook bytes: SDK schema, strict known primitive fields,
// duplicate/trailing JSON, background denial, and actual SDK hard-deny.
// This is NOT a command allowlist: arbitrary shell is allowed only in the isolated helper.
func Validate(ctx context.Context, t tool.CoreTool, in json.RawMessage) error {
	if len(in) == 0 || len(in) > 32768 || !utf8.Valid(in) {
		return errors.New("invalid input size or encoding")
	}
	if _, e := Select(t.Name()); e != nil {
		return e
	}
	d := json.NewDecoder(bytes.NewReader(in))
	tok, e := d.Token()
	if e != nil || tok != json.Delim('{') {
		return errors.New("input must be object")
	}
	props, _ := t.InputSchema()["properties"].(map[string]any)
	seen := map[string]bool{}
	for d.More() {
		k, e := d.Token()
		if e != nil {
			return errors.New("invalid input")
		}
		key, ok := k.(string)
		if !ok || seen[key] {
			return errors.New("duplicate input field")
		}
		seen[key] = true
		if _, ok = props[key]; !ok {
			return fmt.Errorf("unknown input field %q", key)
		}
		var v any
		if e = d.Decode(&v); e != nil {
			return errors.New("invalid input value")
		}
		switch v.(type) {
		case string, float64, bool:
		default:
			return errors.New("only primitive input fields allowed")
		}
		if key == "run_in_background" && v != false {
			return errors.New("background execution disabled")
		}
	}
	if _, e = d.Token(); e != nil {
		return errors.New("invalid object")
	}
	if _, e = d.Token(); e != io.EOF {
		return errors.New("trailing input")
	}
	if e = tool.ValidateInput(t.InputSchema(), in); e != nil {
		return e
	}
	// Norma's minimal required-property helper ignores []string (sleep's schema).
	if t.Name() == "sleep" && !seen["seconds"] {
		return errors.New("missing seconds")
	}
	if t.CheckPermissions(ctx, in, permission.Context{WorkingDir: "/work"}).Behavior == permission.Deny {
		return errors.New("core tool hard denied")
	}
	return nil
}
