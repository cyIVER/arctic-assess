"""Concrete artifact tuple plus protected parent-installed scoped authority."""
import hashlib,json,os,stat
from pathlib import Path
import guest
from guest import need,pinned
PARENT_CONTEXT='/run/artex-parent/run-context.json'
CANONICAL_MAP_SHA='fe8a0c7e2df6e44b343cc2d77e5cce8df8fb64575c958f277ede1042feea279b'
HELPER_SHA='ea54b361fed9d575eaadcd069b59382d853c241abee4821dbd7f02f4fac765ac'
CALLER_SHA='7f9a360e2925e2bfaa257ce8975ac344e9e4f2ddfec879d5d0991821c22ba746'
FIXTURE_SHA='49e1f487b407ebff7bf0d79f5f2e6137b38d6955c4c1ca1e9a4becb15e20a08d'
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def protected_json(path):
    need(isinstance(path,str) and Path(path).is_absolute() and str(Path(path))==path and '..' not in Path(path).parts,'protected JSON path')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        guest.trusted_directory(fd)
        for part in Path(path).parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt;guest.trusted_directory(fd)
        leaf=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            s=os.fstat(leaf)
            need(stat.S_ISREG(s.st_mode) and s.st_uid==guest.TRUSTED_UID and not s.st_mode&0o077 and s.st_nlink==1 and s.st_size<=1048576,'protected JSON owner/mode/type/size')
            with os.fdopen(leaf,'rb',closefd=False) as f:raw=f.read(1048577)
            need(len(raw)<=1048576,'protected JSON cap')
            return json.loads(raw)
        finally:os.close(leaf)
    finally:os.close(fd)
def require_current(c):
    need(c.get('source_profile')=='reviewed-environment-proxy-v3','concrete proxy654 profile required')
    h=c['reviews'];need(h['host']['sha256']==h['source']['sha256'],'single source+host manifest')
    manifest=json.loads(pinned(h['source']['path'],h['source']['sha256']))
    need(canonical(manifest)==CANONICAL_MAP_SHA and c['manifest_counts']=={'source':654,'host':11},'canonical proxy654/host11 maps required')
    need(all(type(x) is int for x in c['manifest_counts'].values()),'strict manifest counts')
    for kind,digest in (('helper',HELPER_SHA),('caller',CALLER_SHA),('fixture',FIXTURE_SHA)):
        need(h[kind]['sha256']==digest,'concrete '+kind+' pin')
        pinned(h[kind]['path'],digest,executable=kind!='fixture',elf=kind!='fixture')
    # No config-selected authority path. Parent alone installs this root-owned
    # run-context after deriving the typed lease from standing authority.
    authority=protected_json(PARENT_CONTEXT)
    need(type(authority['schema']) is int and authority['schema']==1,'parent context schema')
    need(authority['config_sha256']==canonical(c),'parent exact config binding')
    need(authority['guardian_implementation']=={'path':h['guard']['path'],'sha256':h['guard']['sha256']},'executed guardian source binding')
    fields=('vm','lane','created','deadline','external_stop','guard_created','controller_id','parent_scope_lease','reviews','preflight')
    need(all(authority[k]==c[k] and type(authority[k]) is type(c[k]) for k in fields),'parent-installed scoped authority binding')
    lease=c['parent_scope_lease']
    need(set(lease)=={'handle','vm','created','deadline','lane'} and type(lease['handle']) is str and 0<len(lease['handle'])<=256,'typed parent lease')
    need(all(lease[k]==c[k] and type(lease[k]) is type(c[k]) for k in ('vm','created','deadline','lane')),'lease scope')
    for object_kind,report_kind in (('guardian_implementation','guardian_review'),('orchestrator','orchestrator_review')):
        obj=authority[object_kind] if object_kind!='orchestrator' else h['orchestrator']
        pinned(obj['path'],obj['sha256'])
        ref=authority[report_kind];review=json.loads(pinned(ref['path'],ref['sha256'],1048576))
        need(review.get('verdict') in ('PASS','SCOPED_PASS') and review.get('object_sha256')==obj['sha256'],'actual independent '+object_kind+' report')
    pinned(h['guard']['path'],h['guard']['sha256'],executable=True)
    for name in ('docker_cli','python'):
        pin=authority['runtime_executables'][name];need(pin['path']==c[name],'parent executable binding')
        pinned(pin['path'],pin['sha256'],executable=True,elf=True)
    for kind,v in h.items():
        review=json.loads(pinned(v['review_path'],v['review_sha256']))
        need(review.get('parent_scope_lease')==lease['handle'],'report lease binding')
        need(type(review.get('code_review_handle')) is str and bool(review['code_review_handle']),'report reference missing')
    pf=c['preflight'];checkpoint=json.loads(pinned(pf['path'],pf['sha256']))
    need(all(type(checkpoint.get(k)) in (int,float) for k in ('created','deadline')),'strict preflight timestamps')
    need(checkpoint=={'status':'verified','requirement':'already-private-default-quiescent','vm':c['vm'],'created':c['created'],'deadline':c['deadline'],'parent_scope_lease':lease['handle'],'default_service_changes_owner':'parent'},'parent preflight checkpoint')
    return checkpoint
