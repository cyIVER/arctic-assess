"""Offline integrated production entrypoints; injected package/provider seams only."""
import copy,hashlib,json,os,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'canary'),str(ROOT/'guardian')]
import guest,admission_v3,guard
import test_protected_tuple_v3 as tuples
import test_security
from test_guard import fixture,NOW,Runner

def merged(c):
 return {'schema':1,'status':'verified','requirement':'already-private-default-quiescent','vm':c['vm'],'created':c['created'],'deadline':c['deadline'],'parent_scope_lease':c['parent_scope_lease']['handle'],'default_service_changes_owner':'parent','external_stop':c['external_stop'],'default_inventory':{'containers':[],'images':[],'volumes':[]}}
def bind(c,context,a,p):
 raw=guard.canonical(p);path=Path(c['preflight']['path']);path.write_bytes(raw);path.chmod(0o600)
 c['preflight']['sha256']=guard.digest(raw);a['preflight']=copy.deepcopy(c['preflight']);a['config_sha256']=admission_v3.canonical(c);context.write_bytes(guard.canonical(a));context.chmod(0o600)
 return raw

def inventory(c,raw,changes=None):
 seam=test_security.Guest();seam.setUp()
 if changes:
  for k,v in changes.items():setattr(seam,k,v)
 reads=[]
 def read(path,sha=None,**kw):
  if path==c['preflight']['path']:
   reads.append((path,sha));guard.need(guard.digest(raw)==sha,'test pinned read');return raw
  return b'UNIT_ONLY_PACKAGE_FILE'
 out=guard.guest_inventory(c,runner=seam.runner,clock=lambda:c['created'],read=read)
 return out,seam.calls,reads

