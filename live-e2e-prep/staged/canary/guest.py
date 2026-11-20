"""LOCAL-authorable guest API. Nothing privileged runs on import or validation.
Live entry requires parent authority and fresh independent stop-controller readback.
This is a literal, no-model canary lane, never normal ARTEX goal acceptance.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time

HERE=Path(os.path.abspath(__file__)).parent
TRUSTED_UID=0 # Never configured by JSON/environment. Unit tests patch explicitly.
BASE='sha256:de6c8e66f6c0a7b34e043dac442d02e0d6e67e009814b78ce73effd51cf32683'
PINS='90e5a9a6faae63a033a59c884533d089d868b7ba8850b0cb58c2c2a3110b5af9'
HELPER='22b2710376814c792c94962e4d9943125fe387aa7b696664117f102ec3fd8ba1'
VM={'name':'vindler-lab-01','id':'590620893136303309','disk_id':'521979503200711885','project':'syncfall-ir-range','zone':'us-central1-a'}
DAEMON='unix:///home/vindleradmin/artex-standalone-phase-a-standing/storage/docker/docker.sock'
LIMIT=67108864
class Blocked(RuntimeError): pass

def need(value, reason):
    if not value: raise Blocked(reason)

def trusted_directory(fd):
    s=os.fstat(fd)
    need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,TRUSTED_UID) and not s.st_mode&0o022,'untrusted artifact ancestry')

def pinned(path, digest, cap=134217728, *, executable=False, elf=False):
    need(isinstance(path,str) and Path(path).is_absolute() and str(Path(path))==path and '..' not in Path(path).parts,'artifact path')
    need(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),'artifact pin')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        trusted_directory(fd)
        for part in Path(path).parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd); os.close(fd);fd=nxt
            trusted_directory(fd)
        leaf=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            s=os.fstat(leaf)
            need(stat.S_ISREG(s.st_mode) and s.st_uid==TRUSTED_UID and s.st_nlink==1 and not s.st_mode&0o022 and s.st_size<=cap,'artifact owner/type/mode/size')
            need(not executable or bool(s.st_mode&0o111),'artifact not executable')
            with os.fdopen(leaf,'rb',closefd=False) as f: data=f.read(cap+1)
            need(len(data)<=cap and hashlib.sha256(data).hexdigest()==digest,'artifact drift')
            need(not elf or data[:4]==b'\x7fELF','artifact not ELF')
            return data
        finally: os.close(leaf)
    finally: os.close(fd)

def validate_snapshot(c, now, *, current=False):
    try:
        need(type(c['schema']) is int and c['schema']==1 and c['lane']=='literal-no-model-isolation' and c['vm']==VM,'scope')
        import math
        for field in ('created','deadline','external_stop','guard_created','budget_ceiling_usd','spent_usd','reserve_usd'):
            need(type(c[field]) in (int,float) and math.isfinite(c[field]),'strict finite numeric '+field)
        for field in ('socket_uid','socket_inode','socket_device'):
            need(type(c['owner'][field]) is int,'strict socket identity '+field)
        need(type(c['created']) in (int,float) and type(c['deadline']) in (int,float) and 0<=now-c['created']<=120 and 30<c['deadline']-now<=600,'stale task approval/deadline')
        need(c['external_stop']>=c['deadline']+30 and 0<c['external_stop']-c['guard_created']<=3600 and c['guard_created']<=now,'absolute STOP')
        need(c['budget_ceiling_usd']==2 and 0<=c['spent_usd'] and c['spent_usd']+c['reserve_usd']<=2 and c['reserve_usd']>=.50,'cost headroom')
        need(c['daemon']==DAEMON and c['baseline_image']==BASE and c.get('pause_default_service',False) is False,'daemon/base/service authority')
        need(re.fullmatch('/run/artex-canary-[a-f0-9]{12}',c['root']) and not Path(c['root']).exists(),'fresh short root')
        if current:
            nonce=c['root'][-12:]
            need(not any(os.path.lexists(p) for p in (c['root'],'/run/artex-client-'+nonce,'/run/artex-exec-'+nonce,'/run/artex-target-'+nonce)),'all guest staging paths must be fresh')
        need(c['owner']['socket_uid']==os.getuid() and c['owner']['socket_inode']>0 and c['owner']['socket_device']>=0,'daemon owner')
        need(set(c['inventory'])=={'containers','images','volumes'} and all(isinstance(v,list) and len(v)==len(set(v)) for v in c['inventory'].values()),'inventory IDs')
        need([len(c['inventory'][k]) for k in ('containers','images','volumes')]==[9,44,4],'standing inventory cardinality')
        handles=c['reviews']; need(set(handles)=={'source','host','helper','orchestrator','caller','guard','fixture'},'all review handles required')
        if current:
            from admission_v3 import require_current
            require_current(c,now)
        for kind,h in handles.items():
            pinned(h['path'],h['sha256'])
            r=json.loads(pinned(h['review_path'],h['review_sha256'],1048576))
            need(all(type(r.get(k)) in (int,float) for k in ('created','deadline')),'strict review timestamps')
            expected={'status':'approved','kind':kind,'object_sha256':h['sha256'],'vm':VM,'created':c['created'],'deadline':c['deadline']}
            if current:expected.update(parent_scope_lease=c['parent_scope_lease']['handle'],code_review_handle=r.get('code_review_handle'))
            need(r==expected,'unapproved/current object review')
        if not current:need(handles['source']['sha256']==PINS and handles['host']['sha256']==PINS and handles['helper']['sha256']==HELPER,'frozen source653/H2 pins')
        m=json.loads(pinned(handles['source']['path'],handles['source']['sha256']))
        for group in ('host','source'):
            count=c['manifest_counts'][group] if current else (11 if group=='host' else 653)
            need(type(count)is int and count>=(11 if group=='host' else 653) and len(m[group])==count,'exact reviewed manifest count')
            root=Path(c['isolation_root'])/group
            for name,digest in m[group].items():
                need(not Path(name).is_absolute() and '..' not in Path(name).parts,'manifest member')
                pinned(str(root/name),digest)
        own=json.loads(pinned(handles['orchestrator']['path'],handles['orchestrator']['sha256']))
        allowed_dependencies={'vendor/runtime.py','vendor/lifecycle.py'}
        for name,digest in own.items():
            need(Path(name).name==name or name in allowed_dependencies,'own manifest name')
            pinned(str(HERE/name),digest)
        need({'guest.py','probes.py','driver.py','fixture_service.py','reviewed_imports.py','image_stage.py'}|allowed_dependencies<=set(own),'own source coverage')
        if current:need({'v2_cases.py','admission_v3.py','restart_probe.py','bounded_transport.py','caller.go'}<=set(own),'v3 source coverage')
        need(c['reviews']['caller']['path']==c['caller'] and c['reviews']['guard']['path']==c['guard_status'] and c['reviews']['fixture']['path']==c['fixture_module'],'review executable binding')
        need(c['docker_cli'].startswith('/') and c['python'].startswith('/'),'absolute executables')
        return c
    except (KeyError,TypeError,ValueError,OSError) as e: raise Blocked('invalid/missing live inputs') from e

def validate(c,now):
    """Only live-admitting validator. Legacy snapshots are test-only readbacks."""
    return validate_snapshot(c,now,current=True)

class Runner:
    """Bounded commands; clean environment; stdin never retained in command receipts."""
    def __init__(self): self.events=[]
    def run(self, argv, *, timeout=3, cap=131072, payload=b'', env=None, caller=False):
        need(type(caller) is bool and type(timeout) in (int,float) and type(cap) is int and 0<timeout<=120 and 0<cap<=1048576,'caller bounds')
        identity={'user':1001,'group':1002,'extra_groups':[]} if caller else {}
        p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,close_fds=True,cwd='/',env=env or {'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C'},**identity)
        end=time.monotonic()+timeout; out=bytearray();err=bytearray();pending=memoryview(payload);sel=selectors.DefaultSelector()
        try:
            for stream in (p.stdin,p.stdout,p.stderr):os.set_blocking(stream.fileno(),False)
            for stream,label in ((p.stdout,'out'),(p.stderr,'err')):sel.register(stream,selectors.EVENT_READ,label)
            if pending:sel.register(p.stdin,selectors.EVENT_WRITE,'in')
            else:p.stdin.close()
            while sel.get_map():
                need(time.monotonic()<end,'caller deadline')
                for key,_ in sel.select(.02):
                    if key.data=='in':
                        try:n=os.write(key.fd,pending)
                        except BlockingIOError:continue
                        pending=pending[n:]
                        if not pending:sel.unregister(key.fileobj);p.stdin.close()
                    else:
                        try:b=os.read(key.fd,4096)
                        except BlockingIOError:continue
                        if not b:sel.unregister(key.fileobj);continue
                        (out if key.data=='out' else err).extend(b)
                        need(len(out)+len(err)<=cap,'caller output cap')
            rc=p.wait(timeout=max(.001,end-time.monotonic()))
            self.events.append({'argv':list(argv),'returncode':rc,'stdout_bytes':len(out),'stderr_bytes':len(err)})
            need(rc==0,'command failed')
            return bytes(out)
        finally:
            sel.close()
            # Kill this caller's process group; real effect descendants belong to Docker.
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
            for s in (p.stdin,p.stdout,p.stderr):s.close()

def call_caller(runner,argv,**kwargs):
    return runner.run(argv,caller=True,**kwargs)

def prepare_caller(c,key,broker,server_type):
    """Guest-root only, fresh root-controlled public executable and UDS trees."""
    nonce=Path(c['root']).name[-12:]
    client=Path('/run/artex-client-'+nonce);public=Path('/run/artex-exec-'+nonce)
    # Exclusive mkdir, never chmod/chown an existing path.
    client.mkdir(mode=0o711);public.mkdir(mode=0o755)
    os.chmod(client,0o711);os.chmod(public,0o755)
    need(client.stat().st_uid==TRUSTED_UID and public.stat().st_uid==TRUSTED_UID,'caller root-controlled staging')
    executable=public/'caller'
    with executable.open('xb') as f:
        f.write(pinned(c['caller'],c['reviews']['caller']['sha256']));f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),0o555)
    pinned(str(executable),c['reviews']['caller']['sha256'])
    sock=client/'control.sock';control=server_type(str(sock),key,1001,broker);control.start()
    os.chown(sock,1001,1002);os.chmod(sock,0o600)
    return control,executable,sock,client,public

def guard(c,runner,now):
    need(now<c['deadline'] and now<c['external_stop'],'deadline ended')
    status=json.loads(runner.run([c['guard_status'],'--status'],timeout=min(12,c['deadline']-now),cap=8192))
    need(status.get('alive') is True,'typed live-controller status')
    need(all(type(status.get(k)) in (int,float) for k in ('stop_at','guard_created')),'typed guard timestamps')
    if 'preflight' in c:need(status.get('default_docker_quiescent') is True,'typed daemon proof')
    expected={'alive':True,'provider_state':'RUNNING','vm':VM,'stop_at':c['external_stop'],'controller_id':c['controller_id'],'guard_created':c['guard_created']}
    if 'preflight' in c:expected.update(default_docker_quiescent=True,preflight_checkpoint_sha256=c['preflight']['sha256'])
    need(status==expected,'independent stop-controller/provider/default-quiescence readback')
    return status

def inventory(c,r):
    prefix=[c['docker_cli'],'--host',c['daemon']]
    def lines(args):return sorted(set(r.run(prefix+args,cap=65536).decode().split()))
    return {'containers':lines(['ps','--all','--quiet','--no-trunc']),'images':lines(['image','ls','--quiet','--no-trunc']),'volumes':lines(['volume','ls','--quiet'])}

def verify_owner(c,r):
    s=os.stat(c['daemon'][7:],follow_symlinks=False)
    need(stat.S_ISSOCK(s.st_mode) and (s.st_uid,s.st_dev,s.st_ino)==(c['owner']['socket_uid'],c['owner']['socket_device'],c['owner']['socket_inode']),'private daemon socket identity')
    info=json.loads(r.run([c['docker_cli'],'--host',c['daemon'],'info','--format','{{json .}}'],cap=65536))
    need(info['ID']==c['owner']['daemon_id'] and info['DockerRootDir']==c['owner']['docker_root'],'private daemon API owner')
    observed=inventory(c,r)
    need(observed=={k:sorted(v) for k,v in c['inventory'].items()},'initial standing inventory changed')
    return observed

def dockerfile():
    return f'FROM {BASE}\nCOPY --chmod=0555 artex-worker-tools /usr/local/bin/artex-worker-tools\nUSER 1001:1002\nENTRYPOINT ["/usr/local/bin/artex-worker-tools"]\n'

def checkpoint(work,archive):
    """Archive only ordinary valuable workspace leaves; no socket or fixture tree."""
    work=Path(work); archive=Path(archive);need(work not in archive.parents,'archive outside quota')
    expected={};total=0;got={}
    # Caller has fenced admission and settled all containers before entry.
    rootfd=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        with archive.open('x+b') as f:
            os.fchmod(f.fileno(),0o600)
            with tarfile.open(fileobj=f,mode='w',format=tarfile.USTAR_FORMAT) as t:
                for directory,dirs,files,dfd in os.fwalk('.',dir_fd=rootfd,follow_symlinks=False):
                    for name in dirs:
                        need(stat.S_ISDIR(os.stat(name,dir_fd=dfd,follow_symlinks=False).st_mode),'archive directory symlink')
                    for leafname in sorted(files):
                        before=os.stat(leafname,dir_fd=dfd,follow_symlinks=False)
                        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'archive special file')
                        fd=os.open(leafname,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
                        try:
                            s=os.fstat(fd)
                            need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and (s.st_dev,s.st_ino)==(before.st_dev,before.st_ino),'archive leaf identity')
                            total+=s.st_size;need(total<=LIMIT,'archive 64MiB cap')
                            with os.fdopen(fd,'rb',closefd=False) as src:data=src.read(s.st_size+1)
                            after=os.fstat(fd);leaf=os.stat(leafname,dir_fd=dfd,follow_symlinks=False)
                            need(len(data)==s.st_size and (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)==(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns) and (leaf.st_dev,leaf.st_ino)==(s.st_dev,s.st_ino) and after.st_nlink==1,'archive leaf changed')
                        finally:os.close(fd)
                        name=str(Path(directory)/leafname);expected[name]=hashlib.sha256(data).hexdigest()
                        import io
                        ti=tarfile.TarInfo(name);ti.size=len(data);ti.mode=0o600;t.addfile(ti,io.BytesIO(data))
            f.flush();os.fsync(f.fileno());need(os.fstat(f.fileno()).st_size<=LIMIT,'archive file exceeds 64MiB')
            f.seek(0)
            with tarfile.open(fileobj=f,mode='r:') as t:
                for member in t:
                    need(member.isfile() and member.name not in got and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts,'archive member')
                    got[member.name]=hashlib.sha256(t.extractfile(member).read()).hexdigest()
            need(got==expected,'archive readback mismatch');f.seek(0);archive_hash=hashlib.sha256(f.read()).hexdigest()
    finally:os.close(rootfd)
    d=os.open(archive.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)
    return {'members':got,'bytes':total,'archive_sha256':archive_hash}

def save(path,value):
    with open(path,'x') as f:os.chmod(path,0o600);json.dump(value,f,sort_keys=True,indent=2);f.flush();os.fsync(f.fileno())
