package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestH2ActualSDKRoundtripAndSourceReplacements(t *testing.T) {
	for _, replace := range []string{"none", "work", "fixture"} {
		t.Run(replace, func(t *testing.T) {
			dir, e := os.MkdirTemp("", "h2-")
			if e != nil {
				t.Fatal(e)
			}
			defer os.RemoveAll(dir)
			work, fixture := filepath.Join(dir, "work"), filepath.Join(dir, "fixture")
			for _, p := range []string{work, fixture} {
				if e = os.Mkdir(p, 0700); e != nil {
					t.Fatal(e)
				}
			}
			listen, e := net.Listen("unix", filepath.Join(fixture, "gateway.sock"))
			if e != nil {
				t.Fatal(e)
			}
			defer listen.Close()
			if e = os.Chmod(filepath.Join(fixture, "gateway.sock"), 0600); e != nil {
				t.Fatal(e)
			}
			// Preserve the expected objects as actual held descriptors, not re-lstat paths.
			wf, wantWork, e := openMounted(work, false)
			if e != nil {
				t.Fatal(e)
			}
			defer wf.Close()
			ff, wantFixture, e := openMounted(fixture, false)
			if e != nil {
				t.Fatal(e)
			}
			defer ff.Close()
			if replace != "none" {
				p := work
				if replace == "fixture" {
					p = fixture
				}
				if e = os.Rename(p, p+".held"); e != nil {
					t.Fatal(e)
				}
				if e = os.Mkdir(p, 0700); e != nil {
					t.Fatal(e)
				}
				if replace == "fixture" {
					newer, e := net.Listen("unix", filepath.Join(fixture, "gateway.sock"))
					if e != nil {
						t.Fatal(e)
					}
					defer newer.Close()
				}
			}
			requestReader, requestWriter := io.Pipe()
			responseReader, responseWriter := io.Pipe()
			defer requestReader.Close()
			defer requestWriter.Close()
			defer responseReader.Close()
			defer responseWriter.Close()
			settled := make(chan error, 1)
			go func() {
				reader, closeFiles, e := attest(context.Background(), requestReader, responseWriter, work, fixture)
				if e == nil {
					defer closeFiles()
					e = serveTool(context.Background(), reader, responseWriter, work)
				}
				responseWriter.Close()
				settled <- e
			}()
			nonce := strings.Repeat("a", 64)
			if e = json.NewEncoder(requestWriter).Encode(map[string]any{"version": 2, "nonce": nonce}); e != nil {
				t.Fatal(e)
			}
			dec := json.NewDecoder(responseReader)
			var hello mountHello
			if e = dec.Decode(&hello); e != nil {
				t.Fatal(e)
			}
			matches := hello.Version == 2 && hello.Nonce == nonce && hello.Work == wantWork && hello.Fixture == wantFixture
			if replace == "none" {
				if !matches {
					t.Fatalf("positive object mismatch: %+v", hello)
				}
				if e = json.NewEncoder(requestWriter).Encode(map[string]any{"version": 2, "ack": nonce}); e != nil {
					t.Fatal(e)
				}
				if _, e = io.WriteString(requestWriter, `{"version":1,"tool":"Write","input":{"file_path":"public.txt","content":"owned-public-literal"}}`); e != nil {
					t.Fatal(e)
				}
				requestWriter.Close()
				var result wireResponse
				if e = dec.Decode(&result); e != nil {
					t.Fatal(e)
				}
				if result.Version != 1 || result.Error != "" || result.Result.IsError {
					t.Fatalf("bad SDK result %+v", result)
				}
				actual, e := os.ReadFile(filepath.Join(work, "public.txt"))
				if e != nil || string(actual) != "owned-public-literal" {
					t.Fatalf("SDK effect absent %v", e)
				}
			} else {
				if matches {
					t.Fatal("replacement attested as original")
				}
				// The host withholds BOTH ACK and ALL v1 Input on an actual identity mismatch.
				requestWriter.Close()
				if _, e = os.Stat(filepath.Join(work, "public.txt")); !os.IsNotExist(e) {
					t.Fatal("input/effect before verified ACK")
				}
			}
			select {
			case e = <-settled:
				if (replace == "none") != (e == nil) {
					t.Fatalf("unexpected settle %v", e)
				}
			case <-time.After(time.Second):
				t.Fatal("helper failed to settle")
			}
		})
	}
}

func TestH2MalformedAckNeverExecutesTool(t *testing.T) {
	for _, ack := range []string{`{"version":2,"ack":"wrong"}`, `{"version":2,"ack":"` + strings.Repeat("b", 64) + `"}`, `{"version":2,"version":2,"ack":"` + strings.Repeat("a", 64) + `"}`, `{"version":2,"ack":"` + strings.Repeat("a", 64) + `","extra":true}`} {
		t.Run(ack, func(t *testing.T) {
			dir, e := os.MkdirTemp("", "h2-")
			if e != nil {
				t.Fatal(e)
			}
			defer os.RemoveAll(dir)
			work, fixture := filepath.Join(dir, "work"), filepath.Join(dir, "fixture")
			for _, p := range []string{work, fixture} {
				if e = os.Mkdir(p, 0700); e != nil {
					t.Fatal(e)
				}
			}
			listener, e := net.Listen("unix", filepath.Join(fixture, "gateway.sock"))
			if e != nil {
				t.Fatal(e)
			}
			defer listener.Close()
			data := `{"version":2,"nonce":"` + strings.Repeat("a", 64) + `"}` + "\n" + ack + "\n" + `{"version":1,"tool":"Write","input":{"file_path":"public.txt","content":"owned-public-literal"}}`
			var out bytes.Buffer
			reader, closeFiles, e := attest(context.Background(), strings.NewReader(data), &out, work, fixture)
			if e == nil {
				defer closeFiles()
				_ = serveTool(context.Background(), reader, &out, work)
				t.Fatal("invalid ACK accepted")
			}
			if _, e = os.Stat(filepath.Join(work, "public.txt")); !os.IsNotExist(e) {
				t.Fatal("invalid ACK caused effect")
			}
		})
	}
}

func TestProductionServeRefusesHandshakelessToolBeforeEffect(t *testing.T) {
	dir := t.TempDir()
	var out bytes.Buffer
	payload := `{"version":1,"tool":"Write","input":{"file_path":"forbidden.txt","content":"owned-public-literal"}}`
	err := serve(context.Background(), bytes.NewBufferString(payload), &out, dir)
	if err == nil {
		t.Fatal("handshakeless tool admitted")
	}
	if _, err := os.Stat(filepath.Join(dir, "forbidden.txt")); !os.IsNotExist(err) {
		t.Fatal("tool executed before trusted mount ACK")
	}
}
