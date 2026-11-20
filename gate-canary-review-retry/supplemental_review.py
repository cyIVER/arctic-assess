"""LOCAL-only seam reproduction and FD binding; no live guardian call."""
import hashlib,importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
R=Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation');S=R/'artex-worker-guest-canary-v3';O=R/'coordination-20261119/gate-canary-review-retry'
sys.dont_write_bytecode=True;sys.path.insert(0,str(S));os.chdir(S)
import guest,admission_v3,driver
spec=importlib.util.spec_from_file_location('review_guard',R/'artex-worker-live-guard-final/guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
results={}
# Exactly the checkpoint bytes canary requires. Guardian fails before its runner.
p={'status':'verified','requirement':'already-private-default-quiescent','vm':guest.VM,'created':1000,'deadline':1600,'parent_scope_lease':'UNIT_ONLY','default_service_changes_owner':'parent'}
raw=json.dumps(p).encode();calls=[]
def forbidden(*a,**kw):calls.append(a);raise AssertionError('external runner forbidden')
try:g.guest_inventory({'preflight':{'path':'/NOT_READ','sha256':hashlib.sha256(raw).hexdigest()},'external_stop':2000},runner=forbidden,clock=lambda:1000,read=lambda *a,**kw:raw);error=None
except Exception as e:error={'type':type(e).__name__,'reason':str(e)}
assert error=={'type':'Blocked','reason':'preflight stale/scope'} and calls==[]
results['guardian_checkpoint_seam']={'checkpoint':p,'guardian_result':error,'runner_calls':0,'canary_requires_exact_verified_object':True,'guardian_requires_READY_plus_default_inventory_external_stop':True,'compatible':False}
# Archive pathname replacement must not influence returned FD readback hash.
with tempfile.TemporaryDirectory() as d:
 d=Path(d);w=d/'work';w.mkdir();(w/'valuable').write_bytes(b'ORIGINAL');a=d/'archive.tar';real=os.fsync;swapped=[]
 def fsync(fd):
  real(fd)
  if not swapped and a.exists() and os.fstat(fd).st_ino==a.stat().st_ino:
   a.rename(d/'held.tar');a.write_bytes(b'REPLACEMENT');swapped.append(True)
 with patch('guest.os.fsync',side_effect=fsync):v=guest.checkpoint(w,a)
 assert v['archive_sha256']==hashlib.sha256((d/'held.tar').read_bytes()).hexdigest()
 assert v['archive_sha256']!=hashlib.sha256(a.read_bytes()).hexdigest()
 results['archive_hash_consumes_original_fd']={'passed':True,'pathname_swapped':True,'note':'Returned hash describes opened archive object; protected parent/no-writer invariant still required for final pathname.'}
r=subprocess.run([sys.executable,'-B',str(S/'replay_review_v3.py')],capture_output=True,text=True,env=os.environ|{'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':'/home/iveri/.hermes/cache/scratch'},timeout=90)
(O/'review-replay.log').write_text(r.stdout+r.stderr);assert r.returncode==0
results['review_replay']={'returncode':r.returncode,'result':json.loads(r.stdout)}
r=subprocess.run([sys.executable,'-B',str(S/'driver.py')],capture_output=True,text=True,timeout=5);assert r.returncode==2 and json.loads(r.stdout)['status']=='BLOCKED'
results['default_cli']={'returncode':r.returncode,'stdout':json.loads(r.stdout),'stderr':r.stderr}
import ast
old=set()
for p in (R/'artex-worker-guest-canary-v2').glob('test_*.py'):
 for n in ast.walk(ast.parse(p.read_text())):
  if isinstance(n,ast.ClassDef):
   for f in n.body:
    if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'):old.add(p.stem+'.'+n.name+'.'+f.name)
actual=set(json.loads((O/'local-tests.json').read_bytes())['test_ids'])
results['inventory']={'old_tests':len(old),'new_collected':len(actual),'old_missing':sorted(old-actual),'required_guest_cases':sorted(driver.ALL_REQUIRED_CASES),'required_guest_count':len(driver.ALL_REQUIRED_CASES),'guest_executed':0}
assert not old-actual and len(old)==37 and len(actual)==54 and len(driver.ALL_REQUIRED_CASES)==17
(O/'supplemental-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
