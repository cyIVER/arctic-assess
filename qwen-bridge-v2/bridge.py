"""Private fixed-destination OpenAI transport. No effects on import; stdlib only."""
import argparse
import datetime
import hmac
import http.client
import io
import json
import os
import socket
import ssl
import stat
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = 'iverson-pc-1.tail8ccbd1.ts.net'
PATH = '/v1/chat/completions'
MODEL = 'qwen3.5-9b'
REQUEST_CAP = RESPONSE_CAP = 2 * 1024 * 1024
TOTAL_CAP = 8 * 1024 * 1024

class Denied(Exception):
    def __init__(self, code='denied', status=400):
        self.code, self.status = code, status
        super().__init__(code)

def remaining(deadline):
    n = deadline - time.monotonic()
    if n <= 0:
        raise Denied('deadline', 504)
    return n

def strict_json(body):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result: raise ValueError('duplicate')
            result[k] = v
        return result
    try:
        return json.loads(body.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError):
        raise Denied('invalid_json') from None

class DeadlineReader(io.RawIOBase):
    def __init__(self, sock, deadline):
        self.sock, self.deadline, self.wire = sock, deadline, 0
    def readable(self): return True
    def readinto(self, b):
        self.sock.settimeout(remaining(self.deadline))
        n = self.sock.recv_into(b)
        remaining(self.deadline)
        self.wire += n
        if self.wire > RESPONSE_CAP + 65536: raise Denied('response_cap', 502)
        return n

class BoundSocket:
    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline
        self.reader = DeadlineReader(sock, deadline)
    def makefile(self, *args, **kwargs): return io.BufferedReader(self.reader, 4096)
    def __getattr__(self, name): return getattr(self.sock, name)

def upstream(body, vendor_key, deadline):
    """No environment proxy, redirect handling, retries, or caller routing."""
    conn = http.client.HTTPSConnection(HOST, 443, timeout=remaining(deadline),
                                       context=ssl.create_default_context())
    try:
        conn.connect()  # TLS hostname and CA verification are mandatory.
        remaining(deadline)
        conn.sock.settimeout(remaining(deadline))
        bound = BoundSocket(conn.sock, deadline)
        conn.sock = bound
        conn.request('POST', PATH, body=body, headers={
            'Authorization': 'Bearer ' + vendor_key,
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'Accept-Encoding': 'identity', 'Connection': 'close'})
        remaining(deadline)
        response = conn.getresponse()
        remaining(deadline)
        if bound.reader.wire > 65536:
            raise Denied('headers_cap', 502)
        # Never return error reasons, headers, locations, or bodies to callers.
        if response.status != 200: return response.status, b''
        if response.getheader('Content-Encoding', 'identity') != 'identity':
            raise Denied('encoding', 502)
        if response.getheader('Transfer-Encoding') not in (None, 'chunked'):
            raise Denied('framing', 502)
        lengths = response.headers.get_all('Content-Length', [])
        if len(lengths) > 1 or (lengths and response.getheader('Transfer-Encoding')):
            raise Denied('framing', 502)
        if lengths and (not lengths[0].isdigit() or int(lengths[0]) > RESPONSE_CAP):
            raise Denied('response_cap', 502)
        output = bytearray()
        while True:
            remaining(deadline)
            block = response.read1(min(16384, RESPONSE_CAP + 1 - len(output)))
            remaining(deadline)
            output.extend(block)
            if len(output) > RESPONSE_CAP: raise Denied('response_cap', 502)
            if not block: break
        if lengths and len(output) != int(lengths[0]): raise Denied('incomplete', 502)
        return 200, bytes(output)
    finally:
        if 'response' in locals(): response.close()
        conn.close()

# Unknown application fields survive; transport selectors never do.
FORBIDDEN = {'url', 'base_url', 'endpoint', 'proxy', 'headers', 'authorization',
             'api_key', 'api_base', 'host', 'port', 'model_selector', 'fallback', 'retries'}
