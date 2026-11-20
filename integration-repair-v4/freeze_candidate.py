"""Owned deterministic freeze/report builder; no peer writes or execution."""
import ast,hashlib,json,platform,shutil,sys,difflib
from pathlib import Path
W=Path(__file__).resolve().parent;R=W.parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
prior=json.loads((W/'evidence/parents-before.json').read_text())
assert all(sha(R/n)==h for n,h in prior.items()),'parent drift'
save(W/'evidence/parents-after.json',{n:sha(R/n) for n in prior})
changed=[];test_preservation={};inherited=[]
for sub,base in [('canary','artex-worker-guest-canary-v3'),('guardian','artex-worker-live-guard-final')]:
 diff=''
 for p in sorted((W/sub).rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts:continue
  q=R/base/p.relative_to(W/sub)
  assert q.is_file(),str(q)
  if p.name.startswith('test_'):
   assert p.read_bytes()==q.read_bytes();test_preservation[str(p.relative_to(W))]=sha(p)
  if p.read_bytes()!=q.read_bytes():
   changed.append(str(p.relative_to(W)))
   diff+=''.join(difflib.unified_diff(q.read_text().splitlines(True),p.read_text().splitlines(True),fromfile=str(q.relative_to(R)),tofile=str(p.relative_to(W))))
 (W/'evidence'/f'{sub}-v4.diff').write_text(diff)
for p in sorted((R/'artex-worker-guest-canary-v2').glob('test_*.py')):
 assert (W/'canary'/p.name).read_bytes()==p.read_bytes()
 for cls in ast.parse(p.read_text()).body:
  if isinstance(cls,ast.ClassDef):
   inherited.extend(p.stem+'.'+cls.name+'.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
assert len(inherited)==37
summary=json.loads((W/'evidence/combined-final.json').read_text())
assert summary['tests']==92 and summary['successful'] and not summary['loader_errors'] and not summary['skips']
assert set(inherited)<=set(summary['ids'])
canary_ids=[i for i in summary['ids'] if not i.startswith(('test_guard.','test_security.','test_host.','test_integration.'))]
assert len(canary_ids)==54
scope=next(n.value for n in ast.parse((W/'canary/driver.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALL_REQUIRED_CASES' for t in n.targets))
driver=ast.parse((W/'canary/driver.py').read_text());sets={}
for n in driver.body:
 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('REQUIRED_CASES','ALL_REQUIRED_CASES'):
  sets[n.targets[0].id]=ast.literal_eval(n.value) if isinstance(n.value,ast.Set) else sets[n.value.left.id]|ast.literal_eval(n.value.right)
assert len(sets['ALL_REQUIRED_CASES'])==17
functions=[]
for p in [W/'canary/admission_v3.py',W/'guardian/guard.py']:
 functions.append(ast.dump(next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='validate_checkpoint')))
assert functions[0]==functions[1]
preservation={'parent_files_unchanged':len(prior),'changed_production_files':changed,'test_file_hashes':test_preservation,'inherited37_ids':inherited,'canary54_ids':canary_ids,'runtime17_cases':sorted(sets['ALL_REQUIRED_CASES']),'runtime_cases_executed':0,'contract_AST_identical':True,'free_disk_bytes':shutil.disk_usage(W).free}
save(W/'evidence/preservation.json',preservation)
source={}
for p in sorted(W.rglob('*')):
 if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts:continue
 rel=p.relative_to(W)
 if rel.parts[0] in ('evidence','host-scratch') or rel.name in ('FREEZE.json','source-identity.json','report.json'):continue
 source[str(rel)]=sha(p)
save(W/'source-identity.json',source)
report={'status':'LOCAL_CANDIDATE_FOR_INDEPENDENT_REVIEW','live_admission':'BLOCKED','runtime_qualified':False,'tests':summary,'breakdown':{'canary_preserved':54,'v2_inherited_subset':37,'original_guard':20,'final_host':12,'integrated':6},'source_identity_sha256':sha(W/'source-identity.json'),'guard_base_sha256':sha(W/'baseline/final_guard.py'),'guard_candidate_sha256':sha(W/'guardian/guard.py'),'preservation':preservation,'python':sys.version,'executable':sys.executable,'rerun_command':'PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/iveri/.hermes/cache/scratch/v4-local-1119 /usr/bin/python3 -B '+str(W/'run_tests.py')+' combined-independent','issues':'Initial setup/fixture/collector issues retained in REPORT.md and evidence; final run zero setup/collection issues. No privileged/runtime evidence.'}
save(W/'report.json',report)
evidence={str(p.relative_to(W)):sha(p) for p in sorted((W/'evidence').iterdir()) if p.is_file()}
save(W/'FREEZE.json',{'schema':1,'status':'FROZEN_LOCAL_NOT_APPROVED','source_identity':{'path':'source-identity.json','sha256':sha(W/'source-identity.json')},'source':source,'evidence':evidence,'report_sha256':sha(W/'report.json'),'report_md_sha256':sha(W/'REPORT.md')})
print(json.dumps({'tests':summary['tests'],'failures':summary['failures'],'errors':summary['errors'],'skips':summary['skips'],'source_identity_sha256':sha(W/'source-identity.json'),'freeze_sha256':sha(W/'FREEZE.json'),'candidate_guard_sha256':sha(W/'guardian/guard.py'),'parent_unchanged':len(prior),'changed':changed,'free_bytes':shutil.disk_usage(W).free}))
