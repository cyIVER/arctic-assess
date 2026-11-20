"""No-model live canary seams. Local fixtures do not establish guest proof."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from guest import HERE,Blocked,need
import probes

class ScopeBudget:
    """Local revocation does not refund or cancel the shared phase allowance."""
    def __init__(self,phase):self.phase=phase;self.stopped=threading.Event()
    def check(self):
        self.phase.check();need(not self.stopped.is_set(),'scope cancelled')
    def cancel(self):self.stopped.set()

def install_strict_output_budget(phase):
    # Count accepted bytes at the cap; separately retain the observed rejected
    # read chunk. Nothing over the cap is delivered to nativeexec/model/caller.
    phase.observed_bytes=phase.bytes;phase.rejected_bytes=0
    def charge(n):
        with phase.lock:
            need(type(n)is int and n>=0,'charge type')
            phase.observed_bytes+=n
            accepted=min(n,max(0,131072-phase.bytes));phase.bytes+=accepted
            phase.rejected_bytes+=n-accepted
            if phase.bytes>=131072:
                phase.stopped.set();raise Blocked('shared aggregate output exhausted')
    phase.charge=charge

def restart_fence(phase,runner,python):
    before=(phase.calls,phase.bytes)
    marker=phase.root/'executor-started';digest=hashlib.sha256(marker.read_bytes()).hexdigest()
    raw=runner.run([python,str(HERE/'restart_probe.py'),'--root',str(phase.root),'--deadline',str(phase.deadline)],timeout=2,cap=4096)
    result=json.loads(raw)
    need(result=={'second_process_denied':True,'reason':'existing-phase-sentinel','docker_calls':0,'model_calls':0},'restart child did not reject sentinel')
    need((phase.calls,phase.bytes)==before and hashlib.sha256(marker.read_bytes()).hexdigest()==digest,'restart changed counters or sentinel')
    return result|{'counters_before':before,'counters_after':(phase.calls,phase.bytes),'marker_sha256':digest}

def cancel_inflight(call,broker,binding,scope,observed,ready):
    start=len(observed.effects);done=threading.Event();result={}
    def worker():
        try:call('Bash',{'command':"setsid sh -c 'sleep 60' >/dev/null 2>&1 & sleep 60",'timeout_ms':8000},binding_override=binding)
        except Blocked:result['caller_refused']=True
        except BaseException as e:result['unexpected_error']=type(e).__name__
        finally:done.set()
    t=threading.Thread(target=worker,daemon=True);t.start()
    end=time.monotonic()+4
    while not ready() and not done.is_set() and time.monotonic()<end:time.sleep(.005)
    if not ready():
        broker.revoke_scope(binding);t.join(8)
        if t.is_alive():scope.quarantined=True
        raise Blocked('cancel probe did not reach admitted inflight Input')
    broker.revoke_scope(binding)
    guards=sum(e['ack_payload_guard_entries'] for e in observed.effects[start:])
    t.join(8)
    if t.is_alive():scope.quarantined=True;raise Blocked('cancel settlement uncertain; retain reservations')
    effects=observed.effects[start:]
    need(result=={'caller_refused':True} and len(effects)==1,'cancel caller/effect mismatch')
    need(effects[0]['removed'] and effects[0].get('process_cleanup')=={'same_owned_pid_namespace':False,'remaining_cgroup_pids':[]},'whole exact effect cleanup not observed')
    need(sum(e['ack_payload_guard_entries'] for e in effects)==guards,'post-cancel Input write')
    n=len(observed.effects);denied=False
    try:call('LS',{'path':'/work'},binding_override=binding)
    except Blocked:denied=True
    need(denied and len(observed.effects)==n,'post-cancel new effect')
    return {'settled':True,'new_effects_after_cancel':0,'post_cancel_input_writes':0,'caller_refused':True,'effect':effects[0]}

def exhaust_output(phase,call,observed):
    # Must be terminal: exhausting the shared phase intentionally fences all scopes.
    if not hasattr(phase,'observed_bytes'):install_strict_output_budget(phase)
    start=len(observed.effects);admitted=0;attempts=0
    while not phase.stopped.is_set() and phase.bytes<131072 and phase.calls<32:
        attempts+=1;need(attempts<=10,'exhaustion probe bound')
        before=len(observed.effects)
        try:
            result=call('Bash',{'command':probes.command("import os;os.write(1,b'PUBLIC_STDOUT_'+b'O'*8000);os.write(2,b'PUBLIC_STDERR_'+b'E'*8000)")})
            text=''.join(c.get('text','') for c in result['result']['Content'])
            need(not result['result']['IsError'] and 'PUBLIC_STDOUT_' in text and 'PUBLIC_STDERR_' in text,'both finite public output streams required')
            admitted+=1
        except Blocked:
            need(phase.bytes==131072 and phase.stopped.is_set(),'non-exhaustion denial')
        need(len(observed.effects)==before+1 and observed.effects[-1]['removed'] and observed.effects[-1].get('runtime') and observed.effects[-1]['ack_payload_guard_entries']>0,'exhaustion effect admission/cleanup')
    need(admitted>0 and phase.bytes==131072 and phase.stopped.is_set(),'aggregate byte cap not reached after admitted effect')
    need(phase.observed_bytes<=131072 and phase.rejected_bytes==0,'transport read exceeded shared byte allowance')
    counters=(phase.calls,phase.bytes,phase.observed_bytes,phase.rejected_bytes);n=len(observed.effects);denied=False
    try:call('LS',{'path':'/work'})
    except Exception:denied=True
    need(denied and len(observed.effects)==n and counters==(phase.calls,phase.bytes,phase.observed_bytes,phase.rejected_bytes),'post-exhaustion refund/reset or effect')
    return {'exhausted':True,'admitted_before_exhaustion':admitted,'attempts':attempts,'effects':n-start,'shared_calls':phase.calls,'accepted_bytes':phase.bytes,'observed_wire_bytes':phase.observed_bytes,'rejected_read_bytes':phase.rejected_bytes,'post_exhaustion_new_effects':0}
