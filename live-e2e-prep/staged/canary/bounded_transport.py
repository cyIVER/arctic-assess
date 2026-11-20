"""Task-local frozen H2 transport copy, only shared read-budget added.
Provenance: original hostbroker/broker.py DockerCLI. Never modifies frozen source.
"""
import json,os,selectors,subprocess,threading,time
from hostbroker.broker import Refused,strict_json,same_typed_json
class ReadCappedDockerCLI:
    def __init__(self, policy, phase): self.policy=policy;self.phase=phase
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
                        try:b=self.read_chunk(key.fd,charge)
                        except BlockingIOError:continue
                        if not b:
                            sel.unregister(key.fileobj)
                            if key.data=='out' and not verified:raise Refused('missing HELLO')
                            continue
                        total+=len(b)
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

    def read_chunk(self,fd,charge):
        if not charge:return os.read(fd,4096)
        # Linearize gateway charging against transport reads; never read a byte
        # beyond the SAME phase allowance, including H2 HELLO and stderr.
        with self.phase.lock:
            remaining=131072-self.phase.bytes
            if remaining<=0:raise Refused('shared output exhausted')
            b=os.read(fd,min(4096,remaining))
            if b:charge(len(b))
            return b
