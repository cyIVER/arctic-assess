"""Offline-tested phase, membership rehearsal, mount verification and checkpoint controls.
No privileged operations or final broker/DB wiring.
"""
from runtime import Denied
import os
from pathlib import Path
import stat
import threading

class Phase:
    def __init__(self, root, deadline, *, clock):
        self.root,self.deadline,self.clock=Path(root),deadline,clock
        self.started=False;self.paused=False;self.stopped=threading.Event();self.lock=threading.RLock()
        self.calls=0;self.bytes=0
    def start(self):
        with self.lock:
            if self.started or not 0<self.deadline-self.clock()<=600:raise Denied('invalid phase lifetime')
            parent=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                info=os.fstat(parent)
                if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise Denied('private phase root required')
                try:fd=os.open('executor-started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
                except FileExistsError:raise Denied('executor already started; no restart/recovery') from None
                try:os.write(fd,b'fail-closed single incarnation\n');os.fsync(fd)
                finally:os.close(fd)
                os.fsync(parent);self.started=True;return True
            finally:os.close(parent)
    def check(self):
        if not self.started or self.paused or self.stopped.is_set() or self.clock()>=self.deadline:raise Denied('phase inactive')
    def reserve(self):
        with self.lock:
            self.check()
            if self.calls>=32 or self.bytes>=131072:raise Denied('phase exhausted')
            self.calls+=1
    def charge(self,n):
        with self.lock:
            if type(n)is not int or n<0:raise Denied('invalid charge')
            self.bytes+=n
            if self.bytes>131072:self.stopped.set();raise Denied('aggregate output exhausted')
    def pause(self):
        with self.lock:self.paused=True
    def cancel(self):
        with self.lock:self.stopped.set()
class WorkspaceQuota:
    LIMIT=64*1024*1024
    def __init__(self,path,*,uid,gid,mountinfo,statvfs):
        self.path,self.uid,self.gid,self.mountinfo,self.statvfs=path,uid,gid,mountinfo,statvfs
        self.fd=None;self.identity=None
    @staticmethod
    def open_dir(path):
        p=Path(path)
        if not p.is_absolute() or str(p)!=path or any(x in path for x in ('\\','\n',',',' ')):raise Denied('canonical workspace root')
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in p.parts[1:]:
                new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
            return fd
        except BaseException:os.close(fd);raise Denied('workspace ancestry') from None
    def verify(self):
        fd=self.open_dir(self.path)
        try:
            s=os.fstat(fd);identity=(s.st_dev,s.st_ino)
            if s.st_uid!=self.uid or s.st_gid!=self.gid or stat.S_IMODE(s.st_mode)!=0o700:raise Denied('workspace owner/mode')
            if self.identity is not None and identity!=self.identity:raise Denied('workspace replaced')
            records=[]
            for line in self.mountinfo().splitlines():
                left,sep,right=line.partition(' - ');fields=left.split();after=right.split()
                if sep and len(fields)>=6 and fields[4]==self.path:records.append((fields,after))
            if len(records)!=1:raise Denied('exact dedicated mount required')
            fields,after=records[0]
            if len(after)!=3 or fields[3]!='/' or after[:2]!=['tmpfs','tmpfs'] or not {'rw','nodev','nosuid','noexec'}<=set(fields[5].split(',')):raise Denied('private tmpfs mount required')
            opts=dict(x.split('=',1) for x in after[2].split(',') if '=' in x)
            if opts.get('size') not in ('65536k','64m','67108864') or opts.get('uid')!=str(self.uid) or opts.get('gid')!=str(self.gid) or opts.get('mode')!='700':raise Denied('exact aggregate mount policy')
            fs=self.statvfs(fd)
            if fs.f_blocks*fs.f_frsize!=self.LIMIT or not 0<=fs.f_bavail*fs.f_frsize<=self.LIMIT:raise Denied('aggregate capacity')
            if self.fd is None:self.fd=os.dup(fd);self.identity=identity
            return True
        finally:os.close(fd)
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
class Membership:
    """Trusted-callback rehearsal registry, NOT final DB or broker wiring."""
    FIELDS={'PhaseID','Generation','TaskID','ExplorationID','IntentID','Role','SessionID','ExecutorID','NetworkPolicyID'}
    def __init__(self,phase,quota,verify):
        self.phase,self.quota,self.verify=phase,quota,verify
        self.entries={};self.revoked=set();self.phase_identity=None;self.intents=set()
    @classmethod
    def key(cls,binding):
        import re
        if not isinstance(binding,dict) or set(binding)!=cls.FIELDS or binding['Role']!='worker':raise Denied('binding shape')
        for k,v in binding.items():
            if k in {'Generation','TaskID','ExplorationID','IntentID'}:
                if type(v)is not int or v<=0:raise Denied('binding numeric identity')
            elif not isinstance(v,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',v):raise Denied('binding token')
        return tuple(sorted(binding.items()))
    def register(self,binding):
        import copy
        with self.phase.lock:
            self.phase.check();key=self.key(binding)
            if key in self.revoked or key in self.entries:raise Denied('duplicate or revoked scope')
            trusted=copy.deepcopy(binding)
            if self.verify(trusted) is not True:raise Denied('trusted DB membership absent')
            self.phase.check();self.quota.verify()
            phase=tuple(binding[k] for k in ('PhaseID','Generation','TaskID','ExplorationID'))
            if self.phase_identity not in (None,phase) or binding['IntentID'] in self.intents:raise Denied('phase mismatch or duplicate intent')
            name='i'+str(binding['IntentID'])
            try:os.mkdir(name,0o700,dir_fd=self.quota.fd)
            except FileExistsError:raise Denied('workspace must be fresh') from None
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.quota.fd)
            try:
                os.fchmod(fd,0o700);s=os.fstat(fd)
                if s.st_uid!=self.quota.uid or s.st_gid!=self.quota.gid:raise Denied('workspace ownership')
                identity=(s.st_dev,s.st_ino)
            finally:os.close(fd)
            self.quota.verify();self.phase_identity=phase;self.intents.add(binding['IntentID'])
            self.entries[key]=(name,identity)
            return str(Path(self.quota.path)/name)
    def revoke(self,binding):
        with self.phase.lock:self.revoked.add(self.key(binding))
    def check(self,binding):
        import copy
        with self.phase.lock:
            self.phase.check();key=self.key(binding)
            if key not in self.entries or key in self.revoked or self.verify(copy.deepcopy(binding)) is not True:raise Denied('membership revoked/unknown')
            self.phase.check();self.quota.verify();name,identity=self.entries[key]
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.quota.fd)
            try:
                s=os.fstat(fd)
                if (s.st_dev,s.st_ino)!=identity or s.st_uid!=self.quota.uid or s.st_gid!=self.quota.gid or stat.S_IMODE(s.st_mode)!=0o700:raise Denied('workspace changed')
            finally:os.close(fd)
            return True

