package nativeexec

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"github.com/Autumn-27/norma/llm"
	"github.com/Autumn-27/norma/tool"
	"io"
	"net"
	"path/filepath"
	"time"
)

// Client holds trusted control-plane configuration, never model-selected settings.
// Its key is NOT passed to helper or fixture socket. Provisioning stays host-side.
type Client struct {
	path string
	key  []byte
}

func NewClient(path string, key []byte) (*Client, error) {
	if !filepath.IsAbs(path) || len(key) != 32 {
		return nil, errors.New("invalid executor control configuration")
	}
	return &Client{path, append([]byte(nil), key...)}, nil
}
func (c *Client) Execute(ctx context.Context, r Request) (tool.Result, error) {
	fail := func() (tool.Result, error) {
		return tool.Result{}, errors.New("isolated executor unavailable or rejected")
	}
	if e := r.Binding.Validate(); e != nil {
		return fail()
	}
	t, e := Select(r.Tool)
	if e != nil {
		return fail()
	}
	if e = Validate(ctx, t, r.Input); e != nil {
		return fail()
	}
	payload, e := json.Marshal(r)
	if e != nil || len(payload) > 65504 {
		return fail()
	}
	conn, e := (&net.Dialer{Timeout: time.Second}).DialContext(ctx, "unix", c.path)
	if e != nil {
		return fail()
	}
	defer conn.Close()
	deadline := time.Now().Add(20 * time.Second)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	_ = conn.SetDeadline(deadline)
	finished := make(chan struct{})
	defer close(finished)
	go func() {
		select {
		case <-ctx.Done():
			conn.Close()
		case <-finished:
		}
	}()
	mac := hmac.New(sha256.New, c.key)
	mac.Write(payload)
	frame := append(mac.Sum(nil), payload...)
	var b bytes.Buffer
	_ = binary.Write(&b, binary.BigEndian, uint32(len(frame)))
	b.Write(frame)
	if _, e = io.Copy(conn, &b); e != nil {
		return fail()
	}
	var n uint32
	if e = binary.Read(conn, binary.BigEndian, &n); e != nil || n == 0 || n > 65536 {
		return fail()
	}
	raw := make([]byte, n)
	if _, e = io.ReadFull(conn, raw); e != nil {
		return fail()
	}
	if e = strictResponseJSON(raw); e != nil {
		return fail()
	}
	var envelope map[string]json.RawMessage
	if json.Unmarshal(raw, &envelope) != nil || len(envelope) != 2 || envelope["version"] == nil || envelope["result"] == nil {
		return fail()
	}
	var resultFields map[string]json.RawMessage
	if json.Unmarshal(envelope["result"], &resultFields) != nil || len(resultFields) != 2 || resultFields["Content"] == nil || resultFields["IsError"] == nil || bytes.Equal(resultFields["Content"], []byte("null")) {
		return fail()
	}
	var response struct {
		Version int `json:"version"`
		Result  struct {
			Content []llm.ContentBlock
			IsError bool
		} `json:"result"`
		Error string `json:"error"`
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if e = d.Decode(&response); e != nil || response.Version != 1 || response.Error != "" || len(response.Result.Content) > 64 {
		return fail()
	}
	for _, v := range response.Result.Content {
		if v.Type != llm.BlockText || v.Thinking != "" || v.Signature != "" || v.ID != "" || v.Name != "" || len(v.Input) > 0 || v.ToolUseID != "" || len(v.Content) > 0 || v.IsError {
			return fail()
		}
	}
	if e = ctx.Err(); e != nil {
		return fail()
	}
	return tool.Result{Content: response.Result.Content, IsError: response.Result.IsError}, nil
}
func strictResponseJSON(raw []byte) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	var walk func(int) error
	walk = func(depth int) error {
		if depth > 8 {
			return errors.New("depth")
		}
		tok, e := d.Token()
		if e != nil {
			return e
		}
		if delim, ok := tok.(json.Delim); ok {
			switch delim {
			case '{':
				seen := map[string]bool{}
				for d.More() {
					key, e := d.Token()
					if e != nil {
						return e
					}
					s, ok := key.(string)
					if !ok || seen[s] {
						return errors.New("duplicate")
					}
					seen[s] = true
					if e = walk(depth + 1); e != nil {
						return e
					}
				}
				_, e = d.Token()
				return e
			case '[':
				for d.More() {
					if e = walk(depth + 1); e != nil {
						return e
					}
				}
				_, e = d.Token()
				return e
			default:
				return errors.New("delimiter")
			}
		}
		return nil
	}
	if e := walk(0); e != nil {
		return e
	}
	if _, e := d.Token(); e != io.EOF {
		return errors.New("trailing")
	}
	return nil
}
