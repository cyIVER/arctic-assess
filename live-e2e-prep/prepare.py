#!/usr/bin/python3
"""Local-only immutable v4 staging. Does not confer runtime authority."""
import hashlib,json,os,stat,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
COORD=HERE.parent
CONT=COORD.parent
V4=COORD/'integration-repair-v4'
IDENTITY='7b8b8ff769df40567bcf252f0747809be8a8d0e9edce6bcce0069e9a056de0b5'
REVIEW='fbf73ccc6ea879b73b319744774d8692caa5776358ad48e7f196e057adee496d'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def read(p,digest):
    p=Path(p)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
        f=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    finally:os.close(fd)
    try:
        s=os.fstat(f)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>134217728:raise ValueError('unsafe input')
        with os.fdopen(f,'rb',closefd=False) as inp:b=inp.read(134217729)
        if sha(b)!=digest:raise ValueError('source drift: '+str(p))
        return b
    finally:os.close(f)
def write(p,b,mode=0o600):
    p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with p.open('xb') as out:os.fchmod(out.fileno(),mode);out.write(b);out.flush();os.fsync(out.fileno())
def bundle(original,destination,pin,helper):
    raw=read(original/'receipts/final-pins.json',pin);m=json.loads(raw)
    for group in ('host','source'):
        for name,digest in m[group].items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('bundle path')
            write(destination/group/name,read(original/group/name,digest),0o644)
    write(destination/'receipts/final-pins.json',raw)
    write(destination/'receipts/artex-worker-tools-h2',read(original/'receipts/artex-worker-tools-h2',helper),0o555)
    return m
def prepare(destination):
    destination=Path(destination)
    if destination.parent!=HERE or destination.exists():raise ValueError('fresh owned-lane destination required')
    identities=json.loads(read(V4/'source-identity.json',IDENTITY))
    report=read(COORD/'integration-v4-independent-review/report.json',REVIEW)
    # Validate the complete frozen hash base before writing anything.
    for name,digest in identities.items():read(V4/name,digest)
    destination.mkdir(mode=0o700)
    own={}
    for name,digest in identities.items():
        if name.startswith('canary/') and not Path(name).name.startswith('test_') and (name.endswith('.py') or name.endswith('.go')):
            rel=name.removeprefix('canary/');write(destination/name,read(V4/name,digest),0o644);own[rel]=digest
    write(destination/'canary/caller',read(V4/'canary/caller',identities['canary/caller']),0o555)
    write(destination/'guardian/guard.py',read(V4/'guardian/guard.py',identities['guardian/guard.py']),0o555)
    write(destination/'orchestrator.json',canonical(own))
    write(destination/'evidence/v4-source-identity.json',canonical(identities))
    write(destination/'evidence/v4-independent-review.json',report)
    current=bundle(CONT/'artex-worker-canary-bundle',destination/'bundle654','85aef1698ef86d928f4767efcf6754cde410eef959c1bb290340463600e25206','ea54b361fed9d575eaadcd069b59382d853c241abee4821dbd7f02f4fac765ac')
    if len(current['source'])!=654 or len(current['host'])!=11:raise ValueError('bundle cardinality')
    fixture=CONT/'artex-owned-assessment-fixture/fixture.py'
    write(destination/'fixture.py',read(fixture,'49e1f487b407ebff7bf0d79f5f2e6137b38d6955c4c1ca1e9a4becb15e20a08d'),0o644)
    # Launch bootstrap checks every staged code byte AND rejects extra files,
    # including unchecked pyc, before it adds the canary path to sys.path.
    manifest={str(p.relative_to(destination)):sha(p.read_bytes()) for p in destination.rglob('*') if p.is_file()}
    write(destination/'stage-manifest.json',canonical(manifest))
    return {'status':'STAGED_NOT_APPROVED','files':len(manifest),'source':654,'host':11,'runtime_proof':False}
def check_stage(root,manifest_digest):
    root=Path(root);manifest=json.loads(read(root/'stage-manifest.json',manifest_digest))
    actual=set()
    for p in root.rglob('*'):
        if p.is_symlink():raise ValueError('staging symlink')
        if p.is_file():actual.add(str(p.relative_to(root)))
    if actual!=set(manifest)|{'stage-manifest.json'}:raise ValueError('unreviewed source extras/pycache')
    for name,digest in manifest.items():read(root/name,digest)
    return manifest
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: prepare.py NEW_OWNED_LANE_DESTINATION')
    print(json.dumps(prepare(sys.argv[1]),sort_keys=True))
