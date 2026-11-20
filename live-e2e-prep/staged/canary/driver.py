"""Explicit live CLI: absent authority => BLOCKED/2, no mutations.
Do not invoke --live on the local authoring machine. Future guest only.
"""
import argparse
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time
from guest import *
import probes

from v2_cases import install_strict_output_budget,restart_fence,cancel_inflight,exhaust_output,ScopeBudget
# No hardcoded forever-INCOMPLETE status. Actual guest evidence must satisfy all.
UNIMPLEMENTED=[]
REQUIRED_CASES={'environment-proxy','inflight-cancellation','phase-restart','aggregate-output-exhaustion'}
ALL_REQUIRED_CASES=REQUIRED_CASES|{'confinement','app-data','host-absence','fixture-http','quota-enospc','setsid-success','timeout-setsid','fifo-create','fifo-read','work-ordinary-swap','work-symlink-swap','fixture-ordinary-swap','fixture-symlink-swap'}
EXTERNAL_GATES=['current-parent-scope-lease','new-reviewed-proxy-source-helper','independent-code-reviews','fresh-provider-controller-guard','parent-default-docker-quiescence','actual-guest-canary-observations']

def bounded_transport(policy,phase):
    from bounded_transport import ReadCappedDockerCLI
    return ReadCappedDockerCLI(policy,phase)

def inspect_conditions(v):
    h=v['HostConfig'];cfg=v['Config']
    need(all(type(h[k]) is int for k in ('PidsLimit','Memory','MemorySwap')),'strict runtime resource integers')
    need(cfg['User']=='1001:1002' and h['ReadonlyRootfs'] is True,'independent user/rootfs')
    need(h['NetworkMode']=='none' and h['PidMode']=='private' and h['IpcMode']=='private','independent namespaces')
    need(h['CapDrop']==['ALL'] and 'no-new-privileges' in h['SecurityOpt'],'independent caps/nnp')
    need(h['PidsLimit']==64 and h['Memory']==268435456 and h['MemorySwap']==268435456,'independent resource bounds')
    need(cfg['Entrypoint']==['/usr/local/bin/artex-worker-tools'],'independent helper entrypoint')
    need(set(cfg.get('Volumes') or {})=={'/app/data'},'independent inherited volumes')
    return {'user':cfg['User'],'readonly_root':h['ReadonlyRootfs'],'network':h['NetworkMode'],'pid':h['PidMode'],'ipc':h['IpcMode'],'cap_drop':h['CapDrop'],'security_opt':h['SecurityOpt'],'memory':h['Memory'],'memory_swap':h['MemorySwap'],'pids':h['PidsLimit'],'mounts':v['Mounts'],'tmpfs':h['Tmpfs']}

