import http.server, os, socket, tempfile, threading, time, unittest
from hostbroker.gateway import Gateway, Budget
class Fixture(http.server.BaseHTTPRequestHandler):
    calls=[]
    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        type(self).calls.append((self.command,self.path,dict(self.headers)))
        if self.path=='/redirect':
            self.send_response(302); self.send_header('Location','http://forbidden.invalid/secret'); self.send_header('Content-Length','0');self.end_headers();return
        data=b'x'*50000 if self.path=='/large' else b'fixture literal'
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers()
        if self.command!='HEAD':
            try: self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError): pass
    def log_message(self,*a): pass
class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();Fixture.calls=[]
        self.origin='http://fixture.test:'+str(self.server.server_port)
        self.budget=Budget(max_calls=32,max_bytes=131072)
        self.g=Gateway(self.tmp.name+'/gateway.sock',self.origin,'127.0.0.1',self.budget,peer_uid=os.getuid(),timeout=.4,max_response=32768);self.g.start()
    def tearDown(self): self.g.close();self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,target='/',method='GET',extra='',host=None,tail=b''):
        raw=(method+' '+target+' HTTP/1.1\r\nHost: '+(host or self.origin[7:])+'\r\n'+extra+'\r\n').encode()+tail
        return self.raw(raw)
    def raw(self,raw):
        s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect(self.g.path);data=b''
        try:
            s.sendall(raw)
            while True:
                b=s.recv(65536)
                if not b:break
                data+=b
        except (ConnectionResetError, BrokenPipeError):pass
        finally:s.close()
        return data
    def test_positive_get_head_absolute_reconstructed(self):
        self.assertIn(b'200 OK',self.request());self.assertIn(b'fixture literal',self.request(self.origin+'/discover'))
        self.assertNotIn(b'fixture literal',self.request(method='HEAD'))
        self.assertEqual(len(Fixture.calls),3)
        self.assertNotIn('Authorization',Fixture.calls[0][2]);self.assertEqual(Fixture.calls[0][2]['Host'],self.origin[7:])
    def test_origin_method_framing_denied_before_fixture(self):
        cases=[dict(method='POST'),dict(method='CONNECT'),dict(host='other.test'),dict(target='http://evil.invalid/a'),dict(target='//evil/a'),dict(extra='Host: evil\r\n'),dict(extra='Transfer-Encoding: chunked\r\n'),dict(extra='Content-Length: 0\r\n'),dict(extra='Authorization: secret\r\n'),dict(extra='X-Forwarded-Host: evil\r\n'),dict(extra='Upgrade: websocket\r\n'),dict(extra='Connection: upgrade\r\n'),dict(target='/x%0d%0ay'),dict(extra=' Bad: folded\r\n'),dict(tail=b'GET / HTTP/1.1\r\nHost: evil\r\n\r\n')]
        for c in cases:
            with self.subTest(c=c): self.assertNotIn(b'200 OK',self.request(**c))
        self.assertEqual(Fixture.calls,[])
    def test_redirect_not_followed_or_disclosed(self):
        data=self.request('/redirect');self.assertIn(b'502',data);self.assertNotIn(b'forbidden.invalid',data);self.assertEqual([c[1] for c in Fixture.calls],['/redirect'])
    def test_response_limit(self):
        data=self.request('/large');self.assertIn(b'502',data);self.assertLess(len(data),1024)
    def test_shared_budget_and_cancel(self):
        self.budget.max_calls=1;self.assertIn(b'200 OK',self.request());self.assertNotIn(b'200 OK',self.request());self.assertEqual(len(Fixture.calls),1)
        self.budget.cancel();self.assertNotIn(b'200 OK',self.request())
    def test_slow_partial_header_absolute_timeout_and_cancel(self):
        s=socket.socket(socket.AF_UNIX);s.connect(self.g.path);s.sendall(b'GET / HTTP/1.1\r\n');start=time.monotonic();s.settimeout(2);self.assertNotIn(b'200 OK',s.recv(1024));self.assertLess(time.monotonic()-start,1);s.close();self.assertEqual(Fixture.calls,[])
        s=socket.socket(socket.AF_UNIX);s.connect(self.g.path);s.sendall(b'GET /');time.sleep(.03);self.budget.cancel();s.settimeout(1);start=time.monotonic();self.assertNotIn(b'200 OK',s.recv(1024));self.assertLess(time.monotonic()-start,.4);s.close()
