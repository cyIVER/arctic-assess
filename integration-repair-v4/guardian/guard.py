#!/usr/bin/python3 -I
"""Read-only task guard. Import has no effects. Deployment requires parent review.
Trust: VPS coordinator UID1000, guest root/kernel; NOT caller JSON or guest UID1001.
No cloud/SSH execution except --serve authenticated status; no mutation commands exist.
"""
import datetime
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import select
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import time

VM={'name':'vindler-lab-01','id':'590620893136303309','disk_id':'521979503200711885','project':'syncfall-ir-range','zone':'us-central1-a'}
ROOT='/run/artex-live-guard'
SOURCE='/opt/artex-live-guard/guard.py'
ALLOWLIST='/opt/artex-live-guard/allowlist.json'
CONTEXT='/run/artex-parent/run-context.json'
# Fixed trusted launcher role, never selected by request/config metadata.
HOST_UID=1000
HOST_ROOT='/home/iveri/.hermes/cache/scratch/artex-live-guard-v2'
HOST_SOURCE=HOST_ROOT+'/guard.py'
HOST_CONTEXT=HOST_ROOT+'/run-context.json'
SDK=HOST_ROOT+'/google-cloud-sdk'
GCLOUD=SDK+'/bin/gcloud'
VPS_PORT=18773
GUEST_PORT=18774
ROUTE='artex-live-guard-v1/status'
CAP=16384
TOTAL=9.0
BASE=[GCLOUD,'--account=andrew.iverson.2026@gmail.com','--project=syncfall-ir-range','--quiet']
class Blocked(RuntimeError): pass

def need(x,reason):
    if not x: raise Blocked(reason)

def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(b): return hashlib.sha256(b).hexdigest()
def finite(x): return type(x) in (int,float) and math.isfinite(x)
def utc(): return time.time()

def protected(path,sha=None,private=False,cap=1048576,host=False):
    """Guest root-only; host UID1000/root with proven exclusive700 ancestry.

    A writable ancestor BEFORE the shield always denies (rename attack).
    Below the shield only trusted owners may exist; public files still deny writes.
    host is a trusted code-only constructor argument, never JSON/RPC authority.
    """
    if host: need(os.getuid()==HOST_UID and os.geteuid()==HOST_UID,'host UID')
    owners=(0,HOST_UID) if host else (0,)
    shield=False
    p=Path(path)
    need(p.is_absolute() and str(p)==path and '..' not in p.parts,'protected path')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd); fd=nxt
            s=os.fstat(fd)
            need(s.st_uid in owners and (not s.st_mode&0o022 or (host and shield)),'protected ancestor')
            if host and stat.S_IMODE(s.st_mode)==0o700: shield=True
        if host: need(shield,'missing host privacy shield')
        if private: need(stat.S_IMODE(os.fstat(fd).st_mode)==0o700,'private directory')
        leaf=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            s=os.fstat(leaf)
            need(stat.S_ISREG(s.st_mode) and s.st_uid in owners and not s.st_mode&0o022 and s.st_size<=cap,'protected file')
            if private: need(stat.S_IMODE(s.st_mode)==0o600,'private file')
            with os.fdopen(leaf,'rb',closefd=False) as f: data=f.read(cap+1)
            need(len(data)<=cap,'file cap')
            if sha is not None: need(re.fullmatch('[a-f0-9]{64}',sha) and digest(data)==sha,'source pin')
            return data
        finally: os.close(leaf)
    finally: os.close(fd)

def pinned_object(ref): return json.loads(protected(ref['path'],ref['sha256']))

def verify_sdk(root,manifest):
    """Code-only private snapshot, no links. Manifest itself is parent-pinned.

    Do not aim this at account/config/cache directories. No auto-discovery/copy.
    """
    sdk=Path(root); actual=set()
    need(isinstance(manifest,dict) and bool(manifest),'SDK manifest')
    for parent,dirs,files in os.walk(sdk,followlinks=False):
        for p in [Path(parent)]+[Path(parent)/n for n in dirs]:
            s=p.lstat()
            need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,HOST_UID) and not s.st_mode&0o022,'SDK directory')
        for name in files:
            p=Path(parent)/name;rel=str(p.relative_to(sdk));actual.add(rel)
            need(rel in manifest,'SDK unreviewed file')
            protected(str(p),manifest[rel],cap=134217728,host=True)
    need(actual==set(manifest) and 'bin/gcloud' in actual,'SDK manifest completeness')

