"""Real nativeexec/control UDS + frozen Broker; FAKE Docker external seam.
Owned local SDK/process observations are NOT container/H2/runtime proof.
"""
import base64,json,os,signal,socket,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
import guest,driver
from v2_cases import ScopeBudget,install_strict_output_budget
sys.path.insert(0,str(guest.HERE/'vendor'))
sys.path.insert(0,str(guest.HERE.parent/'artex-worker-isolation/host'))
from lifecycle import Phase
from hostbroker.broker import Broker,Policy,Scope,Refused
from hostbroker.control import ControlServer

BINDING=dict(PhaseID='local-canary-only',Generation=1,TaskID=1,ExplorationID=1,IntentID=1,Role='worker',SessionID='local-i1',ExecutorID='local-only',NetworkPolicyID='no-network')
class LocalFakeDocker:
 def __init__(self,phase):self.phase=phase;self.effects=[];self.creates=[];self.mode='output';self.uncertain=False;self.process=None
 def run(self,args,payload=b'',**kw):
  if args[:2]==['image','inspect']:return b'{"/app/data":{}}'
  if args[0]=='create':
   self.phase.reserve();self.creates.append(args);self.effects.append({'name':args[args.index('--name')+1],'removed':False,'ack_payload_guard_entries':0});return b'FAKE_CONTAINER_ID'
  e=self.effects[-1]
  if args[0]=='inspect':
   mounts=[]
   for a in self.creates[-1]:
    if a.startswith('type=bind,src='):
     src=a.split(',src=')[1].split(',dst=')[0];dst=a.split(',dst=')[1].split(',')[0];mounts.append(dict(Type='bind',Source=src,Destination=dst,RW=dst=='/work'))
   return json.dumps({'mounts':mounts,'tmpfs':{'/tmp':'rw,noexec,nosuid,nodev,size=16m,mode=1777','/app/data':'ro,noexec,nosuid,nodev,size=64k,mode=0555'}}).encode()
  if args[0]=='start':
   with kw['payload_guard']():
    e['ack_payload_guard_entries']+=1;e['runtime']={'NOT_CONTAINER':True}
   kw['charge'](len(b'FAKE_PUBLIC_HELLO\n'))
   if self.mode=='cancel':
    self.process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    e['runtime']['local_pid']=self.process.pid
    while not kw['cancel'].wait(.005):pass
    raise Refused('local controlled process cancelled')
   p=subprocess.run([str(guest.HERE/'caller'),'--public-output-self-test'],input=b'',capture_output=True,timeout=4)
   if p.returncode:raise AssertionError('SDK public probe failed')
   sdk=json.loads(p.stdout)
   raw=json.dumps({'version':1,'result':{k:sdk[k] for k in ('Content','IsError')}}).encode()
   for i in range(0,len(raw),4096):kw['charge'](min(len(raw[i:i+4096]),131072-self.phase.bytes))
   return raw
  if args[0]=='rm':
   if self.process and self.process.poll() is None:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=2)
   return b''
  if args[0]=='ps':
   if self.uncertain:return b'FAKE_UNCERTAIN_OWNED_NAME'
   e['removed']=True
   e['process_cleanup']={'same_owned_pid_namespace':False,'remaining_cgroup_pids':[]}
   return b''
  raise AssertionError(args)

