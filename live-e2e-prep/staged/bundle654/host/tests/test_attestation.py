"""Local byteflow only: fake CLI is NOT a daemon or mount-confinement proof."""
import json, os, pathlib, socket, sys, threading, unittest, time, hmac, struct
import test_broker as fixtures
from hostbroker.broker import Broker, DockerCLI, Policy, Refused

SCRIPT='''import json,os,pathlib,sys,time
state=pathlib.Path(__file__).parent
args=sys.argv[3:]; op=args[0]
def identity(p,fs=True):
 s=os.stat(p);d=dict(device=s.st_dev,inode=s.st_ino)
 if fs:
  v=os.statvfs(p);d['fs_bytes']=v.f_blocks*v.f_frsize
 return d
if op=='image':print('{"/app/data":{}}')
elif op=='inspect':
 paths=json.loads((state/'paths').read_text())
 print(json.dumps(dict(mounts=[dict(Type='bind',Source=paths[0],Destination='/work',RW=True),dict(Type='bind',Source=paths[1],Destination='/fixture',RW=False)],tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=16m,mode=1777','/app/data':'ro,noexec,nosuid,nodev,size=64k,mode=0555'})))
elif op=='create':
 paths=[a.split(',src=')[1].split(',dst=')[0] for a in args if a.startswith('type=bind,src=')]
 (state/'paths').write_text(json.dumps(paths))
 race=(state/'mode').read_text()
 if race.startswith('replace-') or race.startswith('symlink-'):
  which=race.split('-')[1]; p=pathlib.Path(paths[0] if which=='work' else paths[1])
  if which=='root':p=p.parent
  old=p.with_name(p.name+'.held');p.rename(old)
  if race.startswith('symlink-'):p.symlink_to(old,target_is_directory=True)
  elif which=='root':
   p.mkdir(mode=0o700);(p/'work').mkdir(mode=0o700);(p/'fixture').symlink_to(old/'fixture',target_is_directory=True)
  else:
   p.mkdir(mode=0o700)
   if which=='fixture':(p/'gateway.sock').symlink_to(old/'gateway.sock')
 print('id')
elif op=='start':
 line=sys.stdin.buffer.readline()
 (state/'first').write_bytes(line)
 try:challenge=json.loads(line)
 except Exception:sys.exit(4)
 if challenge.get('version')!=2:
  (state/'payload').write_bytes(line);print('{"version":1,"result":{"Content":[],"IsError":false}}');sys.exit(0)
 paths=json.loads((state/'paths').read_text());mode=(state/'mode').read_text()
 if mode=='timeout':time.sleep(2);sys.exit(0)
 if mode=='eof':sys.exit(0)
 if mode=='stderr':sys.stderr.buffer.write(b'x'*200000);sys.stderr.buffer.flush()
 hello=dict(version=2,nonce=challenge['nonce'],work=identity(paths[0]),fixture=identity(paths[1]),gateway=identity(paths[1]+'/gateway.sock',False))
 if mode=='nonce':hello['nonce']='0'*64
 if mode=='extra':hello['extra']=True
 if mode=='malformed':print('not-json',flush=True)
 elif mode=='duplicate':print('{"version":2,"version":2}',flush=True)
 elif mode=='oversize':print('x'*9000,flush=True)
 else:print(json.dumps(hello),flush=True)
 ack=sys.stdin.buffer.readline()
 if ack:
  (state/'ack').write_bytes(ack)
  data=sys.stdin.buffer.read();(state/'payload').write_bytes(data)
  print('{"version":1,"result":{"Content":[{"type":"text","text":"local-protocol"}],"IsError":false}}')
elif op=='ps':pass
elif op=='rm':pass
else:sys.exit(3)
'''