def checkpoint(tasks, archive, quota, phase, cleanup):
    """Copy and verify before invoking caller-owned cleanup; never delete tasks.
    Caller must first prove all effect containers absent. No live wiring here.
    """
    import hashlib
    import tarfile
    if not phase.started or not phase.paused:raise Denied('pause admission before checkpoint')
    quota.verify()
    if str(tasks)!=quota.path:raise Denied('checkpoint scope')
    archive=Path(archive)
    if not archive.is_absolute() or Path(tasks)==archive or Path(tasks) in archive.parents:raise Denied('checkpoint must be outside tmpfs')
    parent=WorkspaceQuota.open_dir(str(archive.parent));fd=None;expected={};total=0
    try:
        s=os.fstat(parent)
        if s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o700:raise Denied('private archive parent')
        fd=os.open(archive.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,'w+b',closefd=False) as out:
            with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as tar:
                for root,dirs,files,dirfd in os.fwalk('.',dir_fd=quota.fd,follow_symlinks=False):
                    for name in dirs+files:
                        info=os.stat(name,dir_fd=dirfd,follow_symlinks=False)
                        rel=str(Path(root)/name)
                        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or info.st_nlink>1 and stat.S_ISREG(info.st_mode):raise Denied('checkpoint special/link object')
                        if len(expected)>=4096:raise Denied('checkpoint entry cap')
                        entry=tarfile.TarInfo(rel);entry.mode=stat.S_IMODE(info.st_mode)&0o700;entry.uid=quota.uid;entry.gid=quota.gid
                        if stat.S_ISDIR(info.st_mode):
                            entry.type=tarfile.DIRTYPE;tar.addfile(entry);expected[rel]=None;continue
                        total+=info.st_size
                        if total>quota.LIMIT:raise Denied('checkpoint bytes')
                        leaf=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dirfd)
                        try:
                            before=os.fstat(leaf)
                            if not stat.S_ISREG(before.st_mode) or (before.st_dev,before.st_ino,before.st_size)!=(info.st_dev,info.st_ino,info.st_size):raise Denied('checkpoint source race')
                            with os.fdopen(leaf,'rb',closefd=False) as src:
                                digest=hashlib.file_digest(src,'sha256').hexdigest();src.seek(0);entry.size=info.st_size;tar.addfile(entry,src)
                            after=os.fstat(leaf)
                            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise Denied('checkpoint changed')
                            expected[rel]=digest
                        finally:os.close(leaf)
                        if out.tell()>quota.LIMIT:raise Denied('checkpoint archive cap')
            out.flush();os.fsync(fd)
            if os.fstat(fd).st_size>quota.LIMIT:raise Denied('checkpoint archive cap')
            out.seek(0);observed={}
            with tarfile.open(fileobj=out,mode='r:') as tar:
                for entry in tar:
                    if entry.name in observed:raise Denied('duplicate archive entry')
                    if entry.isdir():observed[entry.name]=None
                    elif entry.isfile():
                        with tar.extractfile(entry) as src:observed[entry.name]=hashlib.file_digest(src,'sha256').hexdigest()
                    else:raise Denied('archive special object')
            if observed!=expected:raise Denied('archive readback mismatch')
        os.fsync(parent);quota.verify()
    except (OSError,tarfile.TarError,ValueError):raise Denied('checkpoint failed; source retained; no cleanup') from None
    finally:
        if fd is not None:os.close(fd)
        os.close(parent)
    quota.close()
    cleanup()
    return True
