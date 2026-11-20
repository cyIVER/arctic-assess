package main
import("io";"net/http";"net/http/httptest";"net/http/httputil";"strings";"testing")
type recordingTransport struct{header http.Header}
func(r *recordingTransport)RoundTrip(q *http.Request)(*http.Response,error){r.header=q.Header.Clone();return &http.Response{StatusCode:200,Header:http.Header{},Body:io.NopCloser(strings.NewReader(""))},nil}
func TestFrozenProxyDirectorAddsHeaderGatewayDisallows(t *testing.T){
 tr:=&recordingTransport{}
 // Exact frozen helper Director; no listener/dial/server is started.
 p:=&httputil.ReverseProxy{Director:func(r *http.Request){r.URL.Scheme="http";if r.URL.Host==""{r.URL.Host=r.Host}},Transport:tr}
 request:=httptest.NewRequest("GET","http://127.0.0.1:12345/",nil)
 p.ServeHTTP(httptest.NewRecorder(),request)
 if tr.header.Get("X-Forwarded-For")==""{t.Fatal("expected Go ReverseProxy-generated header")}
 t.Log("Observed X-Forwarded-For; frozen gateway.py:122 disallows that header")
}
