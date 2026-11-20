"""Read-only byte/domain/preservation verifier; own receipt only."""
from pathlib import Path
import ast,difflib,hashlib,json,shutil,stat
OWN=Path(__file__).resolve().parent;W=OWN.parent/'integration-repair-v4';R=W.parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((OWN/'before.json').read_bytes())
def tree(p):return {str(f.relative_to(p)):{'sha256':sha(f),'size':f.stat().st_size,'mode':stat.S_IMODE(f.stat().st_mode)} for f in sorted(p.rglob('*')) if f.is_file() and not f.is_symlink()}
after=tree(W);assert after==before['candidate'],'candidate changed'
assert {str(p.relative_to(W)):str(p.resolve()) for p in W.rglob('*') if p.is_symlink()}==before['links']
parents={n:sha(R/n) for n in before['parents']};assert parents==before['parents'],'parent changed'
parents_historical=json.loads((W/'evidence/parents-after.json').read_bytes());assert parents==parents_historical
freeze=json.loads((W/'FREEZE.json').read_bytes());identity=json.loads((W/'source-identity.json').read_bytes())
assert identity==freeze['source']
for group in ('source','evidence'):
 for n,h in freeze[group].items():assert sha(W/n)==h
assert sha(W/'report.json')==freeze['report_sha256'];assert sha(W/'REPORT.md')==freeze['report_md_sha256']
# Independently derive whole candidate delta against latest bases, tests included.
diff='';changed=[];unchanged=[];missing=[]
for sub,parent in [('canary','artex-worker-guest-canary-v3'),('guardian','artex-worker-live-guard-final')]:
 candidates={str(p.relative_to(W/sub)):p for p in (W/sub).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 for n,p in candidates.items():
  q=R/parent/n;assert q.is_file()
  if sha(p)==sha(q):unchanged.append(sub+'/'+n)
  else:
   changed.append(sub+'/'+n);diff+=''.join(difflib.unified_diff(q.read_text().splitlines(True),p.read_text().splitlines(True),fromfile=parent+'/'+n,tofile=sub+'/'+n))
 # Candidate intentionally imports selected executable/test inventory, not parent docs/receipts.
 missing.extend(parent+'/'+str(p.relative_to(R/parent)) for p in (R/parent).rglob('*') if p.is_file() and '__pycache__' not in p.parts and str(p.relative_to(R/parent)) not in candidates)
assert set(changed)=={'canary/admission_v3.py','canary/guest.py','guardian/guard.py'}
(OWN/'reviewed.diff').write_text(diff)
functions=[]
for p in [W/'canary/admission_v3.py',W/'guardian/guard.py']:functions.append(ast.dump(next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='validate_checkpoint')))
assert functions[0]==functions[1]
# Source domain: raw manifest vs canonical map vs actual source/host bytes.
bundle=R/'artex-worker-canary-bundle';manifest=bundle/'receipts/final-pins.json';m=json.loads(manifest.read_bytes())
canon=hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
assert canon=='fe8a0c7e2df6e44b343cc2d77e5cce8df8fb64575c958f277ede1042feea279b'
assert len(m['source'])==654 and len(m['host'])==11
for group in ('source','host'):
 for n,h in m[group].items():assert sha(bundle/group/n)==h
assert sha(manifest)=='85aef1698ef86d928f4767efcf6754cde410eef959c1bb290340463600e25206'
assert sha(bundle/'receipts/artex-worker-tools-h2')=='ea54b361fed9d575eaadcd069b59382d853c241abee4821dbd7f02f4fac765ac'
assert sha(R/'artex-owned-assessment-fixture/fixture.py')=='49e1f487b407ebff7bf0d79f5f2e6137b38d6955c4c1ca1e9a4becb15e20a08d'
summary=json.loads((OWN/'evidence/combined-review-final.json').read_bytes());assert summary['successful'] and summary['tests']==92 and not any(summary[k] for k in ('errors','failures','skips','loader_errors'))
ids=summary['ids'];assert len(ids)==len(set(ids))==92
breakdown={'canary':sum(not i.startswith(('test_guard.','test_security.','test_host.','test_integration.')) for i in ids),'original_guard':sum(i.startswith(('test_guard.','test_security.')) for i in ids),'final_host':sum(i.startswith('test_host.') for i in ids),'integrated':sum(i.startswith('test_integration.') for i in ids)}
assert breakdown=={'canary':54,'original_guard':20,'final_host':12,'integrated':6}
inherited=[]
for p in (R/'artex-worker-guest-canary-v2').glob('test_*.py'):
 assert p.read_bytes()==(W/'canary'/p.name).read_bytes()
 for cls in ast.parse(p.read_text()).body:
  if isinstance(cls,ast.ClassDef):inherited.extend(p.stem+'.'+cls.name+'.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
assert len(inherited)==37 and set(inherited)<=set(ids)
cases={}
for n in ast.parse((W/'canary/driver.py').read_text()).body:
 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('REQUIRED_CASES','ALL_REQUIRED_CASES'):cases[n.targets[0].id]=ast.literal_eval(n.value) if isinstance(n.value,ast.Set) else cases[n.value.left.id]|ast.literal_eval(n.value.right)
assert len(cases['ALL_REQUIRED_CASES'])==17
report={'source_identity_sha256':sha(W/'source-identity.json'),'freeze_sha256':sha(W/'FREEZE.json'),'guard_sha256':sha(W/'guardian/guard.py'),'source_count':len(identity),'evidence_count':len(freeze['evidence']),'candidate_all_regular_files_before_after_identical':after==before['candidate'],'candidate_symlinks_preserved':before['links'],'parent_files_unchanged':len(parents),'parent_maps_before_after_equal':True,'changed_production':changed,'unchanged_candidate_members':unchanged,'not_copied_parent_members':missing,'canonical_manifest_sha256':canon,'raw_manifest_sha256':sha(manifest),'source_members_verified':654,'host_members_verified':11,'contract_AST_equal':True,'test_breakdown':breakdown,'inherited37_preserved':inherited,'required_guest_cases':sorted(cases['ALL_REQUIRED_CASES']),'guest_cases_executed':0,'runtime_qualified':False,'free_disk_bytes':shutil.disk_usage(OWN).free,'candidate_after':after,'parents_after':parents}
(OWN/'verification.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
assert json.loads((OWN/'verification.json').read_text())==report
print(json.dumps({k:v for k,v in report.items() if k not in ('candidate_after','parents_after','unchanged_candidate_members','not_copied_parent_members','inherited37_preserved','required_guest_cases')}))
