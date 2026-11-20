"""Explicit guest gateway: 172.29.88.1:18761 -> 127.0.0.1:18760 only.
No vendor credential is accepted or present here. Requires parent's private reverse tunnel.
"""
import argparse
import datetime
import http.client
import sys
import time
from http.server import HTTPServer
from bridge import Bridge, Handler, BoundSocket, Denied, PATH, RESPONSE_CAP, remaining, read_task_key

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
        server=HTTPServer(('172.29.88.1',18761),Handler)
        server.bridge=bridge; server.timeout=.5
        while time.monotonic()<bridge.expires and time.time()<bridge.deadline_utc:
            server.handle_request()
        server.server_close()
    except Exception:
        print('gateway_start_or_runtime_failure',file=sys.stderr); return 2
    return 0
if __name__=='__main__': sys.exit(main())
