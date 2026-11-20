"""Owned, synthetic HTTP assessment fixture; never production data."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def create_server(bind=('127.0.0.1', 0), state_dir=None):
    ground_truth = {
        'path': '/internal-' + secrets.token_hex(6) + '/diagnostics.json',
        'synthetic_marker': 'LAB_PUBLIC_TEST_MARKER_' + secrets.token_hex(12),
    }
    records = []
    lock = threading.Lock()
    state = Path(state_dir) if state_dir is not None else None

    def private_open(name, flags):
        fd = os.open(state / name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            os.close(fd)
            raise ValueError('Invalid fixture state file')
        return fd

    if state is not None:
        state.mkdir(mode=0o700, exist_ok=True)
        info = state.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('Fixture state directory must be private and owned')
        try:
            fd = private_open('ground_truth.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            with os.fdopen(private_open('ground_truth.json', os.O_RDONLY), 'rb') as f:
                raw = f.read(1025)
            if len(raw) > 1024:
                raise ValueError('Oversized fixture state')
            ground_truth = json.loads(raw)
            if set(ground_truth) != {'path', 'synthetic_marker'} or not re.fullmatch(r'/internal-[a-f0-9]{12}/diagnostics\.json', ground_truth['path']) or not re.fullmatch(r'LAB_PUBLIC_TEST_MARKER_[a-f0-9]{24}', ground_truth['synthetic_marker']):
                raise ValueError('Invalid fixture ground truth')
            with os.fdopen(private_open('requests.jsonl', os.O_RDONLY), 'rb') as f:
                raw = f.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError('Oversized fixture ledger')
            records = [json.loads(line) for line in raw.splitlines()]
        else:
            with os.fdopen(fd, 'wb') as f:
                f.write(json.dumps(ground_truth, sort_keys=True).encode())
                f.flush()
                os.fsync(f.fileno())
            os.close(private_open('requests.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if self.command not in ('GET', 'HEAD'):
                status, content_type, body = 405, 'text/plain', b'Method not allowed\n'
            elif path == '/':
                status, content_type = 200, 'text/html; charset=utf-8'
                body = ('<!doctype html><title>Owned assessment lab</title>'
                        '<h1>Owned assessment lab</h1><p>Read-only synthetic application.</p>'
                        '<a href="' + ground_truth['path'] + '">Administrator diagnostics</a>').encode()
            elif path == ground_truth['path']:
                status, content_type = 200, 'application/json'
                body = json.dumps({
                    'synthetic': True,
                    'intended_access': 'authenticated lab administrators',
                    'synthetic_marker': ground_truth['synthetic_marker'],
                    'notice': 'Intentionally exposed lab-only diagnostics; no real secrets or personal data.',
                }, sort_keys=True).encode()
            else:
                status, content_type, body = 404, 'text/plain', b'Not found\n'
            transmitted = b'' if self.command == 'HEAD' else body
            with lock:
                record = {'method': self.command, 'path': self.path,
                          'status': status, 'peer': self.client_address[0],
                          'epoch_ns': time.time_ns(), 'response_bytes': len(transmitted),
                          'response_sha256': hashlib.sha256(transmitted).hexdigest()}
                if state is not None:
                    with os.fdopen(private_open('requests.jsonl', os.O_WRONLY | os.O_APPEND), 'ab') as f:
                        data = json.dumps(record, sort_keys=True).encode() + b'\n'
                        if os.fstat(f.fileno()).st_size + len(data) > 4 * 1024 * 1024:
                            raise ValueError('Fixture ledger capacity exhausted')
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                records.append(record)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            if status == 405:
                self.send_header('Allow', 'GET, HEAD')
            self.end_headers()
            if transmitted:
                self.wfile.write(transmitted)

        do_HEAD = do_GET
        do_POST = do_GET
        do_PUT = do_GET
        do_PATCH = do_GET
        do_DELETE = do_GET
        do_CONNECT = do_GET
        do_TRACE = do_GET
        do_OPTIONS = do_GET

    server = ThreadingHTTPServer(bind, Handler)
    server.ground_truth, server.records = ground_truth, records
    return server