class AttestationTests(unittest.TestCase):
    setUp=fixtures.BrokerTests.setUp
    tearDown=fixtures.BrokerTests.tearDown
    req=fixtures.BrokerTests.req
    def setup_cli(self,mode):
        # Outside data_root so root replacement does not replace test controller.
        self.addCleanup(self.cli_tmp.cleanup) if hasattr(self,'cli_tmp') else None
        import tempfile
        self.cli_tmp=tempfile.TemporaryDirectory();self.addCleanup(self.cli_tmp.cleanup)
        self.control=pathlib.Path(self.cli_tmp.name)
        executable=self.control/'cli';executable.write_text('#!'+sys.executable+'\n'+SCRIPT);executable.chmod(0o700)
        (self.control/'mode').write_text(mode)
        policy=Policy(self.policy.image,self.policy.data_root,self.policy.uid,self.policy.gid,str(executable),self.policy.daemon)
        return Broker(policy,[self.scope],driver=DockerCLI(policy),reviewed=True)

    def test_positive_handshake_admits_unchanged_v1_input(self):
        b=self.setup_cli('valid');self.assertEqual(b.execute(self.req())['version'],1)
        self.assertEqual(json.loads((self.control/'payload').read_bytes())['input'],self.req()['Input'])
        self.assertEqual(json.loads((self.control/'first').read_bytes())['version'],2)
        self.assertEqual(json.loads((self.control/'ack').read_bytes())['version'],2)
        self.assertGreater(self.scope.output_bytes,300)

    def test_replaced_workspace_refused_before_payload(self):
        b=self.setup_cli('replace-work')
        with self.assertRaises(Refused):b.execute(self.req())
        self.assertFalse((self.control/'payload').exists())

    def test_replaced_fixture_and_quota_root_refused_before_payload(self):
        # Each independent fixture has its own admitted pinned registration.
        for mode in ('replace-fixture','replace-root','symlink-work','symlink-fixture','symlink-root'):
            with self.subTest(mode=mode):
                case=AttestationTests();case.setUp()
                try:
                    b=case.setup_cli(mode)
                    with self.assertRaises(Refused):b.execute(case.req())
                    self.assertFalse((case.control/'payload').exists())
                finally:
                    if case.root.is_symlink():case.root.unlink();case.root.with_name(case.root.name+'.held').rename(case.root)
                    import shutil
                    held=case.root.with_name(case.root.name+'.held')
                    if held.exists():shutil.rmtree(held)
                    case.doCleanups();case.tearDown()

    def test_bad_hello_never_receives_ack_or_payload(self):
        for mode in ('nonce','extra','malformed','duplicate','oversize','eof','stderr'):
            with self.subTest(mode=mode):
                b=self.setup_cli(mode)
                with self.assertRaises(Refused):b.execute(self.req())
                self.assertFalse((self.control/'ack').exists())
                self.assertFalse((self.control/'payload').exists())

    def test_membership_revoked_after_mount_before_payload(self):
        b=self.setup_cli('valid');active=[True];calls=[0]
        def verifier(binding):
            calls[0]+=1
            return calls[0]<3
        self.scope.membership_verifier=verifier
        with self.assertRaises(Refused):b.execute(self.req())
        self.assertFalse((self.control/'payload').exists())

    def test_hello_timeout_and_cancel_settle_without_payload(self):
        for cancelled in (False,True):
            with self.subTest(cancelled=cancelled):
                b=self.setup_cli('timeout')
                if cancelled:
                    def cancel_after_challenge():
                        end=time.monotonic()+2
                        while time.monotonic()<end and not (self.control/'first').exists():time.sleep(.005)
                        self.budget.cancel()
                    timer=threading.Thread(target=cancel_after_challenge);timer.start()
                started=time.monotonic()
                with self.assertRaises(Refused):b.execute(self.req())
                if cancelled:timer.join(3)
                self.assertLess(time.monotonic()-started,3)
                self.assertFalse((self.control/'payload').exists())
                self.assertFalse((self.control/'ack').exists())
                # New budget only for this independent transport rehearsal.
                self.scope.budget=fixtures.Budget();self.budget=self.scope.budget

    def test_dropped_authenticated_control_cancels_before_payload(self):
        from hostbroker.control import ControlServer
        b=self.setup_cli('timeout');path=str(self.control/'control.sock');key=b'p'*32
        server=ControlServer(path,key,os.getuid(),b);server.start()
        client=socket.socket(socket.AF_UNIX);client.settimeout(3);client.connect(path)
        try:
            payload=json.dumps(self.req(),separators=(',',':')).encode()
            frame=hmac.digest(key,payload,'sha256')+payload
            client.sendall(struct.pack('!I',len(frame))+frame)
            end=time.monotonic()+2
            while time.monotonic()<end and not (self.control/'first').exists():time.sleep(.005)
            self.assertTrue((self.control/'first').exists());client.close()
            self.assertTrue(self.budget.stopped.wait(2))
        finally:client.close();server.close()
        self.assertFalse((self.control/'payload').exists());self.assertFalse((self.control/'ack').exists())
        self.assertIn(b._key(self.req()['Binding']),b.tombstones)

    def test_wrong_required_quota_rejected_at_reservation(self):
        self.scope.quota_bytes=67108864
        with self.assertRaises(Refused):Broker(self.policy,[self.scope],driver=self.fake,reviewed=True)
        self.assertFalse(self.fake.calls)
