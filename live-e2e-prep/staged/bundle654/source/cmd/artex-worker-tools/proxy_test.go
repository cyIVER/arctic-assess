package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Execute the immutable host gateway's actual parser, allowlist, policy and
// reconstruction. Only its upstream socket is replaced: no target is dialed.
const gatewayValidation = `
import sys,json,time,socket
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
from hostbroker.gateway import Gateway,Budget,Denied
class Wire:
 def __init__(self,b): self.b=b; self.sent=b''
 def settimeout(self,t): pass
 def recv(self,n): b,self.b=self.b[:n],self.b[n:]; return b
 def send(self,b): self.sent+=bytes(b); return len(b)
 def connect(self,a): assert a==('127.0.0.1',18081)
 def getpeername(self): return ('127.0.0.1',18081)
 def __enter__(self): return self
 def __exit__(self,*a): pass
raw=sys.stdin.buffer.read()
g=Gateway('unused','http://127.0.0.1:18081','127.0.0.1',Budget(),peer_uid=0)
u=Wire(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok')
socket.socket=lambda *a,**kw:u
try:
 result=g._exchange(Wire(raw),time.monotonic()+2)
 print(json.dumps(dict(status=200,upstream=u.sent.decode(),reason='')))
except Denied as e:
 print(json.dumps(dict(status=502,upstream=u.sent.decode(),reason=str(e))))
`

type gatewayResult struct {
	Status           int
	Upstream, Reason string
}

func validateGateway(t *testing.T, raw []byte) gatewayResult {
	t.Helper()
	host, err := filepath.Abs("../../../../artex-worker-isolation/host")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/usr/bin/python3", "-B", "-c", gatewayValidation, host)
	cmd.Env = []string{"PATH=/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE=1"}
	cmd.Stdin = bytes.NewReader(raw)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("gateway validation: %v %s", err, out)
	}
	var result gatewayResult
	if err = json.Unmarshal(out, &result); err != nil {
		t.Fatalf("gateway result: %v %s", err, out)
	}
	return result
}

type gatewayTransport struct {
	t      *testing.T
	raw    string
	result gatewayResult
	uri    string
	host   string
	method string
}

func (g *gatewayTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	g.uri = r.RequestURI
	g.host = r.Host
	g.method = r.Method
	var b bytes.Buffer
	// Match production Transport: close per exchange, then serialize origin-form.
	r = r.Clone(r.Context())
	r.Close = true
	if err := r.Write(&b); err != nil {
		return nil, err
	}
	g.raw = b.String()
	g.result = validateGateway(g.t, b.Bytes())
	return &http.Response{StatusCode: g.result.Status, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(http.StatusText(g.result.Status)))}, nil
}

func TestProxyOwnedOriginGETHEAD(t *testing.T) {
	for _, method := range []string{"GET", "HEAD"} {
		t.Run(method, func(t *testing.T) {
			tr := &gatewayTransport{t: t}
			req := httptest.NewRequest(method, "http://127.0.0.1:18081/owned?q=one%20two", nil)
			req.RemoteAddr = "192.0.2.10:1234"
			w := httptest.NewRecorder()
			proxyHandler(tr).ServeHTTP(w, req)
			if w.Code != 200 {
				t.Fatalf("production handler denied %s: status=%d reason=%s wire=%q", method, w.Code, tr.result.Reason, tr.raw)
			}
			if tr.uri != req.RequestURI || tr.host != "127.0.0.1:18081" || tr.method != method {
				t.Fatalf("outgoing URI/Host/method: %q %q %q", tr.uri, tr.host, tr.method)
			}
			want := fmt.Sprintf("%s /owned?q=one%%20two HTTP/1.1\r\nHost: 127.0.0.1:18081\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n", method)
			if tr.result.Upstream != want {
				t.Fatalf("unexpected reconstructed authority/path: %q", tr.result.Upstream)
			}
			for _, h := range []string{"X-Forwarded-For:", "Forwarded:", "X-Real-Ip:"} {
				if strings.Contains(tr.raw, h) {
					t.Fatalf("forwarding header %s", h)
				}
			}
		})
	}
}

func TestProxyUntrustedRequests(t *testing.T) {
	cases := []struct {
		name, method, target, header, value string
		want                                int
	}{
		{"forwarded", "GET", "http://127.0.0.1:18081/", "Forwarded", "for=SYNTHETIC_CANARY", 200},
		{"xff", "GET", "http://127.0.0.1:18081/", "X-Forwarded-For", "SYNTHETIC_CANARY", 200},
		{"xfhost", "GET", "http://127.0.0.1:18081/", "X-Forwarded-Host", "SYNTHETIC_CANARY", 200},
		{"xfproto", "GET", "http://127.0.0.1:18081/", "X-Forwarded-Proto", "SYNTHETIC_CANARY", 200},
		{"realip", "GET", "http://127.0.0.1:18081/", "X-Real-IP", "SYNTHETIC_CANARY", 200},
		{"auth", "GET", "http://127.0.0.1:18081/", "Authorization", "Bearer SYNTHETIC_CANARY", 502},
		{"cookie", "GET", "http://127.0.0.1:18081/", "Cookie", "session=SYNTHETIC_CANARY", 502},
		{"key", "GET", "http://127.0.0.1:18081/", "X-Api-Key", "SYNTHETIC_CANARY", 502},
		{"offorigin", "GET", "http://off-origin.invalid/", "", "", 502},
		{"post", "POST", "http://127.0.0.1:18081/", "", "", 502},
		{"connect", "CONNECT", "http://127.0.0.1:18081/", "", "", 502},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			tr := &gatewayTransport{t: t}
			req := httptest.NewRequest(c.method, c.target, nil)
			if c.header != "" {
				req.Header.Set(c.header, c.value)
			}
			w := httptest.NewRecorder()
			proxyHandler(tr).ServeHTTP(w, req)
			if w.Code != c.want {
				t.Fatalf("status=%d want=%d reason=%s wire=%q", w.Code, c.want, tr.result.Reason, tr.raw)
			}
			if c.want == 502 && tr.result.Upstream != "" {
				t.Fatalf("denied request reached origin: %q", tr.result.Upstream)
			}
			if strings.Contains(tr.result.Upstream, "SYNTHETIC_CANARY") || strings.Contains(w.Body.String(), "SYNTHETIC_CANARY") {
				t.Fatal("authority/credential canary leaked")
			}
		})
	}
}

func TestDirectGatewayRemainsStrict(t *testing.T) {
	for _, header := range []string{"Forwarded", "X-Forwarded-For", "X-Real-IP", "Authorization", "Proxy-Authorization", "Cookie", "X-Api-Key", "Upgrade", "Keep-Alive"} {
		t.Run(header, func(t *testing.T) {
			raw := fmt.Sprintf("GET / HTTP/1.1\r\nHost: 127.0.0.1:18081\r\n%s: SYNTHETIC_CANARY\r\nConnection: close\r\n\r\n", header)
			result := validateGateway(t, []byte(raw))
			if result.Status != 502 || result.Reason != "unsupported headers" || result.Upstream != "" {
				t.Fatalf("direct gateway weakened: %+v", result)
			}
		})
	}
}
