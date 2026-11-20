"""Authenticated host-control UDS; NEVER mount this socket in a worker.
HMAC authenticates exact request bytes, SO_PEERCRED binds the trusted app UID.
Trusted Broker scope registry is still the authority; JSON cannot mint a scope.
"""
import hmac
import os
import select
import socket
import struct
import threading
import time
from .broker import Refused, strict_json
import json

class ControlServer:
    def __init__(self,path,key,peer_uid,broker):
        if len(key)!=32:raise ValueError('32-byte control key required')
        self.path,self.key,self.peer_uid,self.broker=path,bytes(key),peer_uid,broker
        self.closed=threading.Event()
    def start(self):
        self.listener=socket.socket(socket.AF_UNIX)
        try:
            self.listener.bind(self.path);os.chmod(self.path,0o600);self.listener.listen(1);self.listener.settimeout(.05)
        except BaseException:self.listener.close();raise
        self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()
    def close(self):
        self.closed.set();self.thread.join(22);self.listener.close()
        if self.thread.is_alive():raise RuntimeError('control shutdown unresolved')
        os.unlink(self.path)
    def _read(self,s,n,deadline):
        out=b''
        while len(out)<n:
            if self.closed.is_set() or time.monotonic()>=deadline:raise Refused('control deadline')
            s.settimeout(min(.05,max(.001,deadline-time.monotonic())))
            try:b=s.recv(n-len(out))
            except socket.timeout:continue
            if not b:raise Refused('control closed')
            out+=b
        if time.monotonic()>=deadline:raise Refused('control deadline')
        return out
    def _loop(self):
        while not self.closed.is_set():
            try:s,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:break
            with s:
                settled=threading.Event();monitor=None
                try:
                    deadline=time.monotonic()+2
                    uid=struct.unpack('3i',s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
                    if uid!=self.peer_uid:raise Refused('peer identity')
                    n=struct.unpack('!I',self._read(s,4,deadline))[0]
                    if not 34<=n<=65536:raise Refused('frame length')
                    frame=self._read(s,n,deadline);mac,payload=frame[:32],frame[32:]
                    if not hmac.compare_digest(mac,hmac.digest(self.key,payload,'sha256')):raise Refused('auth')
                    request=strict_json(payload)
                    def watch():
                        while not settled.wait(.02):
                            readable,_,_=select.select([s],[],[],0)
                            if self.closed.is_set() or readable:
                                # EOF or any unsolicited further bytes revoke this admitted request.
                                if hasattr(self.broker,'cancel_request'):self.broker.cancel_request(request)
                                return
                    monitor=threading.Thread(target=watch,daemon=True);monitor.start()
                    result=self.broker.execute(request)
                except Exception:result={'version':1,'error':'isolated executor refused or failed'}
                finally:
                    settled.set()
                    if monitor:monitor.join()
                data=json.dumps(result,separators=(',',':')).encode()
                if len(data)>65536:data=b'{"version":1,"error":"control output limit"}'
                try:s.settimeout(.2);s.sendall(struct.pack('!I',len(data))+data)
                except OSError:pass