class NativeControlCases(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='cv2-',dir=os.environ.get('TMPDIR'));self.root=Path(self.tmp.name);self.root.chmod(0o700)
  self.phase=Phase(str(self.root),time.time()+120,clock=time.time);self.phase.start();install_strict_output_budget(self.phase)
  self.work=self.root/'work';self.work.mkdir(mode=0o700);self.fixture=self.root/'fixture';self.fixture.mkdir(mode=0o700)
  self.sock=socket.socket(socket.AF_UNIX);self.sock.bind(str(self.fixture/'gateway.sock'));os.chmod(self.fixture/'gateway.sock',0o600)
  self.fake=LocalFakeDocker(self.phase);self.scope=Scope(BINDING,str(self.work),str(self.fixture),ScopeBudget(self.phase))
  self.broker=Broker(Policy('sha256:'+'a'*64,str(self.root),os.getuid(),os.getgid(),'/FAKE_NOT_EXECUTED/docker','unix:///FAKE/private.sock'),[self.scope],driver=self.fake,reviewed=True)
  original=self.scope.charge
  def charge(n):self.phase.charge(n);original(n)
  self.scope.charge=charge
  self.key=os.urandom(32);self.control=ControlServer(str(self.root/'c.sock'),self.key,os.getuid(),self.broker);self.control.start();self.runner=guest.Runner()
 def tearDown(self):
  self.control.close()
  if self.fake.process and self.fake.process.poll() is None:os.killpg(self.fake.process.pid,signal.SIGKILL);self.fake.process.wait()
  for p in self.broker._pins.values():p.close()
  self.sock.close();self.tmp.cleanup()
 def call(self,tool,inputs,*,binding_override=None):
  request={'Binding':binding_override or BINDING,'Tool':tool,'Input':inputs,'ToolUseID':'local-public-only'}
  return json.loads(self.runner.run([str(guest.HERE/'caller')],timeout=15,cap=65536,payload=json.dumps({'Socket':self.control.path,'Key':base64.b64encode(self.key).decode(),'Request':request}).encode()))
 def test_real_native_control_sdk_aggregate_and_postcap(self):
  v=driver.exhaust_output(self.phase,self.call,self.fake)
  self.assertTrue(v['exhausted']);self.assertGreater(v['admitted_before_exhaustion'],0);self.assertLessEqual(v['shared_calls'],32);self.assertEqual(v['accepted_bytes'],131072)
  self.assertTrue(all(e['removed'] for e in self.fake.effects))
 def test_real_native_control_inflight_cancel_local_process(self):
  self.fake.mode='cancel'
  v=driver.cancel_inflight(self.call,self.broker,BINDING,self.scope,self.fake,lambda:self.fake.process is not None)
  self.assertTrue(v['settled']);self.assertIsNotNone(self.fake.process.poll());self.assertFalse(self.scope.lock.locked());self.assertEqual(v['post_cancel_input_writes'],0)
  # A second scope inherits exactly the same Broker quota and phase allowance.
  b=BINDING|{'IntentID':2,'SessionID':'local-i2'};w=self.root/'work2';w.mkdir(mode=0o700)
  calls=self.scope.quota.calls;global_calls=self.phase.calls
  s=Scope(b,str(w),str(self.fixture),ScopeBudget(self.phase));self.broker.register_scope(s,lambda x:x==b)
  self.assertIs(s.quota,self.scope.quota);self.assertEqual(s.quota.calls,calls);self.assertEqual(self.phase.calls,global_calls)
  original=s.charge
  def charge(n):self.phase.charge(n);original(n)
  s.charge=charge;self.fake.mode='output'
  positive=self.call('Bash',{'command':'PUBLIC_TEST_ONLY'},binding_override=b)
  self.assertFalse(positive['result']['IsError']);self.assertEqual(self.phase.calls,global_calls+1);self.assertEqual(s.quota.calls,calls+1)
 def test_real_native_control_uncertain_cleanup_holds_lock_fds(self):
  self.fake.mode='cancel';self.fake.uncertain=True
  with self.assertRaises(guest.Blocked):driver.cancel_inflight(self.call,self.broker,BINDING,self.scope,self.fake,lambda:self.fake.process is not None)
  self.assertTrue(self.scope.quarantined);self.assertTrue(self.scope.lock.locked())
  pin=self.broker._pins[self.broker._key(BINDING)];self.assertGreaterEqual(os.fstat(pin.fds['work']).st_ino,1)
  n=len(self.fake.effects)
  with self.assertRaises(guest.Blocked):self.call('LS',{'path':'/work'})
  self.assertEqual(len(self.fake.effects),n)
if __name__=='__main__':unittest.main()
