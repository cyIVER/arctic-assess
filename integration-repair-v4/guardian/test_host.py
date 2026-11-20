"""Local only: actual user-owned files/programs; symbolic other-UID/root cases."""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import guard

class Host(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='guard_v2_')
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.p=self.root/'proof';self.p.write_bytes(b'PUBLIC_UNIT_PROOF');self.p.chmod(0o600)
    def tearDown(self):self.tmp.cleanup()
    def read(self,**kw):return guard.protected(str(self.p),private=True,host=True,**kw)
    def test_vps_current_uid_reaches_artifact_gate_not_root_gate(self):
        try:guard.load_scope('vps')
        except Exception as e:self.assertNotEqual(str(e),'root-only')
    def test_current_user_private_file_admitted(self):
        self.assertEqual(os.getuid(),1000)
        self.assertEqual(self.read(),b'PUBLIC_UNIT_PROOF')
    def test_other_uid_file_denied_after_positive(self):
        self.read();real=os.fstat
        def other(fd):
            s=real(fd)
            if stat.S_ISREG(s.st_mode):
                v=list(s);v[4]=1001;return os.stat_result(v)
            return s
        with patch.object(guard.os,'fstat',side_effect=other):
            with self.assertRaises(guard.Blocked):self.read()
    def test_group_write_before_shield_and_no_shield_denied(self):
        self.read();real=os.fstat
        def bad(fd):
            s=real(fd);v=list(s)
            if stat.S_ISDIR(s.st_mode) and s.st_ino==self.root.stat().st_ino:v[0]=(v[0]&~0o777)|0o775
            return os.stat_result(v)
        with patch.object(guard.os,'fstat',side_effect=bad):
            with self.assertRaises(guard.Blocked):self.read()
        self.root.chmod(0o755)
        with self.assertRaises(guard.Blocked):self.read()
    def test_symlink_hash_and_mode_denials(self):
        self.read()
        with self.assertRaises(guard.Blocked):self.read(sha='0'*64)
        self.p.chmod(0o660)
        with self.assertRaises(guard.Blocked):self.read()
        self.p.unlink();self.p.symlink_to('/etc/hosts')
        with self.assertRaises(OSError):self.read()
    def test_guest_still_rejects_user_file(self):
        with self.assertRaises(guard.Blocked):guard.protected(str(self.p),private=True)
    def test_real_sdk_fixture_manifest_and_tamper_denials(self):
        sdk=self.root/'sdk';(sdk/'bin').mkdir(parents=True,mode=0o700);sdk.chmod(0o700)
        p=sdk/'bin'/'gcloud';p.write_text('#!/bin/sh\nprintf "fixture-only\\n"\n');p.chmod(0o700)
        manifest={'bin/gcloud':guard.digest(p.read_bytes())}
        guard.verify_sdk(str(sdk),manifest)
        r=guard.run_command([str(p)],timeout=2);self.assertEqual(r.stdout,'fixture-only\n')
        p.write_text('tamper')
        with self.assertRaises(guard.Blocked):guard.verify_sdk(str(sdk),manifest)
        p.unlink();p.symlink_to('/etc/hosts')
        with self.assertRaises((guard.Blocked,OSError)):guard.verify_sdk(str(sdk),manifest)
    def test_full_host_scope_real_private_artifacts(self):
        from test_guard import fixture,NOW
        source=self.root/'guard.py';source.write_bytes(Path(guard.__file__).read_bytes());source.chmod(0o600)
        sha=guard.digest(source.read_bytes())
        def put(name,obj):
            p=self.root/name;p.write_bytes(guard.canonical(obj));p.chmod(0o600)
            return {'path':str(p),'sha256':guard.digest(p.read_bytes())}
        review=put('review.json',{'status':'approved','object_sha256':sha})
        script=put('controller.py',{'PUBLIC_ONLY':'NOT_AN_ACTUAL_CONTROLLER'})
        c=fixture();c['controller']['uid']=1000;c['controller']['script']=script
        c['controller']['exe']=str(Path('/usr/bin/python3').resolve())
        c['controller']['checkpoint']=put('approval-checkpoint.json',{'deadline':__import__('datetime').datetime.fromtimestamp(c['external_stop'],__import__('datetime').timezone.utc).isoformat()})
        c['parent_scope_lease']={'unit_only':'not authority'}
        ctx={k:copy.deepcopy(c[k]) for k in ('vm','lane','guard_created','external_stop','controller_id','preflight','parent_scope_lease')}
        ctx.update(guardian_implementation={'path':guard.SOURCE,'sha256':sha},guardian_review=review)
        sdk=self.root/'sdk';(sdk/'bin').mkdir(parents=True,mode=0o700);sdk.chmod(0o700)
        exe=sdk/'bin'/'gcloud';exe.write_bytes(b'PUBLIC_ONLY_NOT_EXECUTED');exe.chmod(0o700)
        manifest=put('sdk-manifest.json',{'bin/gcloud':guard.digest(exe.read_bytes())})
        pythonsha=guard.digest(Path(c['controller']['exe']).read_bytes())
        put('allowlist.json',dict(guard_sha256=sha,guardian_review=review,controller_sha256=script['sha256'],controller_exe_sha256=pythonsha,sdk_python_sha256=pythonsha,gcloud_manifest=manifest))
        put('parent.json',c);put('run-context.json',ctx)
        with patch.multiple(guard,HOST_ROOT=str(self.root),HOST_SOURCE=str(source),HOST_CONTEXT=str(self.root/'run-context.json'),SDK=str(sdk),__file__=str(source)),patch.object(guard,'utc',return_value=NOW):
            self.assertEqual(guard.load_scope('vps'),c)
            c['controller']['uid']=1001;put('parent.json',c)
            with self.assertRaisesRegex(guard.Blocked,'fixed controller UID'):guard.load_scope('vps')
            c['controller']['uid']=1000;put('parent.json',c)
            ctx['controller_id']='WRONG';put('run-context.json',ctx)
            with self.assertRaisesRegex(guard.Blocked,'parent context binding'):guard.load_scope('vps')
    def test_pre_shield_write_and_absent_shield_explicit_projection(self):
        self.read();real=os.fstat
        home=Path('/home/iveri').stat().st_ino
        def unsafe(fd):
            s=real(fd);v=list(s)
            if stat.S_ISDIR(s.st_mode) and s.st_ino==home:v[0]=(v[0]&~0o777)|0o775
            return os.stat_result(v)
        with patch.object(guard.os,'fstat',side_effect=unsafe):
            with self.assertRaisesRegex(guard.Blocked,'protected ancestor'):self.read()
        def no_shield(fd):
            s=real(fd);v=list(s)
            if stat.S_ISDIR(s.st_mode):v[0]=(v[0]&~0o777)|0o755
            return os.stat_result(v)
        with patch.object(guard.os,'fstat',side_effect=no_shield):
            with self.assertRaisesRegex(guard.Blocked,'missing host privacy shield'):guard.protected(str(self.p),host=True)
    def test_rpc_owner_override_denied_after_authenticated_control(self):
        class Readback:
            def status(self):return {'unit_only':True}
        key=b'X'*32;rpc=guard.StatusRPC(key,Readback(),clock=lambda:123)
        p={'route':guard.ROUTE,'nonce':'a'*64,'time':123}
        rpc.respond({'payload':p,'mac':guard.mac(key,p)})
        for field in ('uid','owner','role','controller','pid','external_stop'):
            q=dict(p,nonce='b'*64);q[field]=1001
            with self.assertRaisesRegex(guard.Blocked,'fixed request fields'):rpc.respond({'payload':q,'mac':guard.mac(key,q)})
    def test_clear_command_environment_real_program(self):
        with patch.dict(os.environ,{'PYTHONPATH':'UNTRUSTED','LD_PRELOAD':'UNTRUSTED','BASH_ENV':'UNTRUSTED','CLOUDSDK_CONFIG':'UNAPPROVED'}):
            r=guard.run_command(['/usr/bin/python3','-I','-c','import os,json;print(json.dumps(dict(os.environ)))'],2)
        e=json.loads(r.stdout)
        for k in ('PYTHONPATH','LD_PRELOAD','BASH_ENV','CLOUDSDK_CONFIG'):self.assertNotIn(k,e)
        self.assertEqual(e['CLOUDSDK_PYTHON_ARGS'],'-I -B')
    def test_serve_missing_proof_closed_actual_subprocess(self):
        r=subprocess.run(['/usr/bin/python3','-I','-B',guard.__file__,'--serve'],capture_output=True,text=True,timeout=2)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(2,'','BLOCKED\n'))

if __name__=='__main__':unittest.main()
