"""LOCAL fixtures only. No approval or RuntimeProof; external runner is fake."""
import json, os, socket, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
import guest, driver, probes
sys.path.insert(0,str(guest.HERE/'vendor'))
sys.path.insert(0,str(guest.HERE.parent/'artex-worker-isolation/host'))
from lifecycle import Phase

class CasesV2(unittest.TestCase):
 def phase(self,d):
  os.chmod(d,0o700);p=Phase(d,time.time()+120,clock=time.time);p.start();return p
 def test_shared_output_bound_no_refund(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.phase(d)
   install=getattr(driver,'install_strict_output_budget',lambda p:None);install(p)
   p.reserve();p.charge(131000)
   with self.assertRaises(Exception):p.charge(4096)
   self.assertLessEqual(p.bytes,131072)
   before=(p.calls,p.bytes)
   with self.assertRaises(Exception):p.reserve()
   self.assertEqual((p.calls,p.bytes),before)
 def test_terminal_exhaustion_real_seam_and_denial(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.phase(d);observed=type('O',(),{'effects':[]})();calls=[]
   def call(tool,inputs,**kw):
    p.reserve();calls.append(inputs)
    n=18000
    e={'removed':True,'runtime':{'public':True},'ack_payload_guard_entries':1};observed.effects.append(e)
    p.charge(min(n,131072-p.bytes))
    return {'version':1,'result':{'IsError':False,'Content':[{'type':'text','text':'PUBLIC_STDOUT_'+('x'*8000)+'PUBLIC_STDERR_'+('y'*8000)}]}}
   fn=getattr(driver,'exhaust_output',lambda *a: {})
   result=fn(p,call,observed)
   self.assertTrue(result.get('exhausted'))
   self.assertGreater(result['admitted_before_exhaustion'],0)
   self.assertEqual(len(observed.effects),result['effects'])
   self.assertLessEqual(p.calls,32);self.assertLessEqual(p.bytes,131072)
 def test_restart_child_actual_owned_process(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.phase(d);p.reserve();p.charge(17)
   fn=getattr(driver,'restart_fence',lambda *a: {})
   result=fn(p,guest.Runner(),sys.executable)
   self.assertTrue(result.get('second_process_denied'))
   self.assertEqual((p.calls,p.bytes),(1,17))
   self.assertEqual(Path(d,'executor-started').read_bytes(),b'fail-closed single incarnation\n')
 def test_cancel_hook_settles_and_no_postcancel(self):
  cancelled=threading.Event();entered=threading.Event()
  scope=type('S',(),{'quarantined':False})();observed=type('O',(),{'effects':[]})()
  broker=type('B',(),{'revoke_scope':lambda s,b:cancelled.set()})()
  def call(tool,inputs,**kw):
   if cancelled.is_set():raise guest.Blocked('revoked')
   e={'removed':False,'runtime':{'public':True},'ack_payload_guard_entries':1};observed.effects.append(e);entered.set()
   if not cancelled.wait(1):raise AssertionError('not cancelled')
   e['removed']=True;e['process_cleanup']={'same_owned_pid_namespace':False,'remaining_cgroup_pids':[]}
   raise guest.Blocked('cancelled')
  fn=getattr(driver,'cancel_inflight',lambda *a,**k: {})
  result=fn(call,broker,{'IntentID':2},scope,observed,lambda:entered.is_set())
  self.assertTrue(result.get('settled'))
  self.assertEqual(result['new_effects_after_cancel'],0)
 def test_proxy_probe_really_uses_environment_get_head(self):
  fn=getattr(probes,'environment_proxy',lambda origin:'')
  text=fn('http://127.0.0.1:1234')
  self.assertIn('ProxyHandler',text);self.assertIn('GET',text);self.assertIn('HEAD',text)
  self.assertIn('opener.open',text)

 def test_live_rejects_original_fixed_source_helper(self):
  from test_live_inputs import CurrentInputTests
  with tempfile.TemporaryDirectory() as d:
   c=CurrentInputTests().fixture(d)
   with self.assertRaises(guest.Blocked):guest.validate(c,1000)
 def test_fresh_guard_requires_external_quiescent_checkpoint(self):
  class R:
   def run(self,*a,**k):return json.dumps({'alive':True,'provider_state':'RUNNING','vm':guest.VM,'stop_at':300,'controller_id':'c','guard_created':10}).encode()
  c={'deadline':200,'external_stop':300,'controller_id':'c','guard_created':10,'guard_status':'/not-executed','preflight':{'path':'/public-test-only','sha256':'1'*64}}
  with self.assertRaises(guest.Blocked):guest.guard(c,R(),100)

 def test_sdk_finite_both_streams_actual_caller(self):
  p=subprocess.run([str(guest.HERE/'caller'),'--public-output-self-test'],input=b'',capture_output=True,timeout=4)
  self.assertEqual(p.returncode,0)
  v=json.loads(p.stdout);text=''.join(c.get('text','') for c in v['Content'])
  self.assertIn('PUBLIC_STDOUT_',text);self.assertIn('PUBLIC_STDERR_',text)
  self.assertFalse(v['IsError']);self.assertGreater(len(p.stdout),15000);self.assertLess(len(p.stdout),20000)

 def test_transport_reads_no_more_than_shared_remaining(self):
  from hostbroker.broker import DockerCLI,Policy
  with tempfile.TemporaryDirectory() as d:
   p=self.phase(d);driver.install_strict_output_budget(p);p.reserve();p.charge(131000)
   cli=Path(d)/'fake-cli';cli.write_text('#!'+sys.executable+'\nimport os;os.write(1,b"P"*4096);os.write(2,b"E"*4096)\n');cli.chmod(0o700)
   policy=Policy('sha256:'+'a'*64,d,os.getuid(),os.getgid(),str(cli),'unix:///FAKE/private.sock')
   factory=getattr(driver,'bounded_transport',lambda policy,phase:DockerCLI(policy))
   with self.assertRaises(Exception):factory(policy,p).run(['PUBLIC_NO_DOCKER'],timeout=2,cancel=p.stopped,max_bytes=65536,charge=p.charge)
   self.assertEqual(p.observed_bytes,131072)

if __name__=='__main__':unittest.main()
