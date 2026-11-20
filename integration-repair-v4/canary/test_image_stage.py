import json
import os
from pathlib import Path
import tempfile
import unittest
from guest import HERE,VM,BASE,HELPER,DAEMON,Blocked
from image_stage import derive

class BuildCLI:
 def __init__(self,root,existing=False,badvolumes=False):self.root=root;self.events=[];self.existing=existing;self.badvolumes=badvolumes
 def run(self,argv,**kw):
  self.events.append({'argv':argv})
  if argv==['/owned/guard','--status']:return json.dumps({'alive':True,'provider_state':'RUNNING','vm':VM,'stop_at':2000,'controller_id':'test','guard_created':1000}).encode()
  args=argv[3:]
  if args[:2]==['image','ls']:return b'old' if self.existing else b''
  if args==['image','inspect',BASE]:return b'[]'
  if args[0]=='build':
   assert '--pull=false' in args and '--network=none' in args
   Path(args[args.index('--iidfile')+1]).write_text('sha256:'+'a'*64)
   return b'fake-build-not-runtime-proof'
  if args[:2]==['image','inspect']:
   return json.dumps([{'Id':'sha256:'+'a'*64,'Config':{'User':'1001:1002','Volumes':{'/unknown':{}} if self.badvolumes else {'/app/data':{}}}}]).encode()
  raise AssertionError(argv)

class ImageStageTests(unittest.TestCase):
 def setup_fixture(self,d):
  d=Path(d);root=d/'artex-canary-0123456789ab';root.mkdir()
  helper=d/'helper';helper.write_bytes((HERE.parent/'artex-worker-isolation/receipts/artex-worker-tools-h2').read_bytes());helper.chmod(0o555)
  c={'reviews':{'helper':{'path':str(helper),'sha256':HELPER}},'docker_cli':'/owned/docker','daemon':DAEMON,'deadline':1600,'external_stop':2000,'guard_status':'/owned/guard','controller_id':'test','guard_created':1000}
  return root,c
 def test_actual_staging_fake_build_positive(self):
  with tempfile.TemporaryDirectory() as d:
   root,c=self.setup_fixture(d);r=BuildCLI(root);v=derive(c,r,root,clock=lambda:1000)
   self.assertEqual(v['id'],'sha256:'+'a'*64)
   self.assertEqual((root/'build'/'artex-worker-tools').read_bytes(),Path(c['reviews']['helper']['path']).read_bytes())
   self.assertEqual(len([x for x in r.events if 'build' in x['argv']]),1)
 def test_existing_tag_denied_before_build(self):
  with tempfile.TemporaryDirectory() as d:
   root,c=self.setup_fixture(d);r=BuildCLI(root,existing=True)
   with self.assertRaises(Blocked):derive(c,r,root,clock=lambda:1000)
   self.assertEqual(len(r.events),1)
 def test_bad_inherited_volumes_denied_after_readback(self):
  with tempfile.TemporaryDirectory() as d:
   root,c=self.setup_fixture(d);r=BuildCLI(root,badvolumes=True)
   with self.assertRaises(Blocked):derive(c,r,root,clock=lambda:1000)
   self.assertEqual(len([x for x in r.events if 'build' in x['argv']]),1)

if __name__=='__main__':unittest.main()
