"""Independent local boundary probes. No authority, listeners or external commands."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/'unit-copy'))
import guard
from test_guard import fixture, Runner, NOW
spec = importlib.util.spec_from_file_location('review_guest', HERE/'integration-copy/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)

class BoundaryTests(unittest.TestCase):
    def test_real_vps_status_shape_matches_actual_guest_guard_and_timeout12(self):
        c = fixture()
        c.update(deadline=NOW+300, guard_status='/UNIT_ONLY_NOT_EXECUTED')
        status = guard.VPSGuardReadback(c, runner=Runner(), clock=lambda: NOW,
            controller_check=lambda c: None, controller_release=lambda fd: None).status()
        calls = []
        class LocalRunner:
            def run(self, argv, **kw):
                calls.append((argv, kw))
                return json.dumps(status).encode()
        self.assertEqual(guest.guard(c, LocalRunner(), NOW), status)
        self.assertEqual(calls, [([c['guard_status'], '--status'], {'timeout': 12, 'cap': 8192})])

    def test_actual_guest_timeout_limited_by_remaining_phase_deadline(self):
        c = fixture()
        c.update(deadline=NOW+2, guard_status='/UNIT_ONLY_NOT_EXECUTED')
        status = guard.VPSGuardReadback(c, runner=Runner(), clock=lambda: NOW,
            controller_check=lambda c: None, controller_release=lambda fd: None).status()
        class LocalRunner:
            def run(self, argv, **kw):
                self.kw = kw
                return json.dumps(status).encode()
        runner = LocalRunner()
        guest.guard(c, runner, NOW)
        self.assertEqual(runner.kw['timeout'], 2)

    def test_client10_is_not_an_end_to_end10_second_deadline(self):
        c = fixture()
        elapsed = [0.0]
        key = b'x'*32 # synthetic protocol test key, not authority or a real credential
        status = {'alive': True, 'provider_state': 'RUNNING', 'vm': guard.VM,
            'stop_at': c['external_stop'], 'controller_id': c['controller_id'],
            'guard_created': c['guard_created'], 'default_docker_quiescent': True,
            'preflight_checkpoint_sha256': c['preflight']['sha256']}
        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def settimeout(self, value): pass
            def sendall(self, value):
                request = json.loads(value[4:])
                # Request was generated at0, arrives after9 (<10 freshness).
                p = {'nonce': request['payload']['nonce'], 'time': NOW+18, 'status': status}
                encoded = guard.canonical({'payload': p, 'mac': guard.mac(key, p)})
                self.response = struct.pack('!I', len(encoded))+encoded
            def recv(self, n):
                elapsed[0] = 18.0 # response after a further9s readback; no sleep/IO
                out, self.response = self.response[:n], self.response[n:]
                return out
        def connect(*a, **kw):
            elapsed[0] = 9.0
            return FakeSocket()
        with patch.object(guard.socket, 'create_connection', side_effect=connect), patch.object(guard.time, 'monotonic', side_effect=lambda: elapsed[0]):
            self.assertEqual(guard.client_status(c, key, clock=lambda: NOW+elapsed[0]), status)
        self.assertEqual(elapsed[0], 18.0)
        # Demonstrates a local timing-contract issue, not a live response or bypass
        # of the actual canary's separate12s subprocess limit.

if __name__ == '__main__': unittest.main(verbosity=2)
