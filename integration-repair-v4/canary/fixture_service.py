"""Exact-child owned loopback target; loaded fixture bytes are parent reviewed."""
import json
import os
from pathlib import Path
import select
import signal
import time
from guest import need

def close_child_fds(keep):
    # proc list is captured before closes; all controller/quota/key descriptors
    # and stdio are dropped. Retain only the one startup report pipe.
    for name in os.listdir('/proc/self/fd'):
        fd=int(name)
        if fd!=keep:
            try:os.close(fd)
            except OSError:pass

class Target:
    def __init__(self, module_bytes, state):self.module_bytes=module_bytes;self.state=Path(state);self.pid=None
    def start(self):
        self.state.mkdir(mode=0o700);os.chown(self.state,1001,1002)
        r,w=os.pipe()
        self.pid=os.fork()
        if self.pid==0:
            os.close(r)
            try:
                os.setgroups([]);os.setgid(1002);os.setuid(1001)
                os.chdir(self.state);close_child_fds(w)
                ns={'__name__':'owned_fixture'};exec(compile(self.module_bytes,'owned-fixture-reviewed','exec'),ns)
                server=ns['create_server'](('127.0.0.1',0),str(self.state))
                os.write(w,json.dumps({'port':server.server_address[1],'uid':os.getuid(),'pid':os.getpid()}).encode()+b'\n');os.close(w)
                server.serve_forever(poll_interval=.05)
            except BaseException:os._exit(2)
            os._exit(0)
        os.close(w)
        try:
            need(bool(select.select([r],[],[],3)[0]),'target startup timeout')
            data=os.read(r,1024);self.identity=json.loads(data)
            need(self.identity['uid']==1001 and self.identity['pid']==self.pid,'target UID/PID')
            return self.identity['port']
        finally:os.close(r)
    def close(self):
        if self.pid is None:return
        # Unreaped exact child PID cannot be reused. No process scanning or pkill.
        os.kill(self.pid,signal.SIGTERM)
        end=time.monotonic()+2
        while time.monotonic()<end:
            pid,status=os.waitpid(self.pid,os.WNOHANG)
            if pid:self.pid=None;return {'reaped_pid':pid,'wait_status':status}
            time.sleep(.02)
        os.kill(self.pid,signal.SIGKILL);pid,status=os.waitpid(self.pid,0);self.pid=None
        return {'reaped_pid':pid,'wait_status':status}
    def ledger(self):
        p=self.state/'requests.jsonl';need(p.stat().st_size<=131072,'fixture ledger cap')
        return [json.loads(line) for line in p.read_bytes().splitlines()]