class ObservedDriver:
    """Wrap frozen real DockerCLI, not a replacement for the H2 byte protocol."""
    def __init__(self,base,c,r,phase=None):
        self.base,self.c,self.r=base,c,r;self.effects=[];self.current=None;self.before_create=None;self.active=False;self.phase=phase
    def inspect(self,name):
        return json.loads(self.r.run([self.c['docker_cli'],'--host',self.c['daemon'],'inspect',name],timeout=2,cap=65536))[0]
    def collect_runtime(self,e):
        v=self.inspect(e['name']);pid=v['State']['Pid'];need(type(pid)is int and pid>0,'running effect PID')
        e['runtime_config']=inspect_conditions(v)
        ns={kind:os.readlink(f'/proc/{pid}/ns/{kind}') for kind in ('pid','ipc','net','mnt')}
        need(all(ns[k]!=os.readlink('/proc/self/ns/'+k) for k in ns),'private runtime namespaces')
        status=dict(x.split(':',1) for x in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in x)
        need(status['Uid'].split()==['1001']*4 and status['Gid'].split()==['1002']*4,'running UID/GID')
        need(all(int(status[k].strip(),16)==0 for k in ('CapEff','CapPrm','CapBnd')) and status['NoNewPrivs'].strip()=='1','running privilege state')
        cg=Path(f'/proc/{pid}/cgroup').read_text().strip();need(cg.startswith('0::/'),'cgroup v2 required')
        relative=cg[4:];need('..' not in Path(relative).parts,'cgroup path')
        root=Path('/sys/fs/cgroup')/relative
        limits={n:(root/n).read_text().strip() for n in ('pids.max','memory.max')}
        need(limits=={'pids.max':'64','memory.max':'268435456'},'actual cgroup bounds')
        e['runtime']={'pid':pid,'namespaces':ns,'uid':status['Uid'].split(),'gid':status['Gid'].split(),'caps':{k:status[k].strip() for k in ('CapEff','CapPrm','CapBnd')},'nnp':status['NoNewPrivs'].strip(),'cgroup':cg,'limits':limits}
    def run(self,args,payload=b'',**kwargs):
        if args[0]=='create':
            if self.phase:self.phase.reserve()
            name=args[args.index('--name')+1];need(re.fullmatch('artex-effect-[a-f0-9]{32}',name),'generated effect name')
            self.current={'name':name,'create_attempted':True,'ack_payload_guard_entries':0,'removed':False};self.effects.append(self.current)
            guard(self.c,self.r,time.time())
            if self.before_create:self.before_create()
        e=self.current
        if args[:3]==['start','--attach','--interactive']:
            e['config']=inspect_conditions(self.inspect(e['name']))
            original=kwargs['payload_guard']
            @contextmanager
            def guarded():
                with original():
                    if 'runtime' not in e:self.collect_runtime(e)
                    e['ack_payload_guard_entries']+=1
                    yield
            kwargs['payload_guard']=guarded
            e['attached_started']=True
        try:out=self.base.run(args,payload,**kwargs)
        except Exception as exc:
            if e and args[0]=='rm':e['rm_error']=True
            if e and args[:3]==['start','--attach','--interactive']:
                e['transport_error_class']=type(exc).__name__
                e['mounted_object_mismatch']=str(exc)=='mounted object mismatch'
                e['transport_timed_out']=str(exc)=='cancelled or timeout'
            raise
        if e and args[0]=='ps' and args[-1]=='name=^/'+e['name']+'$':
            e['removed']=not bool(out.strip())
            if e['removed'] and 'runtime' in e:
                pid=e['runtime']['pid']
                try:ns=os.readlink(f'/proc/{pid}/ns/pid')
                except FileNotFoundError:ns=None
                need(ns!=e['runtime']['namespaces']['pid'],'effect init remains in owned PID namespace')
                cg=Path('/sys/fs/cgroup')/e['runtime']['cgroup'][4:]/'cgroup.procs'
                remaining=cg.read_text().split() if cg.exists() else []
                need(not remaining,'owned cgroup still contains processes')
                e['process_cleanup']={'same_owned_pid_namespace':False,'remaining_cgroup_pids':remaining}
        return out

