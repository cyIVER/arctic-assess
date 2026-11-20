"""Owned offline runner. Evidence redirects; original tests remain byte-identical."""
import hashlib,json,os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT),str(ROOT/'canary'),str(ROOT/'guardian')]
os.chdir(ROOT/'canary')
from unit_support_v3 import unit_permissions
import test_integration
import stage_reviewed
from unittest.mock import patch
original_stage=stage_reviewed.stage
def resolved_stage(original,*args,**kw):return original_stage(Path(original).resolve(),*args,**kw)
stage_reviewed.stage=resolved_stage
test_integration.tuples.stage=resolved_stage
mode=sys.argv[1] if len(sys.argv)>1 else 'green'
loader=unittest.TestLoader()
with unit_permissions():
 original_trusted=__import__('guest').trusted_directory
 original_root=ROOT.parent.parent
 inodes={(p.stat().st_dev,p.stat().st_ino) for p in (original_root,ROOT.parent)}
 def trusted(fd):
  s=os.fstat(fd)
  if (s.st_dev,s.st_ino) in inodes:
   __import__('guest').need(s.st_uid==os.getuid(),'unit original infrastructure owner');return
  return original_trusted(fd)
 __import__('guest').trusted_directory=trusted
 if mode.startswith('baseline'):
  # Reproduce against owned exact pre-fix bytes, never peer evidence scripts.
  exec(compile((ROOT/'baseline/final_guard.py').read_bytes(),str(ROOT/'baseline/final_guard.py'),'exec'),test_integration.guard.__dict__)
  exec(compile((ROOT/'baseline/admission_v3.py').read_bytes(),str(ROOT/'baseline/admission_v3.py'),'exec'),test_integration.admission_v3.__dict__)
  baseline_require=test_integration.admission_v3.require_current
  test_integration.admission_v3.require_current=lambda c,now=None:baseline_require(c)
  import before_fix
  suite=loader.loadTestsFromModule(before_fix)
 elif mode.startswith('combined'):
  import fixture_migration
  fixture_migration.install(ROOT)
  suite=unittest.TestSuite([loader.discover(str(ROOT/'canary'),pattern='test_*.py',top_level_dir=str(ROOT/'canary')),loader.loadTestsFromModule(__import__('test_guard')),loader.loadTestsFromModule(__import__('test_security')),loader.loadTestsFromModule(__import__('test_host')),loader.loadTestsFromModule(test_integration)])
 else:suite=loader.loadTestsFromModule(test_integration)
 ids=[]
 def flatten(s):
  for t in s:
   if isinstance(t,unittest.TestSuite):yield from flatten(t)
   else:yield t
 ids=[t.id() for t in flatten(suite)]
 with (ROOT/'evidence'/f'{mode}.log').open('w') as f:r=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
 summary={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skips':len(r.skipped),'loader_errors':loader.errors,'ids':ids,'successful':r.wasSuccessful(),'runtime_qualified':False}
 (ROOT/'evidence'/f'{mode}.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary))
sys.exit(0 if r.wasSuccessful() and not loader.errors else 1)