class Integrated(unittest.TestCase):
 def test_actual_guard_scope_loader_same_context_and_checkpoint(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=tuples.fixture(d);d=Path(d)
   source=ROOT/'guardian/guard.py'
   c['guard_status']=str(source);h=c['reviews']['guard'];h.update(path=str(source),sha256=guard.digest(source.read_bytes()))
   rp=Path(h['review_path']);report=json.loads(rp.read_bytes());report['object_sha256']=h['sha256'];rp.write_bytes(guard.canonical(report));h['review_sha256']=guard.digest(rp.read_bytes())
   a['reviews']=copy.deepcopy(c['reviews']);a['guardian_implementation']={'path':str(source),'sha256':h['sha256']}
   review=Path(a['guardian_review']['path']);review.write_bytes(guard.canonical({'status':'approved','verdict':'SCOPED_PASS','object_sha256':h['sha256'],'scope':'UNIT_ONLY_NOT_REAL_APPROVAL'}));a['guardian_review']['sha256']=guard.digest(review.read_bytes())
   raw=bind(c,context,a,merged(c))
   scope={k:copy.deepcopy(c[k]) for k in ('schema','vm','lane','created','deadline','guard_created','external_stop','controller_id','preflight','parent_scope_lease')}
   parent=d/'parent.json';parent.write_bytes(guard.canonical(scope));parent.chmod(0o600)
   allow=d/'allowlist.json';allow.write_bytes(guard.canonical({'guard_sha256':h['sha256'],'guardian_review':a['guardian_review']}));allow.chmod(0o600)
   with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
    self.assertIs(guest.validate(c,1000),c)
   original=os.fstat
   def metadata(fd):
    s=original(fd);v=list(s);v[4]=0
    if __import__('stat').S_ISDIR(s.st_mode):v[0]&=~0o022
    return os.stat_result(v)
   with patch.object(guard.os,'fstat',side_effect=metadata),patch.object(guard.os,'geteuid',return_value=0),patch.multiple(guard,ROOT=str(d),SOURCE=str(source),CONTEXT=str(context),ALLOWLIST=str(allow),__file__=str(source)),patch.object(guard,'utc',return_value=1000):
    loaded=guard.load_scope('guest')
   self.assertEqual(loaded['preflight'],c['preflight']);self.assertEqual(inventory(loaded,raw)[0]['checkpoint_sha256'],guard.digest(raw))
 def test_same_serialized_path_hash_both_actual_validators_and_status(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=tuples.fixture(d);raw=bind(c,context,a,merged(c))
   with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
    self.assertIs(guest.validate(c,1000),c)
    inv,calls,reads=inventory(c,raw)
    self.assertEqual(reads,[(c['preflight']['path'],c['preflight']['sha256'])]);self.assertEqual(inv['checkpoint_sha256'],guard.digest(raw));self.assertEqual(len([x for x in calls if x[0]=='command']),9)
    scope=fixture();scope.update({k:c[k] for k in ('preflight','external_stop','controller_id','guard_created')})
    runner=Runner();runner.guest=inv
    runner.vm['scheduling']['terminationTime']=__import__('datetime').datetime.fromtimestamp(c['external_stop'],__import__('datetime').timezone.utc).isoformat()
    result=guard.VPSGuardReadback(scope,runner=runner,clock=lambda:1000,controller_check=lambda c:None,controller_release=lambda fd:None).status()
    class Consumer:
     def run(self,argv,**kw):self.kw=kw;return guard.canonical(result)
    consumer=Consumer();self.assertEqual(guest.guard(c,consumer,1000),result);self.assertEqual(consumer.kw,{'timeout':12,'cap':8192})
    guest.guard(c|{'deadline':1002},consumer,1000);self.assertEqual(consumer.kw['timeout'],2)
    self.assertEqual(result['preflight_checkpoint_sha256'],guard.digest(raw))
 def test_contract_negatives_both_after_same_entrypoint_positive(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=tuples.fixture(d);good=merged(c)
   with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
    raw=bind(c,context,a,good);self.assertIs(guest.validate(c,1000),c);inventory(c,raw)
    variants=[('schema',True),('status','READY'),('requirement','anything'),('vm',{}),('created',True),('created',879),('deadline',True),('deadline',1601),('parent_scope_lease','forged'),('default_service_changes_owner','worker'),('external_stop',2001),('external_stop',True),('default_inventory',{'containers':['x'],'images':[],'volumes':[]}),('extra',True)]
    for name,value in variants:
     with self.subTest(name=name,value=value):
      raw=bind(c,context,a,good|{name:value})
      with self.assertRaises(guest.Blocked):guest.validate(c,1000)
      with self.assertRaises((guard.Blocked,KeyError)):inventory(c,raw)
    raw=bind(c,context,a,good)
    for change in ({'active':True},{'override':True},{'bad_package':True},{'socket_active':True}):
     with self.subTest(change=change),self.assertRaises(guard.Blocked):inventory(c,raw,change)
    self.assertIs(guest.validate(c,1000),c);inventory(c,raw)
    with self.assertRaises(guard.Blocked):inventory(c,raw+b' ')
    Path(c['preflight']['path']).write_bytes(raw+b' ')
    with self.assertRaises(guest.Blocked):guest.validate(c,1000)

class ClientDeadline(unittest.TestCase):
 def exchange(self,connect_seconds,send_seconds,receive_seconds):
  c=fixture();elapsed=[0.0];key=b'x'*32;timeouts=[]
  status={'alive':True,'provider_state':'RUNNING','vm':guard.VM,'stop_at':c['external_stop'],'controller_id':c['controller_id'],'guard_created':c['guard_created'],'default_docker_quiescent':True,'preflight_checkpoint_sha256':c['preflight']['sha256']}
  class Sock:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def settimeout(self,v):timeouts.append(v)
   def sendall(self,b):
    elapsed[0]+=send_seconds;p=json.loads(b[4:])['payload'];reply={'nonce':p['nonce'],'time':NOW+connect_seconds+send_seconds+receive_seconds,'status':status};data=guard.canonical({'payload':reply,'mac':guard.mac(key,reply)});self.data=struct.pack('!I',len(data))+data
   def recv(self,n):
    if not hasattr(self,'received'):elapsed[0]+=receive_seconds;self.received=True
    out,self.data=self.data[:n],self.data[n:];return out
  def connect(*a,**kw):elapsed[0]+=connect_seconds;timeouts.append(kw['timeout']);return Sock()
  with patch.object(guard.socket,'create_connection',side_effect=connect),patch.object(guard.time,'monotonic',side_effect=lambda:elapsed[0]):
   result=guard.client_status(c,key,clock=lambda:NOW+elapsed[0])
  return result,elapsed[0],timeouts
 def test_18_seconds_rejected_not_perstage_accepted(self):
  with self.assertRaises(guard.Blocked):self.exchange(9,0,9)
 def test_send_time_counts_in_shared_deadline(self):
  with self.assertRaises(guard.Blocked):self.exchange(4,5,2)
 def test_within10_positive_and_remaining_timeout(self):
  result,elapsed,timeouts=self.exchange(2,1,5);self.assertTrue(result['alive']);self.assertEqual(elapsed,8);self.assertLessEqual(min(timeouts),2)
if __name__=='__main__':unittest.main(verbosity=2)
