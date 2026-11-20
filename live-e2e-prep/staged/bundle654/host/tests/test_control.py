import hashlib,hmac,json,os,socket,struct,tempfile,unittest
from hostbroker.control import ControlServer
class FakeBroker:
    def __init__(self):self.calls=[]
    def execute(self,r):self.calls.append(r);return {'version':1,'result':{'Content':[{'type':'text','text':'ok'}],'IsError':False}}
class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=FakeBroker();self.key=b'k'*32;self.c=ControlServer(self.tmp.name+'/control.sock',self.key,os.getuid(),self.b);self.c.start()
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def call(self,payload,key=None):
        mac=hmac.digest(key or self.key,payload,'sha256');s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect(self.c.path)
        with s:
            s.sendall(struct.pack('!I',len(payload)+32)+mac+payload)
            hdr=s.recv(4);n=struct.unpack('!I',hdr)[0];out=b''
            while len(out)<n:out+=s.recv(n-len(out))
            return json.loads(out)
    def test_authenticated_control_separate_from_fixture(self):
        self.assertEqual(self.call(b'{"Tool":"LS"}')['result']['Content'][0]['text'],'ok');self.assertEqual(len(self.b.calls),1);self.assertEqual(os.stat(self.c.path).st_mode&0o777,0o600)
    def test_bad_auth_and_duplicate_before_execution(self):
        self.assertIn('error',self.call(b'{"Tool":"LS"}',b'x'*32));self.assertIn('error',self.call(b'{"Tool":"LS","Tool":"Bash"}'));self.assertEqual(self.b.calls,[])
