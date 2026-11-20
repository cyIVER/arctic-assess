"""Independent output-redirected runner; frozen candidate is read-only."""
import hashlib,json,os,sys,unittest
from pathlib import Path
ROOT=Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation')
OUT=ROOT/'coordination-20261119/gate-canary-review-retry'
SRC=ROOT/'artex-worker-guest-canary-v3'
sys.dont_write_bytecode=True
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['TMPDIR']='/home/iveri/.hermes/cache/scratch'
os.chdir(SRC);sys.path.insert(0,str(SRC))
from unit_support_v3 import unit_permissions
loader=unittest.TestLoader()
with unit_permissions():
 suite=loader.discover(str(SRC),pattern='test_*.py')
 def flatten(s):
  for t in s:
   if isinstance(t,unittest.TestSuite):yield from flatten(t)
   else:yield t.id()
 ids=list(flatten(suite))
 with (OUT/'local-tests.log').open('w') as f:
  result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),'collection_errors':loader.errors,'successful':result.wasSuccessful(),'test_ids':ids,'runtime_proof':False,'scope':'UNIT_ONLY metadata substitutions; actual owned processes/UDS/SDK; fake Docker; no UID changes'}
(OUT/'local-tests.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='test_ids'}))
sys.exit(0 if result.wasSuccessful() and not loader.errors else 1)
