"""Offline socketpair regression against the real HTTP handler and dispatch."""
import io
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from bridge import Bridge, Handler, MODEL, PATH

TASK = 'task-fixture-key-distinct-123456789'
BODY = json.dumps({'model': MODEL, 'messages': [], 'stream': False}).encode()


class OwnedServer:
    def __init__(self, bridge):
        self.bridge = bridge


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.bridge = Bridge(TASK, 'gateway-no-vendor-credential-present', time.time() + 120,
                             transport=lambda body, key, deadline: (self.calls.append(body) or (200, b'{"choices":[]}')))
        self.pairs = []
        self.threads = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for a, b in self.pairs:
            try: b.shutdown(socket.SHUT_WR)
            except OSError: pass
        for t in self.threads:
            t.join(2)
        for a, b in self.pairs:
            a.close(); b.close()

    def client(self, handler=Handler, server=None):
        a, b = socket.socketpair()
        self.pairs.append((a, b))
        t = threading.Thread(target=handler, args=(a, ('fixture', 0), server or OwnedServer(self.bridge)), daemon=True)
        t.start(); self.threads.append(t)
        return b, t

    def test_partial_unauthenticated_header_cannot_occupy_handler_for_seconds(self):
        import guest_gateway
        peer, thread = self.client(getattr(guest_gateway, 'GatewayHandler', Handler))
        peer.sendall(b'POST ' + PATH.encode() + b' HTTP/1.1\r\nAuthorization: Bearer ')
        thread.join(1.6)
        self.assertFalse(thread.is_alive(), 'unauthenticated header held a worker beyond short admission deadline')
        self.assertEqual(self.calls, [])

    def test_two_slow_clients_do_not_starve_authorized_request(self):
        from guest_gateway import GatewayServer
        server = GatewayServer.__new__(GatewayServer)
        server.bridge = self.bridge
        server.RequestHandlerClass = __import__('guest_gateway').GatewayHandler
        server.slots = threading.BoundedSemaphore(4)
        def dispatch():
            a, b = socket.socketpair(); self.pairs.append((a, b))
            server.process_request(a, ('fixture', 0))
            return b
        slow = [dispatch() for _ in range(2)]
        for s in slow: s.sendall(b'POST ' + PATH.encode() + b' HTTP/1.1\r\nAuthorization: Bearer ')
        good = dispatch()
        request = (b'POST ' + PATH.encode() + b' HTTP/1.1\r\nAuthorization: Bearer ' + TASK.encode() +
                   b'\r\nContent-Length: ' + str(len(BODY)).encode() + b'\r\n\r\n' + BODY)
        start = time.monotonic(); good.sendall(request); good.settimeout(1.3)
        response = good.recv(4096)
        self.assertIn(b'200 OK', response)
        self.assertLess(time.monotonic() - start, 1.3)
        self.assertEqual(len(self.calls), 1)
        for s in slow: s.settimeout(2); self.assertEqual(s.recv(4096), b'')

    def test_bad_framing_and_unauthorized_body_never_reach_vendor(self):
        from guest_gateway import GatewayHandler
        for headers, body in (
            (b'Authorization: Bearer wrong\r\nContent-Length: 9', b'123456789'),
            (b'Authorization: Bearer ' + TASK.encode() + b'\r\nContent-Length: nope', b''),
            (b'Authorization: Bearer ' + TASK.encode() + b'\r\nContent-Length: 1\r\nContent-Length: 1', b'X'),
            (b'Authorization: Bearer ' + TASK.encode() + b'\r\nTransfer-Encoding: chunked', b'0\r\n\r\n'),
        ):
            peer, thread = self.client(GatewayHandler)
            peer.sendall(b'POST ' + PATH.encode() + b' HTTP/1.1\r\n' + headers + b'\r\n\r\n' + body)
            peer.settimeout(2)
            self.assertNotIn(b'200 OK', peer.recv(4096))
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(self.calls, [])

    def test_header_cap_denies_and_large_authenticated_body_is_not_header(self):
        from guest_gateway import GatewayHandler
        peer, thread = self.client(GatewayHandler)
        peer.sendall(b'POST ' + PATH.encode() + b' HTTP/1.1\r\nX-Pad: ' + b'x'*8200 + b'\r\n')
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.calls, [])
        body = json.dumps({'model': MODEL, 'messages': [{'role': 'user', 'content': 'z'*10000}], 'stream': False}).encode()
        peer, thread = self.client(GatewayHandler)
        peer.sendall(b'POST ' + PATH.encode() + b' HTTP/1.1\r\nAuthorization: Bearer ' + TASK.encode() +
                     b'\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
        peer.settimeout(2)
        self.assertIn(b'200 OK', peer.recv(4096))
        thread.join(2)
        self.assertEqual(len(self.calls), 1)

    def test_excess_parallel_clients_fail_closed_without_vendor_call(self):
        from guest_gateway import GatewayServer
        server = GatewayServer.__new__(GatewayServer)
        server.bridge = self.bridge
        server.RequestHandlerClass = __import__('guest_gateway').GatewayHandler
        server.slots = threading.BoundedSemaphore(4)
        clients = []
        for _ in range(5):
            a, b = socket.socketpair(); self.pairs.append((a, b)); server.process_request(a, ('fixture', 0)); clients.append(b)
        clients[-1].settimeout(.5)
        self.assertEqual(clients[-1].recv(4096), b'')
        self.assertEqual(self.calls, [])

if __name__ == '__main__': unittest.main()
