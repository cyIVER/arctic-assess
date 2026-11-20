import io, json, socket, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from bridge import Bridge, Handler, MODEL, REQUEST_CAP, RESPONSE_CAP, TOTAL_CAP, Denied

TASK='task-fixture-key-distinct-123456789'; VENDOR='vendor-fixture-secret-123456789'
def payload(**kw):
    return json.dumps(dict(model=MODEL, stream=False, max_tokens=4096,
                           messages=[{'role':'user','content':'owned fixture'}], **kw)).encode()
class Fake:
    def __init__(self, status=200, body=b'{"choices":[]}'):
        self.status=status; self.body=body; self.calls=[]
    def __call__(self, body, key, deadline):
        self.calls.append((json.loads(body),key,deadline)); return self.status,self.body
class Tests(unittest.TestCase):
    def setUp(self):
        self.no_network=patch('socket.socket', side_effect=AssertionError('offline: no sockets'))
        self.no_network.start(); self.addCleanup(self.no_network.stop)
        self.f=Fake(); self.b=Bridge(TASK,VENDOR,time.time()+300,transport=self.f)
    def send(self, body=None, path='/v1/chat/completions', key=TASK, method='POST'):
        return self.b.request(method,path,'Bearer '+key,body or payload())
    def test_positive_passthrough_and_real_owned_file_result(self):
        tool={'role':'assistant','content':None,'tool_calls':[{'id':'call1','type':'function','function':{'name':'read_owned_file','arguments':'{}'}}]}
        self.f.body=json.dumps({'choices':[{'message':tool}]}).encode()
        status,body=self.send(); self.assertEqual(status,200); self.assertEqual(json.loads(body)['choices'][0]['message'],tool)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            p=Path(d)/'owned.txt'; p.write_text('actual-file-result')
            request=json.loads(payload()); request['messages'] += [tool,{'role':'tool','tool_call_id':'call1','content':p.read_text()}]
            self.send(json.dumps(request).encode())
        self.assertEqual(self.f.calls[1][0]['messages'][-1]['content'],'actual-file-result')
        self.assertEqual(self.f.calls[1][0]['messages'][-1]['tool_call_id'],'call1')
    def test_denials_before_upstream(self):
        for change in ({'model':42},{'model':'other'},{'stream':True},{'max_tokens':4097},{'max_tokens':True},{'base_url':'https://evil.invalid'},{'metadata':{'proxy':'x'}}):
            p=json.loads(payload()); p.update(change)
            with self.assertRaises(Denied): self.send(json.dumps(p).encode())
        for kwargs in ({'path':'/v1/models'},{'path':'/v1/chat/completions?x=1'},{'key':'wrong'},{'method':'GET'}):
            with self.assertRaises(Denied): self.send(**kwargs)
        self.assertEqual(self.f.calls,[])
    def test_request_cap(self):
        with self.assertRaises(Denied): self.send(b' '* (REQUEST_CAP+1))
    def test_call_cap(self):
        for _ in range(16): self.send()
        with self.assertRaises(Denied): self.send()
        self.assertEqual(len(self.f.calls),16)
    def test_response_cap(self):
        self.f.body=b'x'*(RESPONSE_CAP+1)
        with self.assertRaises(Denied): self.send()
    def test_total_cap(self):
        self.b.response_bytes=TOTAL_CAP
        with self.assertRaises(Denied): self.send()
        self.assertFalse(self.f.calls)
    def test_expiry(self):
        self.b.expires=time.monotonic()-1
        with self.assertRaises(Denied): self.send()
        self.assertFalse(self.f.calls)
    def test_redirect_and_error_sanitized(self):
        for status in (301,302,307,308,401,500):
            self.f.status=status; self.f.body=VENDOR.encode()
            with self.assertRaises(Denied) as e: self.send()
            self.assertNotIn(VENDOR,str(e.exception))
        self.assertEqual(len(self.f.calls),6)
    def test_secret_echo_denied(self):
        for secret in (TASK,VENDOR):
            self.f.body=json.dumps({'content':secret},ensure_ascii=True).encode()
            with self.assertRaises(Denied): self.send()
    def test_non_utf8_duplicate_json_denied(self):
        for body in (payload().decode().encode('utf-16'), b'{"model":"x","model":"qwen3.5-9b"}'):
            with self.assertRaises(Denied): self.send(body)
    def test_unknown_non_transport_preserved(self):
        self.send(payload(metadata={'fixture':'okay'},tools=[{'type':'function','function':{'name':'read_owned_file','parameters':{'type':'object'}}}]))
        self.assertEqual(self.f.calls[0][0]['metadata'],{'fixture':'okay'})
    def test_fixed_transport_redirect_no_follow(self):
        import bridge
        from email.message import Message
        class Sock:
            def settimeout(self,n): pass
            def close(self): pass
        class Response:
            status=307
            headers=Message()
            def close(self): pass
        calls=[]
        class Connection:
            def __init__(self,host,port,**kw):
                calls.append((host,port,kw)); self.sock=Sock()
            def connect(self): pass
            def request(self,*args,**kw): calls.append((args,kw))
            def getresponse(self): return Response()
            def close(self): pass
        with patch('bridge.http.client.HTTPSConnection',Connection):
            status,body=bridge.upstream(payload(),VENDOR,time.monotonic()+1)
        self.assertEqual((status,body),(307,b''))
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][:2],('iverson-pc-1.tail8ccbd1.ts.net',443))
        self.assertTrue(calls[0][2]['context'].check_hostname)
        self.assertEqual(calls[1][0][:2],('POST','/v1/chat/completions'))
    def test_slow_read_absolute_deadline(self):
        from bridge import DeadlineReader
        class Sock:
            def settimeout(self,n): pass
            def recv_into(self,b): return 1
        with patch('bridge.time.monotonic',side_effect=[0,2]):
            with self.assertRaises(Denied): DeadlineReader(Sock(),1).readinto(bytearray(1))
    def test_tool_schema_url_is_data_not_routing(self):
        self.send(payload(tools=[{'type':'function','function':{'name':'fetch_owned','parameters':{'properties':{'url':{'type':'string'}}}}}]))
        self.assertEqual(len(self.f.calls),1)
    def test_gateway_fixed_loopback(self):
        from guest_gateway import forward
        from email.message import Message
        calls=[]
        class Sock:
            def settimeout(self,n): pass
        class Response:
            status=200
            headers=Message(); headers['Content-Length']='2'
            def getheader(self,k): return self.headers.get(k)
            def read1(self,n): return b'{}'
            def close(self): pass
        class Connection:
            def __init__(self,*args,**kw): calls.append(args); self.sock=Sock()
            def connect(self): pass
            def request(self,*args,**kw): calls.append((args,kw))
            def getresponse(self): return Response()
            def close(self): pass
        with patch('guest_gateway.http.client.HTTPConnection',Connection):
            self.assertEqual(forward(payload(),TASK,time.monotonic()+1),(200,b'{}'))
        self.assertEqual(calls[0],('127.0.0.1',18760))
        self.assertEqual(calls[1][1]['headers']['Authorization'],'Bearer '+TASK)
        self.assertNotIn(VENDOR,str(calls))
    def test_actual_handler_fake_io(self):
        class Conn:
            def makefile(self,mode,*args): return io.BytesIO(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+TASK.encode()+b'\r\nContent-Length: '+str(len(payload())).encode()+b'\r\n\r\n'+payload())
            def sendall(self,b): output.write(b)
            def settimeout(self,n): pass
        class Server: bridge=self.b
        output=io.BytesIO(); Handler(Conn(),('127.0.0.1',1),Server())
        self.assertIn(b'200 OK',output.getvalue()); self.assertNotIn(VENDOR.encode(),output.getvalue())
if __name__=='__main__': unittest.main(verbosity=2)
