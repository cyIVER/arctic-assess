"""UNIT_ONLY admitted tuple fixture. Never approval, guard proof, or activation."""
import copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import guest,admission_v3
import test_live_inputs as legacy
from stage_reviewed import stage

def fixture(d):
 d=Path(d);c=legacy.CurrentInputTests().fixture(d)
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 iso=d/'bundle654';stage(guest.HERE.parent/'artex-worker-canary-bundle',iso,'85aef1698ef86d928f4767efcf6754cde410eef959c1bb290340463600e25206',admission_v3.HELPER_SHA)
 c.update(isolation_root=str(iso),source_profile='reviewed-environment-proxy-v3',manifest_counts={'source':654,'host':11})
 lease={'handle':'UNIT_ONLY_NOT_AUTHORITY','vm':c['vm'],'lane':c['lane'],'created':c['created'],'deadline':c['deadline']};c['parent_scope_lease']=lease
 for k in ('source','host'):c['reviews'][k].update(path=str(iso/'receipts/final-pins.json'),sha256=sha(iso/'receipts/final-pins.json'))
 c['reviews']['helper'].update(path=str(iso/'receipts/artex-worker-tools-h2'),sha256=admission_v3.HELPER_SHA)
 own=Path(c['reviews']['orchestrator']['path']);names=json.loads(own.read_bytes());names.update({k:'' for k in ('admission_v3.py','v2_cases.py','restart_probe.py','bounded_transport.py')});own.write_text(json.dumps({n:sha(guest.HERE/n) for n in names}));c['reviews']['orchestrator']['sha256']=sha(own)
 for kind,v in c['reviews'].items():
  p=Path(v['review_path']);p.write_text(json.dumps({'status':'approved','kind':kind,'object_sha256':v['sha256'],'vm':c['vm'],'created':c['created'],'deadline':c['deadline'],'parent_scope_lease':lease['handle'],'code_review_handle':'UNIT_ONLY_NOT_REVIEW'}));p.chmod(0o600);v['review_sha256']=sha(p)
 pf=d/'preflight.json';pf.write_text(json.dumps({'status':'verified','requirement':'already-private-default-quiescent','vm':c['vm'],'created':c['created'],'deadline':c['deadline'],'parent_scope_lease':lease['handle'],'default_service_changes_owner':'parent'}));pf.chmod(0o600);c['preflight']={'path':str(pf),'sha256':sha(pf)}
 a={k:copy.deepcopy(c[k]) for k in ('vm','lane','created','deadline','external_stop','guard_created','controller_id','parent_scope_lease','reviews','preflight')};a.update(schema=1,config_sha256=admission_v3.canonical(c),guardian_implementation={'path':c['guard_status'],'sha256':sha(c['guard_status'])})
 for key,obj in (('guardian_review',a['guardian_implementation']),('orchestrator_review',c['reviews']['orchestrator'])):
  p=d/(key+'.json');p.write_text(json.dumps({'verdict':'SCOPED_PASS','object_sha256':obj['sha256'],'scope':'UNIT_ONLY_NOT_REVIEW'}));p.chmod(0o600);a[key]={'path':str(p),'sha256':sha(p)}
 # UNIT_ONLY existing ELF is never launched as Docker/Python by this fixture.
 c['docker_cli']=c['caller'];c['python']=c['caller'];a['runtime_executables']={k:{'path':c[k],'sha256':sha(c[k])} for k in ('docker_cli','python')};a['config_sha256']=admission_v3.canonical(c)
 context=d/'context.json';context.write_text(json.dumps(a));context.chmod(0o600)
 return c,context,a

class ProtectedTupleTests(unittest.TestCase):
 def test_unit_only_positive_and_owning_context_required(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=fixture(d)
   with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
    self.assertIs(guest.validate(c,1000),c)
    with patch.object(admission_v3,'PARENT_CONTEXT',str(Path(d)/'NOT_INSTALLED')):
     with self.assertRaises(guest.Blocked):guest.validate(c,1000)
    for field,value in [('schema',True),('spent_usd',True),('external_stop',True)]:
     with self.subTest(field=field),self.assertRaises(guest.Blocked):guest.validate(c|{field:value},1000)
    context.chmod(0o666)
    with self.assertRaises(guest.Blocked):guest.validate(c,1000)
 def test_canonical_maps_not_raw_manifest_whitespace_and_concrete_helper(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=fixture(d)
   with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
    self.assertIs(guest.validate(c,1000),c)
    for k in ('source','host'):
     p=Path(c['reviews'][k]['path']);m=json.loads(p.read_bytes());self.assertEqual(admission_v3.canonical(m),admission_v3.CANONICAL_MAP_SHA)
    manifest=Path(c['reviews']['source']['path']);manifest.write_bytes(manifest.read_bytes()+b'\n')
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    for k in ('source','host'):
     c['reviews'][k]['sha256']=digest
     rp=Path(c['reviews'][k]['review_path']);report=json.loads(rp.read_bytes());report['object_sha256']=digest;rp.write_text(json.dumps(report));c['reviews'][k]['review_sha256']=hashlib.sha256(rp.read_bytes()).hexdigest()
    a['reviews']=copy.deepcopy(c['reviews']);a['config_sha256']=admission_v3.canonical(c);context.write_text(json.dumps(a))
    self.assertIs(guest.validate(c,1000),c) # actual canonical-whitespace positive
    bad=Path(d)/'bad-helper';bad.write_bytes(b'ARBITRARY_NONEXECUTABLE');bad.chmod(0o600)
    c['reviews']['helper'].update(path=str(bad),sha256=hashlib.sha256(bad.read_bytes()).hexdigest())
    with self.assertRaisesRegex(guest.Blocked,'concrete helper pin'):guest.validate(c,1000)
 def test_guardian_and_orchestrator_reports_mandatory(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=fixture(d)
   with patch.object(admission_v3,'PARENT_CONTEXT',str(context)):
    self.assertIs(guest.validate(c,1000),c)
    originals={k:Path(a[k]['path']).read_bytes() for k in ('guardian_review','orchestrator_review')}
    for kind in ('guardian_review','orchestrator_review'):
     for k,bits in originals.items():Path(a[k]['path']).write_bytes(bits)
     b=copy.deepcopy(a);p=Path(b[kind]['path']);p.write_text(json.dumps({'verdict':'BLOCKED','object_sha256':a['guardian_implementation']['sha256']}));b[kind]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();context.write_text(json.dumps(b))
     with self.subTest(kind=kind),self.assertRaises(guest.Blocked):guest.validate(c,1000)
if __name__=='__main__':unittest.main()
