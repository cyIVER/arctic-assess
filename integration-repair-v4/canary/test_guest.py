import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import guest
import driver
import probes

class FakeCLI:
    def __init__(self,replies):self.replies=list(replies);self.events=[]
    def run(self,argv,**kw):
        self.events.append({'argv':argv})
        if not self.replies:raise AssertionError('unexpected command')
        reply=self.replies.pop(0)
        if isinstance(reply,Exception):raise reply
        return reply

class GateTests(unittest.TestCase):
    def test_missing_parent_authority_denied(self):
        with self.assertRaises(guest.Blocked):guest.validate({},100)
    def test_entry_denies_without_commands_or_files(self):
        f=FakeCLI([])
        with self.assertRaises(guest.Blocked):driver.run({},runner=f,clock=lambda:100)
        self.assertEqual(f.events,[])
    def test_cli_default_blocked2(self):
        p=subprocess.run([sys.executable,'driver.py'],capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertEqual(json.loads(p.stdout)['status'],'BLOCKED')
    def test_absolute_stop_readback_positive(self):
        c={'deadline':200,'external_stop':300,'guard_status':'/owned/guard','controller_id':'owned-1','guard_created':10}
        v={'alive':True,'provider_state':'RUNNING','vm':guest.VM,'stop_at':300,'controller_id':'owned-1','guard_created':10}
        f=FakeCLI([json.dumps(v).encode()]);self.assertEqual(guest.guard(c,f,100),v);self.assertEqual(len(f.events),1)
    def test_stop_guard_rejects_wrong_vm_no_mutation(self):
        c={'deadline':200,'external_stop':300,'guard_status':'/owned/guard','controller_id':'owned-1','guard_created':10}
        v={'alive':True,'provider_state':'RUNNING','vm':{},'stop_at':300,'controller_id':'owned-1','guard_created':10}
        with self.assertRaises(guest.Blocked):guest.guard(c,FakeCLI([json.dumps(v).encode()]),100)
    def test_expired_guard_no_command(self):
        f=FakeCLI([])
        with self.assertRaises(guest.Blocked):guest.guard({'deadline':99},f,100)
        self.assertEqual(f.events,[])
    def test_pinned_bytes_and_symlink_denied(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'p';p.write_bytes(b'public');p.chmod(0o600);h=hashlib.sha256(b'public').hexdigest()
            self.assertEqual(guest.pinned(str(p),h),b'public')
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises(OSError):guest.pinned(str(link),h)
            p.write_bytes(b'drift')
            with self.assertRaises(guest.Blocked):guest.pinned(str(p),h)
    def test_inventory_exact_ids_fakecli(self):
        f=FakeCLI([b'b\na\n',b'i\n',b'v\n']);c={'docker_cli':'/owned/docker','daemon':guest.DAEMON}
        self.assertEqual(guest.inventory(c,f),{'containers':['a','b'],'images':['i'],'volumes':['v']})
        self.assertTrue(all(e['argv'][1:3]==['--host',guest.DAEMON] for e in f.events))

class ArtifactTests(unittest.TestCase):
    def test_archive_reads_all_members_no_socket(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work=root/'work';work.mkdir();(work/'a').write_bytes(b'owned public');(work/'sub').mkdir();(work/'sub'/'b').write_bytes(b'other')
            result=guest.checkpoint(work,root/'out.tar')
            self.assertEqual(set(result['members']),{'a','sub/b'});self.assertEqual(result['bytes'],17)
            with tarfile.open(root/'out.tar') as t:self.assertEqual(t.extractfile('a').read(),b'owned public')
    def test_archive_special_and_symlink_deny(self):
        for kind in ('fifo','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);work=root/'work';work.mkdir()
                if kind=='fifo':os.mkfifo(work/'bad')
                else:(work/'bad').symlink_to('/etc/hostname')
                with self.assertRaises(guest.Blocked):guest.checkpoint(work,root/'out.tar')
    def test_derived_image_only_helper_no_pull(self):
        text=guest.dockerfile();self.assertTrue(text.startswith('FROM '+guest.BASE+'\n'))
        self.assertEqual(text.count('COPY'),1);self.assertIn('USER 1001:1002',text);self.assertNotIn('RUN',text)
    def test_runner_actual_literal_output(self):
        r=guest.Runner();out=r.run([sys.executable,'-c','print("PUBLIC_ONLY")'])
        self.assertEqual(out,b'PUBLIC_ONLY\n');self.assertEqual(len(r.events),1)
    def test_runner_deadline_and_bytes_are_bounded(self):
        r=guest.Runner()
        for code,kwargs in [('import time;time.sleep(2)',{'timeout':.05}),('print("x"*5000)',{'cap':128})]:
            with self.subTest(code=code),self.assertRaises(guest.Blocked):r.run([sys.executable,'-c',code],**kwargs)
    def test_probe_inputs_are_sdk_shapes(self):
        req=probes.requests('http://127.0.0.1:12345',12345)
        self.assertEqual(len(req),9)
        self.assertEqual(req[-1][2],{'file_path':'/work/canary-fifo'})
        for name,tool,inputs,expected in req:
            self.assertNotIn('1.1.1.1',json.dumps(inputs));self.assertNotIn('OPENAI_API_KEY=',json.dumps(inputs))
            if tool=='Bash':
                import shlex
                if inputs['command'].startswith('python3 -c '):compile(shlex.split(inputs['command'])[2],name,'exec')
    def test_fact_parser_real_structure_rejects_marker(self):
        def envelope(text,error=False):return {'version':1,'result':{'IsError':error,'Content':[{'type':'text','text':text}]}}
        self.assertEqual(probes.facts(envelope('{"uid":1001}\n'),'json'),{'uid':1001})
        with self.assertRaises(ValueError):probes.facts(envelope('CANARY_OK'),'json')
        with self.assertRaises(ValueError):probes.facts(envelope('{"uid":1001}',True),'json')
        self.assertTrue(probes.facts(envelope('error',True),'error')['tool_error'])

class InspectTests(unittest.TestCase):
    def valid(self):
        return {'Config':{'User':'1001:1002','Entrypoint':['/usr/local/bin/artex-worker-tools'],'Volumes':{'/app/data':{}}},'HostConfig':{'ReadonlyRootfs':True,'NetworkMode':'none','PidMode':'private','IpcMode':'private','CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'PidsLimit':64,'Memory':268435456,'MemorySwap':268435456,'Tmpfs':{}},'Mounts':[]}
    def test_independent_inspect_positive(self):self.assertEqual(driver.inspect_conditions(self.valid())['memory'],268435456)
    def test_independent_inspect_denials(self):
        for key,value in [('ReadonlyRootfs',False),('NetworkMode','host'),('PidMode','host'),('IpcMode','host'),('CapDrop',[]),('PidsLimit',0),('Memory',0),('SecurityOpt',[])]:
            with self.subTest(key=key):
                v=self.valid();v['HostConfig'][key]=value
                with self.assertRaises(guest.Blocked):driver.inspect_conditions(v)
    def test_no_full_acceptance_status(self):
        # This checks source capability, never real VM success.
        self.assertEqual(driver.REQUIRED_CASES,{'environment-proxy','inflight-cancellation','phase-restart','aggregate-output-exhaustion'})

if __name__=='__main__':unittest.main()