def load_scope(role='guest'):
    need(role in ('guest','vps'),'fixed role')
    host=role=='vps'
    need((os.getuid()==HOST_UID and os.geteuid()==HOST_UID) if host else os.geteuid()==0,'host UID' if host else 'root-only')
    source=HOST_SOURCE if host else SOURCE
    root=HOST_ROOT if host else ROOT
    context=HOST_CONTEXT if host else CONTEXT
    allowlist=HOST_ROOT+'/allowlist.json' if host else ALLOWLIST
    def read(path,*args,**kw):
        if host: need(Path(path).is_relative_to(HOST_ROOT),'host task boundary')
        return protected(path,*args,host=True,**kw) if host else protected(path,*args,**kw)
    def pinned(ref):return json.loads(read(ref['path'],ref['sha256']))
    # This allowlist is installed by the parent AFTER independent source review.
    # It is not a caller-selectable review path or approval metadata supplied to RPC.
    a=json.loads(read(allowlist)); code=read(source,a['guard_sha256'])
    need(Path(__file__).absolute()==Path(source),'canonical entrypoint')
    c=json.loads(read(root+'/parent.json',private=True))
    ctx=json.loads(read(context,private=True))
    # Shared context always pins the GUEST canonical path and SAME source bytes.
    need(ctx['guardian_implementation']=={'path':SOURCE,'sha256':digest(code)},'context source pin')
    for key in ('vm','lane','guard_created','external_stop','controller_id','preflight'):
        need(c[key]==ctx[key],'parent context binding')
    need(c['parent_scope_lease']==ctx['parent_scope_lease'],'parent lease binding')
    need(ctx['guardian_review']==a['guardian_review'],'canonical review binding')
    review=pinned(a['guardian_review'])
    need(review['status']=='approved' and review['object_sha256']==digest(code),'review source binding')
    need(c['schema']==1 and c['vm']==VM and c['lane']=='literal-no-model-isolation','parent scope')
    need(all(finite(c[k]) for k in ('guard_created','external_stop')) and c['guard_created']<=utc()<c['external_stop'] and 0<c['external_stop']-c['guard_created']<=5400,'parent lease')
    if role!='vps': return c
    need(c['controller']['uid']==HOST_UID,'fixed controller UID')
    need(c['controller']['script']['sha256']==a['controller_sha256'],'reviewed controller source')
    protected(c['controller']['exe'],a['controller_exe_sha256'],cap=134217728)
    protected(str(Path('/usr/bin/python3').resolve()),a['sdk_python_sha256'],cap=134217728)
    # Snapshot contains only reviewed official SDK code, never auth context.
    verify_sdk(SDK,pinned(a['gcloud_manifest']))
    read(c['controller']['script']['path'],c['controller']['script']['sha256'])
    checkpoint=pinned(c['controller']['checkpoint'])
    need(checkpoint['deadline']==datetime.datetime.fromtimestamp(c['external_stop'],datetime.timezone.utc).isoformat()
         or timestamp(checkpoint['deadline'])==c['external_stop'],'controller deadline')
    need(Path(c['controller']['checkpoint']['path'])==Path(c['controller']['script']['path']).parent/'approval-checkpoint.json','controller checkpoint location')
    return c

def timestamp(s):
    t=datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
    need(t.tzinfo is not None,'timezone'); v=t.timestamp(); need(finite(v),'timestamp'); return v

