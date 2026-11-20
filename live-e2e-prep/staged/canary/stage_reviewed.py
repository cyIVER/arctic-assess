"""Read-only original input, private NEW snapshot. No execution or approval minting."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from guest import PINS,HELPER,need

def stage(original,destination,manifest_sha256=PINS,helper_sha256=HELPER):
    original=Path(original);destination=Path(destination)
    def read(path,digest):
        need(path.is_absolute() and '..' not in path.parts,'stage absolute source path')
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in path.parts[1:-1]:
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=nxt
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        finally:os.close(parent)
        try:
            s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_size<=134217728,'stage input type/size')
            with os.fdopen(fd,'rb',closefd=False) as f:b=f.read(134217729)
            need(hashlib.sha256(b).hexdigest()==digest,'stage input digest');return b
        finally:os.close(fd)
    raw=read(original/'receipts/final-pins.json',manifest_sha256);manifest=json.loads(raw)
    destination.mkdir(mode=0o700);os.chmod(destination,0o700) # fresh only
    def write(path,b,mode=0o644):
        parent=destination
        for part in path.relative_to(destination).parts[:-1]:
            parent=parent/part
            if not parent.exists():parent.mkdir(mode=0o700);os.chmod(parent,0o700)
            need(not parent.is_symlink() and parent.is_dir() and not parent.stat().st_mode&0o022,'stage destination ancestry')
        with path.open('xb') as f:os.chmod(path,mode);f.write(b);f.flush();os.fsync(f.fileno())
    for group in ('source','host'):
        need(isinstance(manifest[group],dict) and bool(manifest[group]),'reviewed manifest members')
        for name,digest in manifest[group].items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts,'stage path')
            write(destination/group/name,read(original/group/name,digest))
    write(destination/'receipts/final-pins.json',raw)
    write(destination/'receipts/artex-worker-tools-h2',read(original/'receipts/artex-worker-tools-h2',helper_sha256),0o555)
    return {'status':'STAGED_NOT_APPROVED','pins_sha256':manifest_sha256,'helper_sha256':helper_sha256,'source_files':len(manifest['source']),'host_files':len(manifest['host']),'destination':str(destination)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--original',required=True);p.add_argument('--destination',required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--helper-sha256',required=True);a=p.parse_args();print(json.dumps(stage(a.original,a.destination,a.manifest_sha256,a.helper_sha256)))