def transport_fields(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if k.lower() in FORBIDDEN or k.lower().endswith('_url'):
                raise Denied('transport_selector')
            transport_fields(v)
    elif isinstance(value, list):
        for v in value: transport_fields(v)

class Bridge:
    def __init__(self, task_key, vendor_key, deadline_utc, *, transport=upstream):
        now = time.time()
        if not now < deadline_utc <= now + 1800: raise Denied('session_deadline')
        for key in (task_key, vendor_key):
            if not isinstance(key, str) or len(key) < 24 or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise Denied('credential_format')
        if hmac.compare_digest(task_key, vendor_key): raise Denied('distinct_credentials')
        self.task_key, self.vendor_key = task_key, vendor_key
        self.expires = time.monotonic() + deadline_utc - now
        self.deadline_utc = deadline_utc
        self.transport = transport
        self.calls = self.response_bytes = 0
        self.lock = threading.Lock()
        self.terminal = False

    def request(self, method, path, authorization, body, *, deadline=None):
        started = time.monotonic()
        if not self.lock.acquire(blocking=False): raise Denied('busy', 429)
        try:
            if method != 'POST' or path != PATH: raise Denied('path', 404)
            if not hmac.compare_digest(authorization, 'Bearer ' + self.task_key): raise Denied('auth', 401)
            if self.terminal or time.time() >= self.deadline_utc: raise Denied('expired', 403)
            remaining(self.expires)
            if len(body) > REQUEST_CAP: raise Denied('request_cap', 413)
            request = strict_json(body)
            if not isinstance(request, dict): raise Denied('request_shape')
            if type(request.get('model')) is not str or request['model'] != MODEL: raise Denied('model')
            if request.get('stream', False) is not False: raise Denied('stream')
            if not isinstance(request.get('messages'), list): raise Denied('messages')
            transport_fields({k:v for k,v in request.items() if k not in ('messages','tools','functions','tool_choice','function_call','response_format')})
            for field in ('max_tokens', 'max_completion_tokens'):
                if field in request and (type(request[field]) is not int or not 1 <= request[field] <= 4096):
                    raise Denied('tokens')
            if 'max_tokens' in request and 'max_completion_tokens' in request: raise Denied('tokens')
            if not any(f in request for f in ('max_tokens','max_completion_tokens')): request['max_tokens'] = 4096
            request['stream'] = False
            wire = json.dumps(request, separators=(',', ':'), ensure_ascii=False).encode()
            if len(wire) > REQUEST_CAP: raise Denied('request_cap', 413)
            if self.calls >= 16 or self.response_bytes + RESPONSE_CAP > TOTAL_CAP: raise Denied('budget', 429)
            limit = min(started + 60, self.expires, deadline or self.expires)
            remaining(limit)
            self.calls += 1  # Never refunded, including failed upstream attempts.
            # One daemon operation: wall deadline also fences stalled DNS resolution.
            done = threading.Event(); result = []
            def run():
                try: result.append(self.transport(wire, self.vendor_key, limit))
                except BaseException: result.append(None)
                finally: done.set()
            threading.Thread(target=run, daemon=True).start()
            if not done.wait(remaining(limit)):
                self.terminal = True
                self.response_bytes += RESPONSE_CAP
                raise Denied('deadline', 504)
            remaining(limit)
            if not result or result[0] is None:
                self.response_bytes += RESPONSE_CAP
                raise Denied('upstream_failure', 502)
            status, output = result[0]
            self.response_bytes += min(len(output), RESPONSE_CAP)
            if status != 200: raise Denied('upstream_status', 502)
            if len(output) > RESPONSE_CAP: raise Denied('response_cap', 502)
            parsed = strict_json(output)
            # Reject literal and JSON-escaped credential echoes, including object keys.
            decoded = json.dumps(parsed, ensure_ascii=False)
            if any(secret in decoded or secret.encode() in output for secret in (self.task_key,self.vendor_key)):
                raise Denied('credential_echo', 502)
            return 200, output
        finally:
            self.lock.release()

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def handle(self):
        self.close_connection = True
        deadline = min(time.monotonic() + 60, self.server.bridge.expires)
        self.connection.settimeout(max(0.001, deadline - time.monotonic()))
        # Setup already made rfile; replace only real socket IO, not test fixtures.
        if hasattr(self.connection, 'recv_into'):
            self.rfile.close()
            self.input_reader = DeadlineReader(self.connection, deadline)
            self.rfile = io.BufferedReader(self.input_reader, 4096)
        self.request_deadline = deadline
        # Base handler is one-shot: never accept pipelined/persistent continuations.
        self.handle_one_request()
    def do_POST(self):
        started = time.monotonic()
        deadline = self.request_deadline
        try:
            if self.path != PATH: raise Denied('path', 404)
            if hasattr(self, 'input_reader') and self.input_reader.wire > 65536: raise Denied('headers_cap', 431)
            if len(self.headers.get_all('Authorization', [])) != 1: raise Denied('auth', 401)
            if not hmac.compare_digest(self.headers['Authorization'], 'Bearer ' + self.server.bridge.task_key): raise Denied('auth', 401)
            if self.headers.get('Transfer-Encoding') or self.headers.get('Expect'): raise Denied('framing')
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not lengths[0].isdigit(): raise Denied('length')
            size = int(lengths[0])
            if size > REQUEST_CAP: raise Denied('request_cap', 413)
            # Unbuffered body reads keep absolute socket deadline effective.
            body = bytearray()
            while len(body) < size:
                self.connection.settimeout(remaining(deadline))
                block = self.rfile.read1(min(16384,size-len(body)))
                remaining(deadline)
                if not block: raise Denied('incomplete')
                body.extend(block)
            status, output = self.server.bridge.request('POST', self.path,
                self.headers['Authorization'], bytes(body), deadline=deadline)
        except Denied as e:
            status, output = e.status, json.dumps({'error':{'code':e.code}}).encode()
        except Exception:
            status, output = 400, b'{"error":{"code":"request_failure"}}'
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(output)))
        self.send_header('Connection','close')
        self.end_headers(); self.wfile.write(output)
        # No prompt, key, path, error text, or response-body logging.
        print(json.dumps({'status':status,'calls':self.server.bridge.calls,
                          'response_bytes':self.server.bridge.response_bytes,
                          'elapsed_ms':int((time.monotonic()-started)*1000)}), flush=True)
    def do_GET(self):
        self.send_error(404, 'not_found')
    def send_error(self, code, message=None, explain=None):
        self.send_response(code); self.send_header('Content-Length','0')
        self.send_header('Connection','close'); self.end_headers()

def read_task_key(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
            raise Denied('task_key_file')
        data = f.read(513)
        if len(data) > 512: raise Denied('task_key_file')
        return data.decode('ascii').strip()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve-loopback',action='store_true',required=True)
    parser.add_argument('--task-key-file',required=True)
    parser.add_argument('--deadline-utc',required=True,help='Absolute ISO-8601 UTC ending Z, <=30 min')
    args = parser.parse_args()
    try:
        if not args.deadline_utc.endswith('Z'): raise Denied('session_deadline')
        deadline = datetime.datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00')).timestamp()
        task = read_task_key(args.task_key_file)
        # Vendor credential only from parent's private stdin pipe, never argv/env/file.
        vendor = sys.stdin.buffer.readline(513).decode('ascii').rstrip('\n')
        bridge = Bridge(task,vendor,deadline)
        server = HTTPServer(('127.0.0.1',18760),Handler)
        server.bridge = bridge; server.timeout = 0.5
        while time.monotonic() < bridge.expires and time.time() < bridge.deadline_utc:
            server.handle_request()
        server.server_close()
    except Exception:
        print('bridge_start_or_runtime_failure',file=sys.stderr)
        return 2
    return 0
if __name__ == '__main__': sys.exit(main())
