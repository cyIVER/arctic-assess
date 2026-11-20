package nativeexec

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"io"
	"net"
	"path/filepath"
	"testing"
	"time"
)

func TestClientAuthenticatedUDSTypedResult(t *testing.T) {
	path := filepath.Join(t.TempDir(), "control.sock")
	l, e := net.Listen("unix", path)
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	key := []byte("12345678901234567890123456789012")
	done := make(chan error, 1)
	go func() {
		c, e := l.Accept()
		if e != nil {
			done <- e
			return
		}
		defer c.Close()
		var n uint32
		if e = binary.Read(c, binary.BigEndian, &n); e != nil {
			done <- e
			return
		}
		b := make([]byte, n)
		_, e = io.ReadFull(c, b)
		if e == nil {
			m := hmac.New(sha256.New, key)
			m.Write(b[32:])
			if !hmac.Equal(m.Sum(nil), b[:32]) {
				t.Error("bad MAC")
			}
			var r Request
			if json.Unmarshal(b[32:], &r) != nil || r.Binding.IntentID != 3 {
				t.Error("bad binding")
			}
			out := []byte(`{"version":1,"result":{"Content":[{"type":"text","text":"real wire"}],"IsError":false}}`)
			binary.Write(c, binary.BigEndian, uint32(len(out)))
			_, e = c.Write(out)
		}
		done <- e
	}()
	client, e := NewClient(path, key)
	if e != nil {
		t.Fatal(e)
	}
	b, _ := binding(context.Background())
	r, e := client.Execute(context.Background(), Request{Binding: b, Tool: "LS", Input: json.RawMessage(`{}`)})
	if e != nil || r.Flatten() != "real wire" || len(r.Extra) != 0 {
		t.Fatalf("%+v %v", r, e)
	}
	if e = <-done; e != nil {
		t.Fatal(e)
	}
}
func TestRejectMalformedResultEnvelope(t *testing.T) {
	for _, raw := range []string{`{"version":1}`, `{"version":1,"result":{"Content":[],"IsError":false,"Extra":[]}}`, `{"version":1,"result":{"Content":[{"type":"tool_use","id":"authority"}],"IsError":false}}`, `{"version":1,"version":1,"result":{"Content":[],"IsError":false}}`} {
		path := filepath.Join(t.TempDir(), "c.sock")
		l, e := net.Listen("unix", path)
		if e != nil {
			t.Fatal(e)
		}
		go func() {
			c, e := l.Accept()
			if e != nil {
				return
			}
			defer c.Close()
			var n uint32
			binary.Read(c, binary.BigEndian, &n)
			io.CopyN(io.Discard, c, int64(n))
			binary.Write(c, binary.BigEndian, uint32(len(raw)))
			c.Write([]byte(raw))
		}()
		c, _ := NewClient(path, make([]byte, 32))
		b, _ := binding(context.Background())
		if _, e = c.Execute(context.Background(), Request{Binding: b, Tool: "LS", Input: json.RawMessage(`{}`)}); e == nil {
			t.Errorf("admitted %s", raw)
		}
		l.Close()
	}
}
func TestClientCancelNoHostFallback(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing.sock")
	c, e := NewClient(path, make([]byte, 32))
	if e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Millisecond)
	defer cancel()
	b, _ := binding(ctx)
	if _, e = c.Execute(ctx, Request{Binding: b, Tool: "LS", Input: json.RawMessage(`{}`)}); e == nil {
		t.Fatal("missing broker admitted")
	}
}