def run(c, *, runner=None, clock=time.time):
    """Actual privileged guest path. Tests inject external commands; no inference."""
    r=runner or Runner();validate(c,clock());guard(c,r,clock())
    need(os.getuid()==0,'guest root required for bounded mount and UID setup')
    before=verify_owner(c,r) # all discovery before first mutation
    root=Path(c['root']);data=root/'data';work=data/'work';fixture=data/'fixture'
    target=None;gateway=None;control=None;quota=None;phase=None;broker=None;observed=None;mounted=False
    previous_public_env=os.environ.get('ARTEX_HOST_PUBLIC_CANARY')
    receipt={'schema':1,'lane':'literal-no-model-isolation','vm':VM,'status':'INCOMPLETE','runtime_proof':False,'unimplemented_gates':UNIMPLEMENTED,'canaries':[],'before_inventory':before}
    sys.dont_write_bytecode=True
    from reviewed_imports import load
    load(c)
    from hostbroker.broker import Policy,Scope,Broker,DockerCLI
    from hostbroker.gateway import Gateway,Budget
    from hostbroker.control import ControlServer
    from lifecycle import Phase,WorkspaceQuota
    from fixture_service import Target
    try:
        guard(c,r,clock());root.mkdir(mode=0o700)
        phase=Phase(str(root),c['deadline'],clock=clock);phase.start();install_strict_output_budget(phase)
        receipt['canaries'].append({'name':'phase-restart','facts':restart_fence(phase,r,c['python'])})
        save(root/'authority.json',{k:v for k,v in c.items() if k!='reviews'}|{'review_digests':{k:v['review_sha256'] for k,v in c['reviews'].items()}})
        from image_stage import derive
        receipt['image']=derive(c,r,root,clock)
        image=receipt['image']['id']
        data.mkdir(mode=0o700)
        guard(c,r,clock())
        mounted=True # ambiguous mount completion must quarantine, never disappear
        r.run(['/usr/bin/mount','-t','tmpfs','-o','rw,nodev,nosuid,noexec,size=64m,uid=1001,gid=1002,mode=0700','tmpfs',str(data)])
        quota=WorkspaceQuota(str(data),uid=1001,gid=1002,mountinfo=lambda:Path('/proc/self/mountinfo').read_text(),statvfs=os.fstatvfs);quota.verify()
        receipt['quota']={'device':os.fstat(quota.fd).st_dev,'inode':os.fstat(quota.fd).st_ino,'capacity':os.fstatvfs(quota.fd).f_blocks*os.fstatvfs(quota.fd).f_frsize,'mountinfo':[x for x in Path('/proc/self/mountinfo').read_text().splitlines() if str(data) in x]}
        for p in (work,fixture):p.mkdir(mode=0o700);os.chown(p,1001,1002)
        # Public synthetic host facts, not secrets, intentionally outside mounts.
        (root/'host-public-private-canary').write_text('PUBLIC_SYNTHETIC_HOST_ONLY\n');os.chmod(root/'host-public-private-canary',0o600)
        (root/'native-canary.key').write_bytes(os.urandom(32));os.chmod(root/'native-canary.key',0o600)
        os.environ['ARTEX_HOST_PUBLIC_CANARY']='PUBLIC_SYNTHETIC_HOST_ONLY'
        persistent=work/'persistent-public-canary';persistent.write_bytes(b'PUBLIC_SYNTHETIC_PERSISTENT\n');os.chown(persistent,1001,1002);os.chmod(persistent,0o600)
        target=Target(pinned(c['fixture_module'],c['reviews']['fixture']['sha256']),'/run/artex-target-'+root.name[-12:]);port=target.start();origin='http://127.0.0.1:'+str(port)
        budget=Budget();budget.stopped=phase.stopped
        # One aggregate byte/effect+HTTP budget and cancellation event, in
        # addition to the frozen Broker's independently enforced phase quotas.
        gateway_reserve=budget.reserve;gateway_charge=budget.charge
        def shared_reserve():phase.reserve();gateway_reserve()
        def shared_charge(n):phase.charge(n);gateway_charge(n)
        budget.reserve=shared_reserve;budget.charge=shared_charge
        gateway=Gateway(str(fixture/'gateway.sock'),origin,'127.0.0.1',budget,peer_uid=1001);gateway.start();os.chown(fixture/'gateway.sock',1001,1002)
        key=os.urandom(32) # not written, argv, env, mounted, or recorded
        policy=Policy(image,str(data),1001,1002,c['docker_cli'],c['daemon'])
        observed=ObservedDriver(bounded_transport(policy,phase),c,r,phase)
        broker=Broker(policy,[],driver=observed,reviewed=True)
        control,caller_path,control_path,client_dir,exec_dir=prepare_caller(c,key,broker,ControlServer)
        binding={'PhaseID':'literal-canary-'+root.name[-12:],'Generation':1,'TaskID':1,'ExplorationID':1,'IntentID':1,'Role':'worker','SessionID':'exp1-worker-i1','ExecutorID':'canary-h2','NetworkPolicyID':'owned-loopback-only'}
        scope=Scope(binding,str(work),str(fixture),ScopeBudget(phase),quota_bytes=LIMIT)
        def attach_charge(s):
            original=s.charge
            def charge(n):phase.charge(n);original(n)
            s.charge=charge
        attach_charge(scope)
        broker.register_scope(scope,lambda b:b==binding and not phase.stopped.is_set() and clock()<c['deadline'])
        def call(tool,inputs,*,binding_override=None):
            guard(c,r,clock()) # real ControlServer/Broker performs budget denial
            request={'Binding':binding_override or binding,'Tool':tool,'Input':inputs,'ToolUseID':'literal-canary-'+str(len(receipt['canaries']))}
            receipt.setdefault('requests',[]).append(request) # full public literal payload; never HMAC/key
            raw=call_caller(r,[str(caller_path)],timeout=min(20,c['deadline']-clock()),cap=65536,payload=json.dumps({'Socket':str(control_path),'Key':base64.b64encode(key).decode(),'Request':request}).encode())
            return json.loads(raw)
        normal=probes.requests(origin,port,[str(root/'host-public-private-canary'),str(root/'native-canary.key'),str(control_path),str(caller_path)])
        normal.append(('environment-proxy','Bash',{'command':probes.environment_proxy(origin)},'json'))
        for name,tool,inputs,expected in normal:
            start=len(observed.effects);before_ledger=target.ledger()
            begun=time.monotonic()
            try:
                result=call(tool,inputs);facts=probes.facts(result,'error' if expected=='error-or-outer-timeout' else expected)
            except Blocked:
                elapsed=time.monotonic()-begun
                effects=observed.effects[start:]
                need(expected in ('outer-timeout','error-or-outer-timeout') and len(effects)==1 and effects[0].get('transport_timed_out') is True and effects[0]['ack_payload_guard_entries']>0 and elapsed<=17,'expected bounded post-ACK tool timeout')
                facts={'outer_transport_timeout':True,'elapsed_seconds':elapsed}
            effects=observed.effects[start:]
            need(len(effects)==1 and effects[0].get('removed') is True and 'runtime' in effects[0],'actual effect+runtime+removal required')
            if name in ('fixture-http','environment-proxy'):
                delta=target.ledger()[len(before_ledger):]
                need([(x['method'],x['path'],x['status']) for x in delta]==[('GET','/',200),('HEAD','/',200)],'independent fixture requests')
                facts['independent_fixture_ledger']=delta
            receipt['canaries'].append({'name':name,'facts':facts,'effect':effects[0]})
            if name=='fifo-read':
                p=work/'canary-fifo';need(stat.S_ISFIFO(p.lstat().st_mode),'exact own fifo cleanup');p.unlink()
        # Actual daemon-consuming hook: replacement occurs after Broker pins paths,
        # immediately before Docker create. The real H2 transport must withhold ACK.
        for leaf in ('work','fixture'):
            for kind in ('ordinary','symlink'):
                original=work if leaf=='work' else fixture;old=original.with_name(original.name+'-held');replacement=original.with_name(original.name+'-replacement')
                swap_socket=None
                def swap():
                    nonlocal swap_socket
                    original.rename(old);replacement.mkdir(mode=0o700);os.chown(replacement,1001,1002)
                    if leaf=='fixture':
                        swap_socket=socket.socket(socket.AF_UNIX);swap_socket.bind(str(replacement/'gateway.sock'));os.chmod(replacement/'gateway.sock',0o600);os.chown(replacement/'gateway.sock',1001,1002)
                    if kind=='ordinary':replacement.rename(original)
                    else:original.symlink_to(replacement,target_is_directory=True)
                start=len(observed.effects);observed.before_create=swap;denied=False
                try:call('Write',{'file_path':'/work/swap-effect','content':'PUBLIC_SYNTHETIC_ONLY'})
                except Blocked:denied=True
                finally:
                    observed.before_create=None
                    if old.exists():
                        if original.is_symlink():original.unlink()
                        else:original.rename(replacement)
                        old.rename(original)
                    if swap_socket:swap_socket.close()
                    if replacement.exists():
                        if leaf=='fixture':(replacement/'gateway.sock').unlink()
                        need(not list(replacement.iterdir()),'replacement has unexpected effect');replacement.rmdir()
                effects=observed.effects[start:]
                need(denied and len(effects)==1 and effects[0]['removed'] and effects[0].get('attached_started') and effects[0].get('mounted_object_mismatch') is True and effects[0]['ack_payload_guard_entries']==0 and not (work/'swap-effect').exists(),'actual swap denied before ACK/Input')
                receipt['canaries'].append({'name':leaf+'-'+kind+'-swap','effect':effects[0],'facts':{'caller_exit':2,'ack_guard_entries':0,'write_effect_exists':False}})
        # Cancel an already admitted real nativeexec call, then observe exact
        # whole-container removal/cgroup/PID absence, not caller exit alone.
        cancel_start=len(observed.effects)
        receipt['canaries'].append({'name':'inflight-cancellation','facts':cancel_inflight(call,broker,binding,scope,observed,lambda:len(observed.effects)>cancel_start and observed.effects[-1]['ack_payload_guard_entries']>0 and 'runtime' in observed.effects[-1])})
        # Literal isolation-only second Intent; SAME Phase+Broker+quota. A scope
        # cancellation must not refund calls/bytes or force a fresh phase.
        work2=data/'work-output';work2.mkdir(mode=0o700);os.chown(work2,1001,1002)
        binding2=binding|{'IntentID':2,'SessionID':'exp1-worker-i2'}
        scope2=Scope(binding2,str(work2),str(fixture),ScopeBudget(phase),quota_bytes=LIMIT);attach_charge(scope2)
        broker.register_scope(scope2,lambda b:b==binding2 and not phase.stopped.is_set() and clock()<c['deadline'])
        need(scope.quota is scope2.quota,'scope registration reset shared phase quota')
        receipt['canaries'].append({'name':'aggregate-output-exhaustion','facts':exhaust_output(phase,lambda tool,inputs:call(tool,inputs,binding_override=binding2),observed)})
        receipt['subset_runtime_observed']=True
        receipt['missing_canaries']=sorted(ALL_REQUIRED_CASES-{x['name'] for x in receipt['canaries']})
        need(not receipt['missing_canaries'],'required runtime canary missing')
        receipt['status']='OBSERVED_PENDING_CLEANUP'
    except BaseException as exc:
        receipt['status']='FAILED';receipt['error_class']=type(exc).__name__
    finally:
        if previous_public_env is None:os.environ.pop('ARTEX_HOST_PUBLIC_CANARY',None)
        else:os.environ['ARTEX_HOST_PUBLIC_CANARY']=previous_public_env
        cleanup=[];safe=True
        if phase:phase.pause();phase.cancel()
        for name,obj in [('control',control),('gateway',gateway),('target',target)]:
            if obj:
                try:cleanup.append({'component':name,'settled':True,'readback':obj.close()})
                except Exception as exc:safe=False;cleanup.append({'component':name,'settled':False,'error_class':type(exc).__name__})
        if observed:
            safe=safe and all(e['removed'] for e in observed.effects)
            receipt['effects']=observed.effects
        if broker:
            safe=safe and all(not s.quarantined for s in broker.scopes.values())
        receipt['cleanup']=cleanup
        try:
            after=inventory(c,r);receipt['after_inventory']=after
            need(after['containers']==before['containers'] and after['volumes']==before['volumes'] and set(before['images'])<=set(after['images']),'standing inventory not preserved')
            need(set(after['images'])-set(before['images'])<=({receipt['image']['id']} if 'image' in receipt else set()),'unexpected added image')
            receipt['old_inventory_preserved']=True
        except Exception as exc:safe=False;receipt['inventory_error_class']=type(exc).__name__
        if mounted and safe:
            try:
                quota.verify();receipt['archive']=checkpoint(work,root/'workspace.tar')
                # Archive readback done; close FDs only after all containers settled.
                if broker:
                    for p in broker._pins.values():p.close()
                quota.close();r.run(['/usr/bin/umount',str(data)])
                need(not any(line.split(' - ')[0].split()[4]==str(data) for line in Path('/proc/self/mountinfo').read_text().splitlines()),'unmount readback')
                receipt['unmounted']=True
            except Exception as exc:safe=False;receipt['archive_unmount_error_class']=type(exc).__name__
        receipt['quarantined']=not safe
        receipt['missing_canaries']=sorted(ALL_REQUIRED_CASES-{x['name'] for x in receipt['canaries']})
        if safe and receipt['status']=='OBSERVED_PENDING_CLEANUP' and receipt.get('unmounted') and receipt.get('old_inventory_preserved'):
            receipt['status']='COMPLETE';receipt['runtime_proof']=True
        receipt['commands']=r.events
        if root.exists():save(root/'receipt.json',receipt)
        # On uncertainty retain mount, source FDs and the live process for parent
        # independent cleanup; never close quarantined reservations or reuse paths.
    if not safe:return receipt,3,{'broker':broker,'quota':quota,'phase':phase}
    return receipt,(0 if receipt['status']=='COMPLETE' else 2),None

def main():
    p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--live',action='store_true');args=p.parse_args()
    if not args.live or not args.config:
        print(json.dumps({'status':'BLOCKED','reason':'explicit --live plus current parent-approved input required','runtime_proof':False,'unresolved_gates':EXTERNAL_GATES}));return 2
    try:
        from admission_v3 import protected_json
        c=protected_json(args.config);receipt,rc,retained=run(c)
        print(json.dumps({'status':receipt['status'],'receipt':str(Path(c['root'])/'receipt.json'),'runtime_proof':receipt['runtime_proof'],'quarantined':receipt['quarantined']}))
        if retained:
            # Parent's external absolute STOP overrides this retention hold.
            while time.time()<c['external_stop']:time.sleep(.1)
        return rc
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason_class':type(exc).__name__,'runtime_proof':False}));return 2
if __name__=='__main__':sys.exit(main())
