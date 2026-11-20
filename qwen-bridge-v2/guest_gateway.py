"""Explicit guest gateway: 172.29.88.1:18761 -> 127.0.0.1:18760 only.
No vendor credential is accepted or present here. Requires parent's private reverse tunnel.
"""
import argparse
import datetime
import http.client
import hmac
import io
import sys
import threading
import time
from http.server import HTTPServer
from socketserver import ThreadingMixIn
from bridge import Bridge, Handler, DeadlineReader, BoundSocket, Denied, PATH, RESPONSE_CAP, remaining, read_task_key

class HeaderReader(DeadlineReader):
    """Absolute one-second and 8192-byte admission limit, before authentication."""
    def readinto(self, b):
        if getattr(self, 'authenticated', False): return super().readinto(b)
        if self.wire >= 8192: raise TimeoutError('header_limit')
        return super().readinto(memoryview(b)[:min(len(b), 8192-self.wire)])

class GatewayHandler(Handler):
    def handle(self):
        self.close_connection = True
        now = time.monotonic()
        self.request_deadline = min(now + 60, self.server.bridge.expires)
        self.connection.settimeout(max(.001, min(now + 1, self.request_deadline) - now))
        self.rfile.close()
        self.input_reader = HeaderReader(self.connection, min(now + 1, self.request_deadline))
        self.rfile = io.BufferedReader(self.input_reader, 1)
        self.handle_one_request()

    def parse_request(self):
        if not super().parse_request(): return False
        if self.input_reader.wire > 8192 or len(self.headers.get_all('Authorization', [])) != 1 or not hmac.compare_digest(
                self.headers['Authorization'], 'Bearer ' + self.server.bridge.task_key):
            self.send_error(401, 'auth'); return False
        self.input_reader.deadline = self.request_deadline
        self.input_reader.authenticated = True
        return True

class GatewayServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    def __init__(self, address, handler, bridge):
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(address, handler)
        self.bridge = bridge
    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try: super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise
    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.slots.release()

def forward(body, task_key, deadline):
    conn = http.client.HTTPConnection('127.0.0.1',18760,timeout=remaining(deadline))
    try:
        conn.connect()
        remaining(deadline)
        conn.sock = BoundSocket(conn.sock,deadline)
        conn.request('POST',PATH,body=body,headers={
            'Authorization':'Bearer '+task_key,'Content-Type':'application/json',
            'Accept-Encoding':'identity','Connection':'close'})
        response = conn.getresponse()
        remaining(deadline)
        if response.status != 200: return response.status,b''
        lengths = response.headers.get_all('Content-Length',[])
        if len(lengths)!=1 or not lengths[0].isdigit() or int(lengths[0])>RESPONSE_CAP or response.getheader('Transfer-Encoding'):
            raise Denied('framing',502)
        output=bytearray()
        while len(output)<int(lengths[0]):
            remaining(deadline)
            block=response.read1(min(16384,int(lengths[0])-len(output)))
            remaining(deadline)
            if not block: raise Denied('incomplete',502)
            output.extend(block)
        return 200,bytes(output)
    finally:
        if 'response' in locals(): response.close()
        conn.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serve-fixed-guest',action='store_true',required=True)
    p.add_argument('--task-key-file',required=True)
    p.add_argument('--deadline-utc',required=True)
    args=p.parse_args()
    try:
        if not args.deadline_utc.endswith('Z'): raise Denied('deadline')
        deadline=datetime.datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00')).timestamp()
        task=read_task_key(args.task_key_file)
        # Sentinel is not a credential; closure forwards ONLY the task key.
        bridge=Bridge(task,'gateway-no-vendor-credential-present',deadline,
                      transport=lambda body,_sentinel,end: forward(body,task,end))
        server=GatewayServer(('172.29.88.1',18761),GatewayHandler,bridge)
        server.bridge=bridge; server.timeout=.5
        while time.monotonic()<bridge.expires and time.time()<bridge.deadline_utc:
            server.handle_request()
        server.server_close()
    except Exception:
        print('gateway_start_or_runtime_failure',file=sys.stderr); return 2
    return 0
if __name__=='__main__': sys.exit(main())