def run_command(argv,timeout):
    # Existing normal gcloud account context only. Never read/copy/log its files.
    return subprocess.run(argv,capture_output=True,text=True,timeout=timeout,
        env={'PATH':'/usr/bin:/bin','HOME':'/home/iveri','PYTHONDONTWRITEBYTECODE':'1',
             'CLOUDSDK_PYTHON':'/usr/bin/python3','CLOUDSDK_PYTHON_ARGS':'-I -B','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL)

def proc_identity(c):
    pid=c['pid']; need(type(pid)is int and pid>1 and pid!=os.getpid(),'external PID')
    fd=os.pidfd_open(pid)
    try:
        need(not select.select([fd],[],[],0)[0],'controller exited')
        root=Path('/proc')/str(pid)
        s=(root/'stat').read_text(); fields=s[s.rfind(')')+2:].split()
        need(fields[0] not in ('Z','X') and int(fields[1])!=os.getpid(),'controller independence')
        need(root.stat().st_uid==c['uid'] and int(fields[19])==c['start_ticks'],'controller UID/starttime')
        need(os.readlink(root/'exe')==c['exe'],'controller exe')
        # cmd hash is an additional public identity check, NEVER a replacement for pidfd/starttime.
        cmd=(root/'cmdline').read_bytes(); need(digest(cmd)==c['cmd_sha256'],'controller command')
        need(os.fsencode(c['script']['path']) in cmd.split(b'\0'),'controller script argument')
        need(not select.select([fd],[],[],0)[0],'controller exited')
        return fd
    except BaseException:
        os.close(fd); raise

def release_identity(fd):
    try: need(not select.select([fd],[],[],0)[0],'controller exited during readback')
    finally: os.close(fd)

class VPSGuardReadback:
    """Constructor is trusted parent-only. No request field can reach it."""
    def __init__(self,scope,runner=run_command,clock=utc,controller_check=proc_identity,controller_release=release_identity):
        self.scope=scope;self.runner=runner;self.clock=clock
        self.controller_check=controller_check;self.controller_release=controller_release
    def status(self):
        try: return self._status()
        except Blocked: raise
        except Exception: raise Blocked('readback failed') from None
    def _status(self):
        c=self.scope; need(isinstance(c,dict),'missing live parent input/review')
        now=self.clock(); start=time.monotonic()
        need(c['schema']==1 and c['vm']==VM and c['lane']=='literal-no-model-isolation','scope')
        need(all(finite(v) for v in (now,c['guard_created'],c['external_stop'])),'finite lease')
        need(c['guard_created']<=now<c['external_stop'] and 0<c['external_stop']-c['guard_created']<=5400,'lease expired/extended')
        need(isinstance(c['controller_id'],str) and 0<len(c['controller_id'])<=128,'controller handle')
        token=self.controller_check(c['controller'])
        try:
            def query(args):
                remaining=TOTAL-(time.monotonic()-start); need(remaining>0,'readback timeout')
                r=self.runner(args,timeout=remaining)
                need(r.returncode==0 and len(r.stdout)<=1048576,'readback command')
                return json.loads(r.stdout)
            v=query(BASE+['compute','instances','describe',VM['name'],'--zone='+VM['zone'],'--format=json'])
            need(v['id']==VM['id'] and v['name']==VM['name'] and v['status']=='RUNNING','provider identity/state')
            need(not v.get('serviceAccounts'),'service account')
            n=v['networkInterfaces'];need(len(n)==1,'NIC count')
            need(not n[0].get('accessConfigs') and not n[0].get('ipv6AccessConfigs') and not n[0].get('ipv6Address') and not n[0].get('externalIpv6'),'public IP/IPv6')
            for k in ('network','subnetwork','networkIP'):
                # GCE selfLinks may be fully qualified; compare project-relative exact scope.
                actual=n[0][k]
                if k!='networkIP': actual=actual.removeprefix('https://www.googleapis.com/compute/v1/')
                need(actual==c['network'][k],'network drift')
            disks=v['disks'];need(len(disks)==1 and disks[0].get('autoDelete') is False and disks[0].get('boot') is True,'disk retained')
            need(disks[0]['source'].removeprefix('https://www.googleapis.com/compute/v1/')=='projects/syncfall-ir-range/zones/us-central1-a/disks/vindler-lab-01','disk source')
            s=v['scheduling'];need(s.get('automaticRestart') is False and s.get('instanceTerminationAction')=='STOP' and timestamp(s['terminationTime'])==c['external_stop'],'provider absolute STOP')
            disk=query(BASE+['compute','disks','describe',VM['name'],'--zone='+VM['zone'],'--format=json'])
            need(disk['id']==VM['disk_id'] and disk['name']==VM['name'],'disk identity')
            # No SSH fallback: an absent existing mux hits /usr/bin/false, not a new IAP session.
            guest=query(['/usr/bin/ssh','-S',HOST_ROOT+'/iap.sock','-o','ControlMaster=no','-o','ProxyCommand=/usr/bin/false',
                '-o','BatchMode=yes','-o','ConnectTimeout=2','vindleradmin@vindler-lab-01',
                'sudo -n /usr/bin/python3 -I -B /opt/artex-live-guard/guard.py --guest-inventory'])
            need(guest=={'default_docker_quiescent':True,'checkpoint_sha256':c['preflight']['sha256']},'default daemon/checkpoint')
            second=self.controller_check(c['controller']); self.controller_release(second)
            need(time.monotonic()-start<TOTAL and self.clock()<c['external_stop'],'readback expired')
            return {'alive':True,'provider_state':'RUNNING','vm':VM,'stop_at':c['external_stop'],
                'controller_id':c['controller_id'],'guard_created':c['guard_created'],
                'default_docker_quiescent':True,'preflight_checkpoint_sha256':c['preflight']['sha256']}
        finally: self.controller_release(token)

VERSIONS={'docker.io':'29.1.3-0ubuntu3~24.04.2','containerd':'2.2.1-0ubuntu1~24.04.4','runc':'1.3.4-0ubuntu1~24.04.1'}
def validate_checkpoint(p,c,now):
    """V4 single exact immutable contract; same body in standalone guardian."""
    lease=c['parent_scope_lease']
    number=lambda v:type(v) in (int,float) and math.isfinite(v)
    need(type(lease) is dict and set(lease)=={'handle','vm','created','deadline','lane'},'checkpoint typed lease')
    need(type(lease['handle']) is str and 0<len(lease['handle'])<=256 and lease['vm']==c['vm'] and lease['lane']==c['lane'],'checkpoint lease scope')
    need(all(number(lease[k]) for k in ('created','deadline')) and number(c['external_stop']) and number(now),'checkpoint finite scope')
    need(all(k not in c or (type(c[k]) is type(lease[k]) and c[k]==lease[k]) for k in ('created','deadline')),'checkpoint phase scope')
    need(type(p) is dict and type(p.get('schema')) is int and p['schema']==1,'checkpoint schema')
    need(all(number(p.get(k)) for k in ('created','deadline','external_stop')),'checkpoint strict timestamps')
    expected={'schema':1,'status':'verified','requirement':'already-private-default-quiescent','vm':c['vm'],'created':lease['created'],'deadline':lease['deadline'],'parent_scope_lease':lease['handle'],'default_service_changes_owner':'parent','external_stop':c['external_stop'],'default_inventory':{'containers':[],'images':[],'volumes':[]}}
    need(p==expected,'parent preflight checkpoint')
    need(0<=now-p['created']<=120 and now<p['deadline'] and p['external_stop']>=p['deadline']+30,'checkpoint stale/deadline')
    return p

def guest_inventory(scope,runner=run_command,clock=utc,read=protected):
    """Fresh inactive state + package integrity. No Docker API call/socket activation."""
    start=time.monotonic()
    def checked(argv):
        left=TOTAL-(time.monotonic()-start);need(left>0,'guest inventory deadline')
        r=runner(argv,timeout=left);need(r.returncode==0,'guest inventory command');return r.stdout.strip()
    raw=read(scope['preflight']['path'],scope['preflight']['sha256'])
    p=json.loads(raw)
    need(digest(raw)==scope['preflight']['sha256'],'checkpoint returned bytes pin')
    need(scope['vm']==VM,'preflight VM')
    validate_checkpoint(p,scope,clock())
    versions=checked(['/usr/bin/dpkg-query','-W','-f=${Package}=${Version}\n','docker.io','containerd','runc'])
    need(set(versions.splitlines())=={k+'='+v for k,v in VERSIONS.items()},'package versions')
    need(not checked(['/usr/bin/dpkg','--verify','docker.io','containerd','runc']),'package integrity')
    for unit in ('docker.service','docker.socket'):
        out=checked(['/usr/bin/systemctl','show',unit,'-p','LoadState','-p','ActiveState','-p','SubState','-p','FragmentPath','-p','DropInPaths','-p','MainPID'])
        props=dict(line.split('=',1) for line in out.splitlines() if '=' in line)
        need(props.get('LoadState')=='loaded' and props.get('ActiveState')=='inactive' and props.get('MainPID')=='0' and not props.get('DropInPaths'),'default daemon active/override')
        path=props.get('FragmentPath');need(path in ('/usr/lib/systemd/system/'+unit,'/lib/systemd/system/'+unit),'unit path')
        # /lib is an OS symlink: resolve canonical package path before protected checks.
        canonical_path=str(Path(path).resolve());read(canonical_path)
        need(checked(['/usr/bin/dpkg-query','-S',path]).startswith('docker.io:'),'unit package owner')
    # Check both again after package inspection to narrow a state transition race.
    for unit in ('docker.service','docker.socket'):
        need(checked(['/usr/bin/systemctl','show',unit,'-p','ActiveState','--value'])=='inactive','default daemon raced')
    listeners=checked(['/usr/bin/ss','-lxH'])
    need(not ({'/run/docker.sock','/var/run/docker.sock'} & set(listeners.split())),'default socket listening')
    return {'default_docker_quiescent':True,'checkpoint_sha256':digest(raw)}

# Small length-prefixed HMAC channel, distinct from the model bridge. Key never in argv/env/log.
def mac(key,obj): return hmac.new(key,canonical(obj),hashlib.sha256).hexdigest()
def read_frame(s,deadline=None):
    if deadline is None: deadline=time.monotonic()+10
    def take(n):
        out=b''
        while len(out)<n:
            left=deadline-time.monotonic();need(left>0,'frame deadline');s.settimeout(left)
            b=s.recv(n-len(out));need(bool(b),'truncated frame');out+=b
        return out
    n=struct.unpack('!I',take(4))[0];need(0<n<=CAP,'frame cap')
    return json.loads(take(n))
def write_frame(s,obj):
    b=canonical(obj);need(len(b)<=CAP,'frame cap');s.sendall(struct.pack('!I',len(b))+b)

class StatusRPC:
    def __init__(self,key,readback,clock=utc):
        need(isinstance(key,bytes) and len(key)==32,'transport key');self.key=key;self.readback=readback;self.clock=clock;self.seen={}
    def respond(self,request):
        need(isinstance(request,dict) and set(request)=={'payload','mac'},'request envelope')
        p=request['payload'];need(isinstance(p,dict) and set(p)=={'route','nonce','time'},'fixed request fields')
        need(isinstance(request['mac'],str) and hmac.compare_digest(mac(self.key,p),request['mac']),'request auth')
        now=self.clock();need(finite(p['time']) and finite(now) and abs(now-p['time'])<=10,'request freshness')
        need(p['route']==ROUTE and isinstance(p['nonce'],str) and re.fullmatch('[a-f0-9]{64}',p['nonce']),'route/nonce')
        self.seen={n:t for n,t in self.seen.items() if now-t<=21}
        need(p['nonce'] not in self.seen and len(self.seen)<2048,'request replay/cap')
        self.seen[p['nonce']]=now
        data=self.readback.status()
        response={'nonce':p['nonce'],'time':self.clock(),'status':data}
        return {'payload':response,'mac':mac(self.key,response)}

def serve(scope,key):
    rpc=StatusRPC(key,VPSGuardReadback(scope))
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(10)
            try: write_frame(self.request,rpc.respond(read_frame(self.request,time.monotonic()+1)))
            except Exception: pass # closed connection is denial; no request/error data logged
    class Server(socketserver.TCPServer): allow_reuse_address=False
    # Serialized bounded requests, poll on invocation only, no cache/daemon/cron.
    with Server(('127.0.0.1',VPS_PORT),Handler) as server:
        server.timeout=.25
        while utc()<scope['external_stop']: server.handle_request()

def client_status(scope,key,clock=utc):
    deadline=time.monotonic()+10
    def remaining():
        left=deadline-time.monotonic();need(left>0,'client deadline');return left
    p={'route':ROUTE,'nonce':secrets.token_hex(32),'time':clock()}
    with socket.create_connection(('127.0.0.1',GUEST_PORT),timeout=remaining()) as s:
        s.settimeout(remaining());write_frame(s,{'payload':p,'mac':mac(key,p)})
        remaining();response=read_frame(s,deadline)
    remaining()
    need(set(response)=={'payload','mac'},'response envelope'); r=response['payload']
    need(isinstance(response['mac'],str) and hmac.compare_digest(mac(key,r),response['mac']),'response auth')
    need(set(r)=={'nonce','time','status'} and r['nonce']==p['nonce'] and finite(r['time']) and abs(clock()-r['time'])<=10,'response freshness')
    expected={'alive':True,'provider_state':'RUNNING','vm':VM,'stop_at':scope['external_stop'],
              'controller_id':scope['controller_id'],'guard_created':scope['guard_created'],
              'default_docker_quiescent':True,'preflight_checkpoint_sha256':scope['preflight']['sha256']}
    need(r['status']==expected and clock()<scope['external_stop'],'status binding/expiry')
    remaining()
    return r['status']

def main(argv):
    try:
        need(argv in (['--status'],['--serve'],['--guest-inventory']),'fixed operation')
        c=load_scope('vps' if argv==['--serve'] else 'guest')
        if argv==['--guest-inventory']: result=guest_inventory(c)
        else:
            host=argv==['--serve']
            key=protected((HOST_ROOT if host else ROOT)+'/transport.key',private=True,cap=32,host=host);need(len(key)==32,'transport key')
            if argv==['--serve']:serve(c,key);return 0
            result=client_status(c,key)
        print(json.dumps(result,separators=(',',':')));return 0
    except Exception:
        print('BLOCKED',file=sys.stderr);return 2
if __name__=='__main__': sys.exit(main(sys.argv[1:]))
