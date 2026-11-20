"""Independent real-validator negatives; no production monkeypatch or external commands."""
from pathlib import Path
import copy,hashlib,json,os,sys,tempfile
from unittest.mock import patch
SOURCE=Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/integration-repair-v4')
OWN=Path(__file__).resolve().parent
scratch=tempfile.mkdtemp(prefix='iv4p-',dir='/home/iveri/.hermes/cache/scratch')
os.environ['TMPDIR']=scratch;tempfile.tempdir=scratch
sys.dont_write_bytecode=True
sys.path[:0]=[str(SOURCE),str(SOURCE/'canary'),str(SOURCE/'guardian')]
import guest,guard,admission_v3,test_integration as t,stage_reviewed
from unit_support_v3 import unit_permissions
real_stage=stage_reviewed.stage
def stage(p,*a,**kw):return real_stage(Path(p).resolve(),*a,**kw)
stage_reviewed.stage=stage;t.tuples.stage=stage
results=[]
with unit_permissions():
 old=guest.trusted_directory
 exempt={(p.stat().st_dev,p.stat().st_ino) for p in (SOURCE.parent,SOURCE.parent.parent)}
 def trust(fd):
  s=os.fstat(fd)
  if (s.st_dev,s.st_ino) in exempt:guest.need(s.st_uid==os.getuid(),'owned infrastructure');return
  return old(fd)
 with patch.object(guest,'trusted_directory',trust),tempfile.TemporaryDirectory() as d:
  c,context,a=t.tuples.fixture(d);good=t.merged(c)
  with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
   raw=t.bind(c,context,a,good);assert guest.validate(c,1000) is c
   inv,calls,reads=t.inventory(c,raw);assert inv['checkpoint_sha256']==guard.digest(raw)
   results.append({'case':'same_real_entrypoints_positive','sha256':guard.digest(raw),'path':c['preflight']['path'],'commands':len([x for x in calls if x[0]=='command'])})
   variants=[('missing-'+k,{j:v for j,v in good.items() if j!=k}) for k in good]
   variants += [('extra',good|{'x':0}),('inventory-extra',good|{'default_inventory':good['default_inventory']|{'x':[]}}),('schema-bool',good|{'schema':True}),('created-bool',good|{'created':True}),('deadline-bool',good|{'deadline':True}),('stop-bool',good|{'external_stop':True}),('created-nan',good|{'created':float('nan')}),('created-infinity',good|{'created':float('inf')}),('old-status',good|{'status':'READY'}),('lease-wrong',good|{'parent_scope_lease':'other'}),('owner-wrong',good|{'default_service_changes_owner':'worker'}),('vm-wrong',good|{'vm':guard.VM|{'id':'other'}}),('inventory-nonempty',good|{'default_inventory':{'containers':[],'images':['unexpected'],'volumes':[]}})]
   for name,p in variants:
    # Serialize deliberately invalid nonfinite values with permissive encoder,
    # then re-pin raw bytes/context so rejection is semantic, not stale hash.
    if name in ('created-nan','created-infinity'):
     raw=json.dumps(p,sort_keys=True).encode();pf=Path(c['preflight']['path']);pf.write_bytes(raw);c['preflight']['sha256']=guard.digest(raw);a['preflight']=copy.deepcopy(c['preflight']);a['config_sha256']=admission_v3.canonical(c);context.write_bytes(guard.canonical(a))
    else:raw=t.bind(c,context,a,p)
    denied=[];external=[]
    try:guest.validate(c,1000)
    except guest.Blocked:denied.append('canary')
    def forbidden(argv,timeout):external.append(argv);raise AssertionError('invalid checkpoint reached command seam')
    try:guard.guest_inventory(c,runner=forbidden,clock=lambda:1000,read=lambda path,sha:raw)
    except (guard.Blocked,KeyError,TypeError,ValueError):denied.append('guardian')
    assert denied==['canary','guardian'] and not external,(name,denied,external)
    results.append({'case':name,'denied':denied,'commands':0})
   raw=t.bind(c,context,a,good)
   for now in (999,1121,1600):
    for name,fn in [('canary',lambda:guest.validate(c,now)),('guardian',lambda:guard.guest_inventory(c,runner=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('external')),clock=lambda:now,read=lambda *a:raw))]:
     try:fn()
     except (guest.Blocked,guard.Blocked):results.append({'case':'time-'+str(now),'validator':name,'denied':True})
     else:raise AssertionError(('bad time accepted',now,name))
   # Prove root-projected actual guardian protected read consumes same file/pin,
   # not only the injected reader used by contract tests.
   real=os.fstat
   def metadata(fd):
    s=real(fd);v=list(s);v[4]=0
    if __import__('stat').S_ISDIR(s.st_mode):v[0]&=~0o022
    return os.stat_result(v)
   with patch.object(guard.os,'fstat',side_effect=metadata):assert guard.protected(c['preflight']['path'],c['preflight']['sha256'])==raw
   results.append({'case':'actual_guardian_protected_same_path_hash','passed':True,'synthetic_root':True})
(OWN/'supplemental.json').write_text(json.dumps({'results':results,'runtime_qualified':False,'all_passed':True},indent=2)+'\n')
print(json.dumps({'all_passed':True,'records':len(results),'runtime_qualified':False}))
