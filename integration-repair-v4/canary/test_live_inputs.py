import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from guest import HERE,VM,DAEMON,BASE,PINS,HELPER,validate_snapshot as validate,Blocked

class CurrentInputTests(unittest.TestCase):
 def fixture(self,d):
  d=Path(d);base=HERE.parent;iso=base/'artex-worker-isolation'
  def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
  names=['guest.py','driver.py','probes.py','fixture_service.py','reviewed_imports.py','image_stage.py','caller.go','vendor/runtime.py','vendor/lifecycle.py']
  own=d/'own.json';own.write_text(json.dumps({n:sha((HERE/n).resolve()) for n in names}));own.chmod(0o600)
  guard=d/'guard';guard.write_text('TEST_ONLY_NOT_AN_APPROVAL');guard.chmod(0o700)
  c={'schema':1,'lane':'literal-no-model-isolation','vm':VM,'created':1000,'deadline':1600,'guard_created':1000,'external_stop':2000,'budget_ceiling_usd':2,'spent_usd':.438629,'reserve_usd':.50,'daemon':DAEMON,'baseline_image':BASE,'root':'/run/artex-canary-0123456789ab','owner':{'socket_uid':os.getuid(),'socket_inode':1,'socket_device':0,'daemon_id':'test','docker_root':'/test'},'inventory':{'containers':['c'+str(i) for i in range(9)],'images':['i'+str(i) for i in range(44)],'volumes':['v'+str(i) for i in range(4)]},'isolation_root':str(iso),'caller':str(HERE/'caller'),'guard_status':str(guard),'fixture_module':str(base/'artex-owned-assessment-fixture/fixture.py'),'docker_cli':'/test/docker','python':'/usr/bin/python3','controller_id':'test-only'}
  # Test-only snapshots normalize modes without altering frozen original files.
  import shutil
  from stage_reviewed import stage
  staged=d/'isolation';stage(iso,staged)
  fixture=d/'fixture.py';shutil.copyfile(c['fixture_module'],fixture);fixture.chmod(0o644);c['fixture_module']=str(fixture)
  c['isolation_root']=str(staged)
  objects={'source':staged/'receipts/final-pins.json','host':staged/'receipts/final-pins.json','helper':staged/'receipts/artex-worker-tools-h2','orchestrator':own,'caller':Path(c['caller']),'guard':guard,'fixture':fixture}
  c['reviews']={}
  for kind,path in objects.items():
   h=sha(path);rp=d/(kind+'-review.json');rp.write_text(json.dumps({'status':'approved','kind':kind,'object_sha256':h,'vm':VM,'created':1000,'deadline':1600}));rp.chmod(0o600)
   c['reviews'][kind]={'path':str(path),'sha256':h,'review_path':str(rp),'review_sha256':sha(rp)}
  return c
 def test_actual_frozen_inventory_positive_readonly(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.fixture(d);self.assertIs(validate(c,1000),c)
   self.assertEqual(c['reviews']['source']['sha256'],PINS);self.assertEqual(c['reviews']['helper']['sha256'],HELPER)
   self.assertFalse(Path(c['root']).exists())
 def test_gate_rejects_current_schema_mutations(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.fixture(d)
   mutations=[('deadline',999),('created',1),('external_stop',1601),('daemon','unix:///var/run/docker.sock'),('baseline_image','artex:latest'),('spent_usd',1.8),('root','/tmp/not-owned'),('pause_default_service',True)]
   for key,value in mutations:
    with self.subTest(key=key),self.assertRaises(Blocked):validate(c|{key:value},1000)
 def test_missing_or_stale_reviews_deny(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.fixture(d)
   for name in c['reviews']:
    x=copy.deepcopy(c);del x['reviews'][name]
    with self.subTest(name=name),self.assertRaises(Blocked):validate(x,1000)
   x=copy.deepcopy(c);p=Path(x['reviews']['helper']['review_path']);r=json.loads(p.read_bytes());r['created']=900;p.write_text(json.dumps(r));x['reviews']['helper']['review_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
   with self.assertRaises(Blocked):validate(x,1000)
 def test_reviewed_imports_use_pinned_source(self):
  import reviewed_imports
  with tempfile.TemporaryDirectory() as d:
   c=self.fixture(d);validate(c,1000);reviewed_imports.load(c)
   from hostbroker.broker import Broker,Policy
   from lifecycle import WorkspaceQuota,Phase
   self.assertEqual(WorkspaceQuota.LIMIT,67108864)

if __name__=='__main__':unittest.main()
