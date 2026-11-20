"""Trusted, disabled-by-default executor component. No CLI or daemon activation.
Fake-driver tests establish argv/lifecycle contracts, NOT runtime confinement.
"""
from dataclasses import dataclass, field
import copy
import json
import os
import pathlib
import re
import selectors
import stat
import subprocess
import threading
import time
from contextlib import contextmanager, ExitStack
import uuid

def same_typed_json(actual,expected):
    if type(actual) is not type(expected):return False
    if isinstance(expected,dict):
        return actual.keys()==expected.keys() and all(same_typed_json(actual[k],v) for k,v in expected.items())
    return actual==expected

def object_identity(fd,filesystem=True):
    s=os.fstat(fd);identity={'device':s.st_dev,'inode':s.st_ino}
    if filesystem:
        v=os.fstatvfs(fd);identity['fs_bytes']=v.f_blocks*v.f_frsize
    return identity

class Refused(Exception): pass

@dataclass(frozen=True)
class Policy:
    image: str
    data_root: str
    uid: int
    gid: int
    docker_cli: str
    daemon: str

class PhaseQuota:
    def __init__(self):self.calls=0;self.bytes=0;self.lock=threading.Lock()
    def reserve(self):
        with self.lock:
            if self.calls>=32 or self.bytes>=131072:raise Refused('phase budget')
            self.calls+=1
    def charge(self,n):
        with self.lock:
            self.bytes+=n
            if self.bytes>131072:raise Refused('phase byte budget')

@dataclass
class Scope:
    binding: dict
    workspace: str
    fixture_dir: str
    budget: object
    calls: int = 0
    output_bytes: int = 0
    quarantined: bool = False
    lock: object = field(default_factory=threading.Lock)
    quota_bytes: object = None # Host runtime supplies its independently verified quota capacity.
    def charge(self,n):
        self.quota.charge(n)
        self.output_bytes+=n
        if self.output_bytes>131072:raise Refused("aggregate output cap")

class DockerCLI:
    def __init__(self, policy): self.policy=policy
    def run(self,args,payload=b'',*,timeout,cancel,max_bytes,charge=None,attestation=None,payload_guard=None):
        # Attestation is mandatory for attached effects; no legacy fallback.
        attached=args[:3]==['start','--attach','--interactive']
        if attached and (attestation is None or payload_guard is None):raise Refused('attestation required')
        argv=[self.policy.docker_cli,'--host',self.policy.daemon,*args]
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','DOCKER_CONFIG':'/nonexistent','LANG':'C'}
        p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,start_new_session=True)
        end=time.monotonic()+timeout; hello_end=min(end,time.monotonic()+2)
        output=bytearray();hello=bytearray();total=0;verified=not attached
        nonce=os.urandom(32).hex()
        pending=memoryview((json.dumps({'version':2,'nonce':nonce},separators=(',',':')).encode()+b'\n') if attached else payload)
        sel=selectors.DefaultSelector()
        try:
            for stream in (p.stdin,p.stdout,p.stderr):os.set_blocking(stream.fileno(),False)
            if pending:sel.register(p.stdin,selectors.EVENT_WRITE,'in')
            else:p.stdin.close()
            sel.register(p.stdout,selectors.EVENT_READ,'out');sel.register(p.stderr,selectors.EVENT_READ,'err')
            while sel.get_map():
                if cancel.is_set() or time.monotonic()>=end or (not verified and time.monotonic()>=hello_end):raise Refused('cancelled or timeout')
                for key,mask in sel.select(.02):
                    if cancel.is_set():raise Refused('cancelled')
                    if key.data=='in':
                        try:
                            if attached and verified:
                                # Linearize revocation/admission against each nonblocking write.
                                with payload_guard():
                                    if cancel.is_set():raise Refused('cancelled')
                                    n=os.write(key.fd,pending)
                            else:n=os.write(key.fd,pending)
                        except BlockingIOError:continue
                        pending=pending[n:]
                        if not pending:
                            sel.unregister(key.fileobj)
                            if verified:p.stdin.close()
                    else:
                        try:b=os.read(key.fd,4096)
                        except BlockingIOError:continue
                        if not b:
                            sel.unregister(key.fileobj)
                            if key.data=='out' and not verified:raise Refused('missing HELLO')
                            continue
                        total+=len(b)
                        if charge:charge(len(b))
                        if total>max_bytes:raise Refused('outer byte limit')
                        if key.data=='out':
                            if not verified:
                                hello.extend(b)
                                if len(hello)>8192:raise Refused('HELLO cap')
                                if b'\n' not in hello:continue
                                frame,rest=hello.split(b'\n',1)
                                if rest:raise Refused('unsolicited pre-ACK bytes')
                                expected={'version':2,'nonce':nonce,**attestation}
                                actual=strict_json(bytes(frame))
                                # Equality alone would accept bools/floats as integers.
                                if not same_typed_json(actual,expected):raise Refused('mounted object mismatch')
                                if cancel.is_set() or time.monotonic()>=hello_end:raise Refused('late HELLO')
                                verified=True
                                pending=memoryview(json.dumps({'version':2,'ack':nonce},separators=(',',':')).encode()+b'\n'+payload)
                                sel.register(p.stdin,selectors.EVENT_WRITE,'in')
                            else:output.extend(b)
            if not verified:raise Refused('missing HELLO')
            if p.wait(timeout=max(.001,end-time.monotonic()))!=0:raise Refused('Docker CLI failed')
            return bytes(output)
        except (OSError, subprocess.SubprocessError):
            raise Refused('Docker transport failed') from None
        finally:
            sel.close()
            if p.poll() is None:p.kill()
            p.wait()
            for s in (p.stdin,p.stdout,p.stderr):s.close()

