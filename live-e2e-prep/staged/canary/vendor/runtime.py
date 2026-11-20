"""Offline controls. No cloud, Docker, mount, native or model execution entrypoint."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

class Denied(RuntimeError):
    pass

VM={'name':'vindler-lab-01','id':'590620893136303309','disk_id':'521979503200711885','project':'syncfall-ir-range','zone':'us-central1-a'}
KINDS={'image','source','binary','helper','assets','roles','broker','controller'}

def read_pinned(path, digest, cap=16*1024*1024):
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise Denied('invalid pin')
    p=Path(path)
    if not p.is_absolute() or str(p)!=path:raise Denied('noncanonical path')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
        leaf=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            s=os.fstat(leaf)
            if not stat.S_ISREG(s.st_mode) or s.st_mode&0o022 or s.st_size>cap:raise Denied('artifact type/mode/size')
            data=bytearray()
            while True:
                chunk=os.read(leaf,min(65536,cap+1-len(data)))
                if not chunk:break
                data.extend(chunk)
                if len(data)>cap:raise Denied('artifact cap')
            if hashlib.sha256(data).hexdigest()!=digest:raise Denied('artifact drift')
            return bytes(data)
        finally:os.close(leaf)
    except OSError:raise Denied('artifact unavailable or linked') from None
    finally:os.close(fd)

def verify_tree(root, manifest):
    """Verify exact reviewed inventory, without assuming final file/role counts.
    This is a read-only check, not protection of a later moving-tree compiler.
    """
    from lifecycle import WorkspaceQuota
    try:
        rows=manifest['files']
        if not isinstance(rows,list) or not rows:raise Denied('empty inventory')
        expected={}
        for row in rows:
            name=row['path'];p=Path(name)
            if not isinstance(name,str) or p.is_absolute() or str(p)!=name or '..' in p.parts or name in expected:raise Denied('source path/duplicate')
            if not {'path','bytes','sha256','mode'}<=set(row) or row['mode']not in ('100644','100755') or type(row['bytes'])is not int or row['bytes']<0:raise Denied('source row')
            expected[name]=row
        fd=WorkspaceQuota.open_dir(root)
        try:
            observed=set()
            for directory,dirs,files,dfd in os.fwalk('.',dir_fd=fd,follow_symlinks=False):
                for name in dirs:
                    if not stat.S_ISDIR(os.stat(name,dir_fd=dfd,follow_symlinks=False).st_mode):raise Denied('source linked directory')
                for name in files:
                    relative=str(Path(directory)/name)
                    if relative not in expected:raise Denied('unreviewed source file')
                    row=expected[relative];leaf=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
                    try:
                        s=os.fstat(leaf)
                        if not stat.S_ISREG(s.st_mode) or s.st_mode&0o022 or s.st_size!=row['bytes'] or ('100755' if s.st_mode&0o100 else '100644')!=row['mode']:raise Denied('source type/mode/size')
                        with os.fdopen(leaf,'rb',closefd=False) as src:digest=hashlib.file_digest(src,'sha256').hexdigest()
                        if digest!=row['sha256']:raise Denied('source bytes changed')
                        observed.add(relative)
                    finally:os.close(leaf)
            if observed!=set(expected):raise Denied('source coverage mismatch')
            if 'count' in manifest and manifest['count']!=len(observed):raise Denied('declared count mismatch')
            return len(observed)
        finally:os.close(fd)
    except (KeyError,TypeError,OSError,ValueError):raise Denied('source inventory rejected') from None

def validate_inputs(config, now, *, fresh=True):
    try:
        if set(config)!={'vm','created','deadline','rollback_image','handles'} or config['vm']!=VM:raise Denied('scope')
        created,end=config['created'],config['deadline']
        if type(created) not in (int,float) or type(end) not in (int,float) or not 0<=now-created<3600 or fresh and now-created>120 or end-created!=3600:raise Denied('fresh 60-minute guard required')
        if not re.fullmatch('sha256:[0-9a-f]{64}',config['rollback_image']):raise Denied('immutable rollback image')
        if set(config['handles'])!=KINDS:raise Denied('all final review handles required')
        for name,h in config['handles'].items():
            if set(h)!={'path','sha256','review_path','review_sha256'}:raise Denied('review handle schema')
            read_pinned(h['path'],h['sha256'],cap=128*1024*1024 if name=='binary' else 16*1024*1024)
            review=json.loads(read_pinned(h['review_path'],h['review_sha256']))
            if review!={'status':'approved','kind':name,'object_sha256':h['sha256']}:raise Denied('review does not bind object')
        return True
    except (KeyError,TypeError,ValueError):raise Denied('invalid input') from None
