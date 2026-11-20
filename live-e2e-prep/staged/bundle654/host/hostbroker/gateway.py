"""Fixture-only, reconstructed HTTP over UDS. Never a generic proxy or dial RPC.
No activation/daemon entrypoint: trusted host policy must instantiate it.
"""
import ipaddress
import os
import re
import socket
import struct
import threading
import time
import urllib.parse

class Denied(Exception): pass

class Budget:
    def __init__(self, max_calls=32, max_bytes=131072):
        self.max_calls, self.max_bytes = max_calls, max_bytes
        self.calls = self.bytes = 0
        self.stopped = threading.Event()
        self.lock = threading.Lock()
    def check(self):
        if self.stopped.is_set(): raise Denied('cancelled')
    def reserve(self):
        with self.lock:
            self.check()
            if self.calls >= self.max_calls: raise Denied('call budget')
            self.calls += 1
    def charge(self, n):
        with self.lock:
            self.check()
            if n > self.max_bytes-self.bytes: raise Denied('byte budget')
            self.bytes += n
    def cancel(self): self.stopped.set()

class Gateway:
    def __init__(self, path, origin, peer_ip, budget, *, peer_uid, timeout=2., max_response=32768):
        u = urllib.parse.urlsplit(origin)
        if u.scheme != 'http' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
            raise ValueError('fixed bare HTTP origin required')
        ipaddress.ip_address(peer_ip)  # No DNS and no proxy environment.
        if not 0 < timeout <= 10 or not 0 < max_response <= 131072: raise ValueError('invalid limits')
        self.path, self.origin, self.authority = path, origin, u.netloc
        self.peer_ip, self.port, self.peer_uid = peer_ip, u.port or 80, peer_uid
        self.budget, self.timeout, self.max_response = budget, timeout, max_response
        self.closed = threading.Event()
    def start(self):
        # Never unlink an existing socket (another owner's live capability).
        self.listener = socket.socket(socket.AF_UNIX)
        try:
            self.listener.bind(self.path); os.chmod(self.path, 0o600)
            self.listener.listen(1); self.listener.settimeout(.05)
        except BaseException:
            self.listener.close(); raise
        self.thread = threading.Thread(target=self._loop, daemon=True); self.thread.start()
    def close(self):
        self.closed.set(); self.budget.cancel()
        self.thread.join(timeout=self.timeout+1)
        self.listener.close()
        if self.thread.is_alive(): raise RuntimeError('gateway did not settle')
        os.unlink(self.path)
    def _check(self, deadline):
        self.budget.check()
        if self.closed.is_set() or time.monotonic() >= deadline: raise Denied('deadline')
    def _recv(self, s, n, deadline):
        while True:
            self._check(deadline); s.settimeout(min(.05, max(.001, deadline-time.monotonic())))
            try: b = s.recv(n)
            except socket.timeout: continue
            self._check(deadline)
            return b
    def _send(self, s, data, deadline):
        view = memoryview(data)
        while view:
            self._check(deadline); s.settimeout(min(.05, max(.001, deadline-time.monotonic())))
            try: n = s.send(view)
            except socket.timeout: continue
            if n == 0: raise Denied('closed')
            self._check(deadline); view = view[n:]
    def _headers(self, s, deadline, cap=8192, charge=False):
        b = b''
        while b'\r\n\r\n' not in b:
            part = self._recv(s, min(1024, cap+1-len(b)), deadline)
            if not part: raise Denied('partial headers')
            if charge: self.budget.charge(len(part))
            b += part
            if len(b)>cap: raise Denied('header limit')
        header, rest = b.split(b'\r\n\r\n',1)
        try: lines = header.decode('ascii').split('\r\n')
        except UnicodeError: raise Denied('header encoding') from None
        if len(lines)>33: raise Denied('header count')
        fields = {}
        for line in lines[1:]:
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+: [\x20-\x7e]*", line): raise Denied('header syntax')
            key, value = line.split(': ',1); key = key.lower()
            if key in fields: raise Denied('duplicate header')
            fields[key] = value
        return lines[0], fields, rest
    def _loop(self):
        while not self.closed.is_set():
            try: client,_ = self.listener.accept()
            except socket.timeout: continue
            except OSError: break
            with client:
                deadline = time.monotonic()+self.timeout
                try:
                    uid = struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
                    if uid != self.peer_uid: raise Denied('peer identity')
                    self.budget.reserve()
                    result = self._exchange(client, deadline)
                    self._check(deadline)
                    self._send(client, result, deadline)
                except (Denied, OSError, ValueError):
                    # Classified error only; never echo destination, headers, or peer bytes.
                    try: client.settimeout(.05); client.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 6\r\nConnection: close\r\n\r\ndenied')
                    except OSError: pass
    def _exchange(self, client, deadline):
        first, fields, rest = self._headers(client, deadline, charge=True)
        parts = first.split(' ')
        if len(parts)!=3 or parts[0] not in ('GET','HEAD') or parts[2]!='HTTP/1.1': raise Denied('method or request line')
        method, target, _ = parts
        if rest: raise Denied('request body or pipeline')
        if set(fields)-{'host','accept','user-agent','accept-encoding','connection'}: raise Denied('unsupported headers')
        if fields.get('host')!=self.authority or fields.get('connection','close').lower()!='close': raise Denied('authority or connection')
        if target.startswith(self.origin+'/'): target=target[len(self.origin):]
        if not target.startswith('/') or target.startswith('//') or '#' in target or '\\' in target or any(ord(c)<33 or ord(c)>126 for c in target): raise Denied('target')
        if re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)',target,re.I): raise Denied('encoded control')
        # Reconstruct; no user-controlled dial target or credential/forwarding headers.
        request = (f'{method} {target} HTTP/1.1\r\nHost: {self.authority}\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii')
        self._check(deadline)
        family = socket.AF_INET6 if ':' in self.peer_ip else socket.AF_INET
        with socket.socket(family,socket.SOCK_STREAM) as upstream:
            upstream.settimeout(max(.001,deadline-time.monotonic()))
            upstream.connect((self.peer_ip,self.port))
            if upstream.getpeername()[0]!=self.peer_ip: raise Denied('peer mismatch')
            self._check(deadline); self._send(upstream,request,deadline)
            status, headers, body = self._headers(upstream,deadline,charge=True)
            if not re.fullmatch(r'HTTP/1\.[01] [2-5][0-9]{2}(?: [\x20-\x7e]*)?',status): raise Denied('status')
            code = int(status.split(' ')[1])
            if 300<=code<400 or 'transfer-encoding' in headers or 'upgrade' in headers: raise Denied('redirect or framing')
            length=headers.get('content-length','')
            if not re.fullmatch(r'0|[1-9][0-9]{0,8}',length): raise Denied('length')
            n=int(length)
            if n>self.max_response: raise Denied('response limit')
            if method=='HEAD': body=b'';n=0
            if len(body)>n: raise Denied('response framing')
            while len(body)<n:
                part=self._recv(upstream,min(4096,n-len(body)),deadline)
                if not part: raise Denied('partial body')
                self.budget.charge(len(part));body+=part
            self._check(deadline)
            reason='OK' if code==200 else 'Fixture Response'
            return (f'HTTP/1.1 {code} {reason}\r\nContent-Length: {len(body)}\r\nContent-Type: application/octet-stream\r\nConnection: close\r\n\r\n').encode()+body