class Broker:
    def __init__(self,policy,scopes,*,driver=None,reviewed=False,scope_resolver=None):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',policy.image):raise ValueError('immutable local image ID required')
        if not policy.daemon.startswith('unix:///') or policy.daemon=='unix:///var/run/docker.sock':raise ValueError('private task daemon required')
        if not os.path.isabs(policy.docker_cli) or policy.uid<=0 or policy.gid<0:raise ValueError('invalid host policy')
        self.policy=policy;self.driver=driver or DockerCLI(policy);self.reviewed=reviewed
        self.scopes={};self.phase_quotas={};self.registry_lock=threading.RLock();self._pins={}
        self.tombstones=set();self.scope_resolver=scope_resolver
        for s in scopes:
            self.register_scope(s,getattr(s,'membership_verifier',lambda binding:True))

    def register_scope(self,scope,membership_verifier):
        """Host-only. Callbacks must do fresh trusted membership/phase verification."""
        with self.registry_lock:
            key=self._key(scope.binding)
            if key in self.tombstones or key in self.scopes:raise Refused('binding permanently owned or revoked')
            if not callable(membership_verifier):raise Refused('membership verifier required')
            binding=copy.deepcopy(scope.binding)
            try:
                if membership_verifier(copy.deepcopy(binding)) is not True:raise Refused('membership refused')
                scope.budget.check()
            except Exception:raise Refused('membership or budget refused') from None
            if any(s.workspace==scope.workspace for s in self.scopes.values()):raise Refused('workspace already assigned')
            pins=self._paths(scope)
            scope.binding=binding;scope.membership_verifier=membership_verifier
            phase=tuple(binding[k] for k in ('PhaseID','Generation','TaskID','ExplorationID'))
            scope.quota=self.phase_quotas.setdefault(phase,PhaseQuota())
            self.scopes[key]=scope;self._pins[key]=pins
            return scope

    def revoke_scope(self,binding):
        """Permanent fence; execute owns independent removal and absence readback."""
        with self.registry_lock:
            key=self._key(binding);self.tombstones.add(key)
            scope=self.scopes.get(key)
            if scope:scope.budget.cancel()

    def _admit(self,key,scope):
        # Caller holds registry_lock; never reset quota, budget, lock or tombstone.
        if key in self.tombstones or self.scopes.get(key) is not scope:raise Refused('scope revoked')
        try:
            if scope.membership_verifier(copy.deepcopy(scope.binding)) is not True:raise Refused('membership refused')
            scope.budget.check()
        except Exception:
            self.revoke_scope(scope.binding)
            raise Refused('membership or budget refused') from None
        if scope.quarantined:raise Refused('workspace quarantined')

    @contextmanager
    def _payload_guard(self,key,scope,name,deadline):
        with self.registry_lock:
            self._admit(key,scope)
            with self._paths(scope):
                config=strict_json(self.driver.run(['inspect','--format','{"mounts":{{json .Mounts}},"tmpfs":{{json .HostConfig.Tmpfs}}}',name],timeout=min(2,max(.001,deadline-time.monotonic())),cancel=scope.budget.stopped,max_bytes=8192))
                validate_mount_config(config,scope)
                if scope.budget.stopped.is_set() or time.monotonic()>=deadline:raise Refused('effect deadline or cancellation')
                yield

    @staticmethod
    def _key(binding):
        keys={'PhaseID','Generation','TaskID','ExplorationID','IntentID','Role','SessionID','ExecutorID','NetworkPolicyID'}
        if not isinstance(binding,dict) or set(binding)!=keys:raise Refused('invalid binding')
        for k in ('Generation','TaskID','ExplorationID','IntentID'):
            if type(binding[k]) is not int or binding[k]<=0:raise Refused('invalid identity')
        for k in keys-{'Generation','TaskID','ExplorationID','IntentID'}:
            if not isinstance(binding[k],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',binding[k]):raise Refused('invalid identity')
        if binding['Role']!='worker':raise Refused('role')
        return tuple((k,binding[k]) for k in sorted(keys))
    def _paths(self,scope):
        stack=ExitStack();stack.identities={};stack.fds={}
        try:
            root=pathlib.Path(self.policy.data_root)
            if not root.is_absolute():raise Refused('data root')
            if scope.workspace==str(root) or scope.fixture_dir==str(root) or scope.workspace==scope.fixture_dir:raise Refused('mount scope is not a dedicated leaf')
            # Trusted ancestors must not be replaceable by worker identity. Preserve
            # descriptors for every leaf through create/start. Worker sees only /work.
            for path in (str(root),scope.workspace,scope.fixture_dir):
                p=pathlib.Path(path)
                if os.path.normpath(path)!=path or any(c in path for c in ',\r\n'):raise Refused('noncanonical mount path')
                if not p.is_absolute() or p==root and path!=str(root) or (p!=root and root not in p.parents):raise Refused('scope path')
                current=pathlib.Path('/')
                for part in p.parts[1:]:
                    current=current/part
                    if stat.S_ISLNK(os.lstat(current).st_mode):raise Refused('symlink ancestry')
                if p==root:
                    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);stack.callback(os.close,fd)
                    label='root'
                else:
                    parent=stack.fds['root']
                    for part in p.relative_to(root).parts:
                        fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                        stack.callback(os.close,fd);parent=fd
                    label='work' if path==scope.workspace else 'fixture'
                stack.fds[label]=fd;stack.identities[label]=object_identity(fd)
                info=os.fstat(fd)
                if info.st_uid!=self.policy.uid or info.st_mode & 0o022:raise Refused('scope ownership/mode')
            if set(os.listdir(stack.fds['fixture']))!={'gateway.sock'}:raise Refused('fixture-only socket directory required')
            socket_fd=os.open('gateway.sock',os.O_PATH|os.O_NOFOLLOW,dir_fd=stack.fds['fixture']);stack.callback(os.close,socket_fd)
            si=os.fstat(socket_fd)
            if not stat.S_ISSOCK(si.st_mode) or si.st_uid!=self.policy.uid or si.st_mode & 0o077:raise Refused('fixture socket identity')
            stack.identities['gateway']=object_identity(socket_fd,False)
            root_id=stack.identities['root'];work_id=stack.identities['work']
            if root_id['device']!=work_id['device'] or root_id['fs_bytes']!=work_id['fs_bytes']:raise Refused('workspace outside quota filesystem')
            quota_bytes=getattr(scope,'quota_bytes',None)
            if quota_bytes is not None and (type(quota_bytes) is not int or quota_bytes!=root_id['fs_bytes']):raise Refused('required filesystem quota mismatch')
            pinned=self._pins.get(self._key(scope.binding))
            if pinned is not None and not same_typed_json(stack.identities,pinned.identities):raise Refused('reserved source objects changed')
            return stack
        except BaseException:
            stack.close();raise
    def cancel_request(self,request):
        with self.registry_lock:
            try:key=self._key(request["Binding"])
            except (Refused,KeyError,TypeError):return
            # Also fence disconnects while the resolver is still registering.
            self.revoke_scope(dict(key))
    def execute(self,request):
        if not self.reviewed:raise Refused('runtime disabled pending review and VM proof')
        if not isinstance(request,dict) or set(request)!={'Binding','Tool','Input','ToolUseID'}:raise Refused('invalid request')
        with self.registry_lock:
            key=self._key(request['Binding'])
            if key in self.tombstones:raise Refused('scope revoked')
            scope=self.scopes.get(key)
            if scope is None and self.scope_resolver is not None:
                try:
                    scope,verifier=self.scope_resolver(copy.deepcopy(request['Binding']))
                    if self._key(scope.binding)!=key:raise Refused('resolver binding mismatch')
                except Exception:raise Refused('scope resolver refused') from None
                scope=self.register_scope(scope,verifier)
            if scope is None:raise Refused('unregistered authority')
            self._admit(key,scope)
        if request['Tool'] not in {'Read','Write','Edit','LS','Bash','sleep'} or not isinstance(request['Input'],dict):raise Refused('tool/input')
        if not isinstance(request['ToolUseID'],str) or len(request['ToolUseID'])>128:raise Refused('metadata')
        payload=json.dumps({'version':1,'tool':request['Tool'],'input':request['Input'],'tool_use_id':request['ToolUseID']},separators=(',',':')).encode()
        if len(payload)>32768:raise Refused('input cap')
        # Serialization is intentional; SDK concurrency flags are not a security gate.
        if not scope.lock.acquire(blocking=False):raise Refused('workspace busy')
        name='artex-effect-'+uuid.uuid4().hex
        cleanup_needed=False
        deadline=time.monotonic()+10
        try:
            scope.budget.check()
            if scope.quarantined or scope.calls>=32 or scope.output_bytes>=131072:raise Refused('scope exhausted or quarantined')
            with self._paths(scope) as paths:
                with self.registry_lock:self._admit(key,scope)
                scope.quota.reserve()
                scope.calls+=1
                args=['create','--name',name,'--label','artex.executor='+request['Binding']['ExecutorID'],'--read-only','--cap-drop=ALL','--network=none','--pid=private','--ipc=private','--security-opt=no-new-privileges','--pids-limit=64','--memory=256m','--memory-swap=256m','--cpus=1','--log-driver=none','--ulimit','core=0:0','--ulimit','fsize=8388608:8388608','--user',f'{self.policy.uid}:{self.policy.gid}','--workdir','/work','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777','--tmpfs','/app/data:ro,noexec,nosuid,nodev,size=64k,mode=0555','--mount',f'type=bind,src={scope.workspace},dst=/work','--mount',f'type=bind,src={scope.fixture_dir},dst=/fixture,readonly','--env','PATH=/usr/local/bin:/usr/bin:/bin','--env','HOME=/tmp','--env','TMPDIR=/tmp','--interactive','--entrypoint','/usr/local/bin/artex-worker-tools',self.policy.image]
                image_volumes=strict_json(self.driver.run(['image','inspect','--format','{{json .Config.Volumes}}',self.policy.image],timeout=min(2,max(.001,deadline-time.monotonic())),cancel=scope.budget.stopped,max_bytes=4096))
                if not same_typed_json(image_volumes,{'/app/data':{}}):raise Refused('unexpected inherited image volumes')
                cleanup_needed=True # even ambiguous create failure requires removal/absence proof
                self.driver.run(args,timeout=min(3,max(.001,deadline-time.monotonic())),cancel=scope.budget.stopped,max_bytes=4096)
                scope.budget.check()
                if time.monotonic()>=deadline:raise Refused('effect deadline')
                mount_config=strict_json(self.driver.run(['inspect','--format','{"mounts":{{json .Mounts}},"tmpfs":{{json .HostConfig.Tmpfs}}}',name],timeout=min(2,max(.001,deadline-time.monotonic())),cancel=scope.budget.stopped,max_bytes=8192))
                validate_mount_config(mount_config,scope)
                output=self.driver.run(['start','--attach','--interactive',name],payload,timeout=max(.001,deadline-time.monotonic()),cancel=scope.budget.stopped,max_bytes=min(65536,131072-scope.output_bytes),charge=scope.charge,attestation={k:v for k,v in paths.identities.items() if k!='root'},payload_guard=lambda:self._payload_guard(key,scope,name,deadline))
                scope.budget.check()
                result=strict_json(output)
                validate_result(result)
            return result
        except Exception:
            raise Refused('isolated execution refused or failed') from None
        finally:
            if cleanup_needed:
                try:
                    # Independent cleanup deadline/cancellation: revocation must not disable cleanup.
                    never_cancel=threading.Event()
                    try:self.driver.run(['rm','--force','--volumes',name],timeout=3,cancel=never_cancel,max_bytes=4096)
                    finally:
                        remaining=self.driver.run(['ps','--all','--quiet','--filter','name=^/'+name+'$'],timeout=3,cancel=never_cancel,max_bytes=4096)
                        if remaining.strip():raise Refused('container absence not confirmed')
                except Exception:
                    scope.quarantined=True
                    # Keep capacity owned when liveness is uncertain; never host-fallback.
                    raise Refused('cleanup unresolved; workspace quarantined') from None
            if not scope.quarantined:scope.lock.release()

