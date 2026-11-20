"""UNIT_ONLY protocol/guest/immutable-file regression evidence; no cloud/network service."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import guard
from test_guard import fixture,NOW,Runner

class RPC(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.key=b'UNIT_ONLY_TRANSPORT_KEY_32_BYTES'
        self.assertEqual(len(self.key),32)
        class Readback:
            def status(inner): self.calls.append('actual_readback');return {'unit_only':True}
        self.rpc=guard.StatusRPC(self.key,Readback(),clock=lambda:NOW)
    def request(self,**updates):
        p={'route':guard.ROUTE,'nonce':'a'*64,'time':NOW};p.update(updates)
        return {'payload':p,'mac':guard.mac(self.key,p)}
    def test_authenticated_request_calls_readback(self):
        r=self.rpc.respond(self.request());self.assertEqual(self.calls,['actual_readback'])
        self.assertEqual(r['mac'],guard.mac(self.key,r['payload']))
    def test_missing_wrong_key_and_caller_scope_fields(self):
        variants=[{}, {'payload':{},'mac':''},self.request(pid=1),self.request(vm=guard.VM),
                  self.request(external_stop=NOW+4000),self.request(provider_state='RUNNING')]
        wrong=self.request();wrong['mac']='0'*64;variants.append(wrong)
        for r in variants:
            with self.subTest(request=r):
                with self.assertRaises(guard.Blocked): self.rpc.respond(r)
        self.assertEqual(self.calls,[])
    def test_replay_stale_and_overflow(self):
        self.rpc.respond(self.request())
        with self.assertRaises(guard.Blocked):self.rpc.respond(self.request())
        for value in (NOW-11,NOW+11,float('inf'),float('nan'),True):
            # nonfinite canonical encoding also must fail closed, before readback.
            with self.subTest(value=value):
                with self.assertRaises((guard.Blocked,ValueError)): self.rpc.respond(self.request(time=value,nonce='b'*64))
        self.assertEqual(len(self.calls),1)
    def test_private_socketpair_frame_effect(self):
        a,b=socket.socketpair()
        try:
            a.settimeout(1);b.settimeout(1)
            guard.write_frame(a,self.request());result=self.rpc.respond(guard.read_frame(b))
            guard.write_frame(b,result);self.assertEqual(guard.read_frame(a),result)
        finally:a.close();b.close()
        self.assertEqual(self.calls,['actual_readback'])

class Guest(unittest.TestCase):
    def setUp(self):
        self.scope=fixture();self.calls=[];self.active=False;self.override=False;self.bad_package=False;self.socket_active=False
        self.proof={'vm':guard.VM,'status':'READY','created':NOW-10,
                    'external_stop':NOW+3570,'default_inventory':{'containers':[],'images':[],'volumes':[]}}
    def read(self,path,sha=None,**kw):
        self.calls.append(('read',path))
        return guard.canonical(self.proof) if path==self.scope['preflight']['path'] else b'UNIT_ONLY_UNIT_FILE'
    def runner(self,argv,timeout):
        self.calls.append(('command',argv))
        if argv[0]=='/usr/bin/dpkg-query' and '-W' in argv:
            out='\n'.join(k+'='+v for k,v in guard.VERSIONS.items())
        elif argv[0]=='/usr/bin/dpkg':out='changed' if self.bad_package else ''
        elif argv[0]=='/usr/bin/dpkg-query':out='docker.io: '+argv[-1]
        elif argv[0]=='/usr/bin/ss':out='u_str LISTEN 0 4096 /run/docker.sock 123 * 0' if self.socket_active else ''
        elif '--value' in argv:out='active' if self.active else 'inactive'
        else:
            unit=argv[2];out='LoadState=loaded\nActiveState='+('active' if self.active else 'inactive')+'\nMainPID=0\nFragmentPath=/usr/lib/systemd/system/'+unit+'\nDropInPaths='+('bad.conf' if self.override else '')
        return subprocess.CompletedProcess(argv,0,out,'')
    def status(self):return guard.guest_inventory(self.scope,runner=self.runner,clock=lambda:NOW,read=self.read)
    def test_positive_reads_actual_package_and_service_commands(self):
        self.assertTrue(self.status()['default_docker_quiescent'])
        commands=[x[1] for x in self.calls if x[0]=='command']
        self.assertEqual(len(commands),9)
        self.assertTrue(any(x[:2]==['/usr/bin/dpkg','--verify'] for x in commands))
        self.assertFalse(any('stop' in x or 'start' in x or 'restart' in x for x in commands))
    def test_default_socket_listener_denied_even_if_units_inactive(self):
        self.socket_active=True
        with self.assertRaises(guard.Blocked):self.status()
    def test_active_override_package_stale_inventory_deny(self):
        for attr in ('active','override','bad_package'):
            with self.subTest(attr=attr):
                setattr(self,attr,True)
                with self.assertRaises(guard.Blocked):self.status()
                setattr(self,attr,False)
        self.proof['created']=NOW-121
        with self.assertRaises(guard.Blocked):self.status()
        self.proof['created']=NOW;self.proof['default_inventory']['containers']=['one']
        with self.assertRaises(guard.Blocked):self.status()

class PathsAndProcess(unittest.TestCase):
    def test_unprotected_tree_and_noncanonical_origin_denied(self):
        with tempfile.TemporaryDirectory(prefix='unit_guard_') as root:
            p=Path(root)/'proof';p.write_text('UNIT_ONLY');p.chmod(0o600)
            # This task is unprivileged and cannot mint root-owned authority.
            with self.assertRaises((guard.Blocked,PermissionError)):guard.protected(str(p))
            with self.assertRaises(guard.Blocked):guard.protected(str(p.parent/'..'/p.parent.name/p.name))
        with self.assertRaises((guard.Blocked,FileNotFoundError,PermissionError)):guard.load_scope()
    def test_controller_missing_and_current_rpc_process_denied(self):
        c=fixture()['controller']
        for pid in (0,1,os.getpid(),2147483647):
            c['pid']=pid
            with self.subTest(pid=pid):
                with self.assertRaises((guard.Blocked,ProcessLookupError,OSError)):guard.proc_identity(c)
    def test_default_entrypoint_missing_input_exit2_no_stdout(self):
        r=subprocess.run(['/usr/bin/python3','-I','-B',str(Path(guard.__file__).absolute()),'--status'],capture_output=True,text=True,timeout=2)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(2,'','BLOCKED\n'))
    def test_controller_real_local_fixture_lifetime_and_identity_mismatch(self):
        script=str(Path(guard.__file__).absolute())
        p=subprocess.Popen(['/usr/bin/python3','-c','import sys;sys.stdin.read()',script],stdin=subprocess.PIPE)
        try:
            root=Path('/proc')/str(p.pid); text=(root/'stat').read_text(); f=text[text.rfind(')')+2:].split()
            c={'pid':p.pid,'uid':os.getuid(),'start_ticks':int(f[19]),'exe':os.readlink(root/'exe'),
               'cmd_sha256':guard.digest((root/'cmdline').read_bytes()),'script':{'path':script}}
            with self.assertRaises(guard.Blocked):guard.proc_identity(c) # direct RPC child is not external
            with patch.object(guard.os,'getpid',return_value=2147483646):
                token=guard.proc_identity(c);guard.release_identity(token)
                for field,value in [('uid',99999),('start_ticks',0),('exe','/wrong/exe'),('cmd_sha256','0'*64)]:
                    with self.subTest(field=field):
                        bad=copy.deepcopy(c);bad[field]=value
                        with self.assertRaises(guard.Blocked):guard.proc_identity(bad)
            p.stdin.close();self.assertEqual(p.wait(timeout=2),0)
            with self.assertRaises((guard.Blocked,OSError)):guard.proc_identity(c)
        finally:
            if not p.stdin.closed:p.stdin.close()
            p.wait(timeout=2)
    def test_protected_file_positive_synthetic_root_then_mode_symlink_hash_denials(self):
        # UNIT_ONLY UID projection: this user cannot install real root files.
        real_fstat=os.fstat
        def root_metadata(fd):
            original=real_fstat(fd);fields=list(original);fields[4]=0
            if __import__('stat').S_ISDIR(fields[0]): fields[0]&=~0o022
            return os.stat_result(fields)
        with tempfile.TemporaryDirectory(prefix='unit_guard_') as root:
            p=Path(root)/'proof';p.write_bytes(b'UNIT_ONLY_PROOF');p.chmod(0o600)
            with patch.object(guard.os,'fstat',side_effect=root_metadata):
                self.assertEqual(guard.protected(str(p),guard.digest(b'UNIT_ONLY_PROOF'),private=True),b'UNIT_ONLY_PROOF')
                with self.assertRaises(guard.Blocked):guard.protected(str(p),'0'*64)
                p.chmod(0o666)
                with self.assertRaises(guard.Blocked):guard.protected(str(p))
                p.chmod(0o600); link=Path(root)/'link';link.symlink_to(p)
                with self.assertRaises(OSError):guard.protected(str(link))
    def test_root_context_source_review_and_lease_bindings(self):
        c=fixture();c['parent_scope_lease']={'handle':'UNIT_ONLY_LEASE','created':NOW-30,'deadline':NOW+3570}
        code=b'UNIT_ONLY_SOURCE_NOT_EXECUTED';sha=guard.digest(code)
        review_ref={'path':'/opt/artex-live-guard/review.json','sha256':'e'*64}
        allow={'guard_sha256':sha,'guardian_review':review_ref}
        ctx={k:copy.deepcopy(c[k]) for k in ('vm','lane','guard_created','external_stop','controller_id','preflight','parent_scope_lease')}
        ctx.update(guardian_implementation={'path':guard.SOURCE,'sha256':sha},guardian_review=review_ref)
        review={'status':'approved','object_sha256':sha}
        reads=[]
        def trusted_read(path,sha=None,**kwargs):
            reads.append(path)
            values={guard.ALLOWLIST:guard.canonical(allow),guard.SOURCE:code,
                    guard.ROOT+'/parent.json':guard.canonical(c),guard.CONTEXT:guard.canonical(ctx),
                    review_ref['path']:guard.canonical(review)}
            return values[path]
        with patch.object(guard,'protected',side_effect=trusted_read),patch.object(guard,'__file__',guard.SOURCE),patch.object(guard.os,'geteuid',return_value=0),patch.object(guard,'utc',return_value=NOW):
            self.assertEqual(guard.load_scope('guest'),c)
            self.assertNotIn(guard.GCLOUD,reads) # guest never needs SDK or credentials
            for key,value in [('controller_id','wrong'),('parent_scope_lease',{'handle':'forged'}),
                              ('guardian_implementation',{'path':'/home/worker/fake','sha256':sha})]:
                original=copy.deepcopy(ctx[key]);ctx[key]=value
                with self.subTest(key=key):
                    with self.assertRaises(guard.Blocked):guard.load_scope('guest')
                ctx[key]=original
            review['object_sha256']='0'*64
            with self.assertRaises(guard.Blocked):guard.load_scope('guest')
            review['object_sha256']=sha
            with patch.object(guard,'__file__','/home/worker/copied_guard.py'):
                with self.assertRaises(guard.Blocked):guard.load_scope('guest')
    def test_exec_boundary_only_fixed_gcloud_read_and_mux_inventory(self):
        runner=Runner();guard.VPSGuardReadback(fixture(),runner=runner,clock=lambda:NOW,
            controller_check=lambda c:None,controller_release=lambda fd:None).status()
        for argv,_ in runner.calls[:2]:
            self.assertNotIn('stop',argv);self.assertNotIn('start',argv);self.assertNotIn('set-scheduling',argv)
            self.assertEqual(argv[0],guard.GCLOUD);self.assertIn('describe',argv)
        ssh=runner.calls[2][0]
        self.assertIn('ProxyCommand=/usr/bin/false',ssh)
        self.assertEqual(ssh[-1],'sudo -n /usr/bin/python3 -I -B /opt/artex-live-guard/guard.py --guest-inventory')

if __name__=='__main__':unittest.main()