def validate_mount_config(config,scope):
    # Exact inherited-volume shadow policy for this reviewed task image only.
    tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=16m,mode=1777','/app/data':'ro,noexec,nosuid,nodev,size=64k,mode=0555'}
    if not isinstance(config,dict) or set(config)!={'mounts','tmpfs'} or not same_typed_json(config['tmpfs'],tmpfs) or not isinstance(config['mounts'],list):raise Refused('container mount configuration')
    seen=set()
    for mount in config['mounts']:
        if not isinstance(mount,dict):raise Refused('mount shape')
        dest=mount.get('Destination')
        if not isinstance(dest,str) or dest in seen:raise Refused('mount collision')
        seen.add(dest)
        if dest in ('/work','/fixture'):
            source=scope.workspace if dest=='/work' else scope.fixture_dir
            if mount.get('Type')!='bind' or mount.get('Source')!=source or type(mount.get('RW')) is not bool or mount['RW']!=(dest=='/work'):raise Refused('bind configuration')
        elif dest in tmpfs:
            if mount.get('Type')!='tmpfs' or type(mount.get('RW')) is not bool or mount['RW']!=(dest=='/tmp'):raise Refused('tmpfs configuration')
        else:raise Refused('unexpected container mount')
    if not {'/work','/fixture'}<=seen:raise Refused('missing bind mount')

def strict_json(payload):
    if not isinstance(payload,bytes) or len(payload)>65536:raise Refused('frame limit')
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise Refused('duplicate JSON key')
            d[k]=v
        return d
    try:return json.loads(payload.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(Refused('JSON constant')))
    except (UnicodeError,ValueError):raise Refused('invalid JSON') from None

def validate_result(r):
    if not isinstance(r,dict) or set(r)!={'version','result'} or type(r['version']) is not int or r['version']!=1:raise Refused('result envelope')
    result=r['result']
    if not isinstance(result,dict) or set(result)!={'Content','IsError'} or type(result['IsError']) is not bool or not isinstance(result['Content'],list) or len(result['Content'])>64:raise Refused('result shape')
    for c in result['Content']:
        if not isinstance(c,dict) or set(c)-{'type','text'} or c.get('type')!='text' or not isinstance(c.get('text',''),str):raise Refused('nontext result')
