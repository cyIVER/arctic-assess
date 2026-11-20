"""Offline tests only: no Docker daemon, cloud, image or model execution."""
import copy, json, subprocess, unittest
from unittest.mock import patch
import install as target

class SafetyTests(unittest.TestCase):
    def test_reviewed_plans(self):
        for role in ('web','db'):
            a=target.run_args(role); target.validate_args(a)
            self.assertEqual(a[0],'run');self.assertIn('--pull=never',a)
            self.assertIn('--cap-drop=ALL',a);self.assertIn('--read-only',a)
            self.assertIn('--restart=no',a);self.assertIn('--security-opt=no-new-privileges:true',a)
            self.assertIn('--pids-limit=160',a);self.assertIn('--cpus=0.75',a)
            self.assertIn('--user=mysql' if role=='db' else '--user=www-data',a)
            self.assertEqual(a[-1],target.PINS['images'][target.pinned_role(role)]['pinned'])
            for forbidden in ('--privileged','--network=host','--pid=host','--publish','-p','-P','--mount','-v','--volume'):
                self.assertNotIn(forbidden,a)
            for i,v in enumerate(a):
                if v=='--tmpfs':
                    self.assertIn('size=',a[i+1]); self.assertIn('nosuid',a[i+1]);self.assertIn('nodev',a[i+1]);self.assertIn('noexec',a[i+1])

    def test_mutation_rejected(self):
        for unsafe in ('--privileged','--network=host','--pid=host','-p','80:80','-v','/:/host','--restart=always','--pull=always','--cap-add=SYS_ADMIN','--mount=type=bind,src=/var/run/docker.sock,dst=/sock'):
            with self.subTest(unsafe=unsafe),self.assertRaises(ValueError): target.validate_args(target.run_args('web')[:-1]+[unsafe,target.run_args('web')[-1]])
        a=target.run_args('db');a[-1]='mariadb:10'
        with self.assertRaises(ValueError):target.validate_args(a)

    def test_explicit_config_id_mode(self):
        with patch.object(target,'USE_CONFIG_IDS',True):
            for role in ('web','db'):
                a=target.run_args(role);target.validate_args(a)
                self.assertEqual(a[-1],target.PINS['images'][target.pinned_role(role)]['config_digest'])
                self.assertIn('--pull=never',a)

    def test_budget_and_pins(self):
        p=target.PINS
        layers={v['digest']:v['size'] for im in p['images'].values() for v in im['layers']}
        self.assertEqual(sum(layers.values()),p['unique_compressed_layer_bytes'])
        self.assertLessEqual(sum(layers.values()),p['budget_bytes'])
        self.assertRegex(p['source_commit'],r'^[a-f0-9]{40}$')
        for im in p['images'].values():
            self.assertRegex(im['pinned'],r'@sha256:[a-f0-9]{64}$')
            self.assertEqual(im['compressed_layer_bytes'],sum(v['size'] for v in im['layers']))

    def test_private_daemon_fixed_no_shell(self):
        with patch.object(target.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ok','')) as run:
            target.docker('version')
            self.assertEqual(run.call_args.args[0],['docker','--host',target.HOST,'version'])
            self.assertNotIn('shell',run.call_args.kwargs)

    def test_deadline_blocks_before_execution(self):
        with patch.object(target,'DEADLINE',1),patch.object(target.subprocess,'run') as run:
            with self.assertRaises(RuntimeError): target.docker('run')
            run.assert_not_called()

    def test_csrf_required(self):
        self.assertEqual(target.token("<input name='user_token' type='hidden' value='abc123'>"),'abc123')
        with self.assertRaises(RuntimeError): target.token('<html>not a setup form</html>')

    def test_cookie_roundtrip_and_status(self):
        payload={'headers':['HTTP/1.1 200 OK','Set-Cookie: PHPSESSID=test-only; path=/'],'body':'setup'}
        with patch.object(target,'docker',return_value=subprocess.CompletedProcess([],0,json.dumps(payload),'')) as run:
            cookies={};target.request('setup.php',cookies)
            self.assertEqual(cookies,{'PHPSESSID':'test-only'})
            target.request('setup.php',cookies,'a=b')
            self.assertEqual(json.loads(run.call_args.kwargs['data'])['cookie'],'PHPSESSID=test-only')
            self.assertEqual(run.call_args.args[:4],('exec','-i',target.WEB,'php'))
        payload['headers']=['HTTP/1.1 500 Error']
        with patch.object(target,'docker',return_value=subprocess.CompletedProcess([],0,json.dumps(payload),'')), self.assertRaises(RuntimeError): target.request('setup.php',{})

    def test_stop_refuses_unowned(self):
        with patch.object(target,'exists',return_value=True),patch.object(target,'info',return_value={'Config':{'Labels':{}}}),patch.object(target,'docker') as run:
            with self.assertRaises(RuntimeError):target.stop_owned()
            run.assert_not_called()

    def test_stop_exact_names_no_removal(self):
        state={'Config':{'Labels':{'lab.owner':'dvwa-target-20261119'}},'State':{'Running':False}}
        with patch.object(target,'exists',return_value=True),patch.object(target,'info',return_value=state),patch.object(target,'docker') as run:
            target.stop_owned()
            self.assertEqual([c.args for c in run.call_args_list],[('stop','--time','8',target.WEB),('stop','--time','8',target.DB)])

    def test_runtime_verification_rejects_unsafe_mounts(self):
        x={'Config':{'Labels':{'lab.owner':'dvwa-target-20261119'}},'State':{'Running':True},'Image':target.PINS['images']['db']['config_digest'],
           'HostConfig':{'Privileged':False,'PortBindings':{},'Binds':None,'ReadonlyRootfs':True,'RestartPolicy':{'Name':'no'},'CapDrop':['ALL'],'CapAdd':None,'SecurityOpt':['no-new-privileges:true'],'PidsLimit':160,'NanoCpus':750000000,'Memory':768*1024*1024},
           'Mounts':[{'Type':'tmpfs'}],'NetworkSettings':{'Networks':{target.BACK:{}}}}
        with patch.object(target,'info',return_value=x): target.verify_container('db')
        for field,value in [('Privileged',True),('PortBindings',{'80/tcp':[{'HostPort':'80'}]}),('NetworkMode','host'),('PidMode','host'),('CapAdd',['SYS_ADMIN']),('ReadonlyRootfs',False)]:
            bad=copy.deepcopy(x);bad['HostConfig'][field]=value
            with self.subTest(field=field),patch.object(target,'info',return_value=bad),self.assertRaises(RuntimeError): target.verify_container('db')
        for typ in ('bind','volume'):
            bad=copy.deepcopy(x);bad['Mounts']=[{'Type':typ}]
            with patch.object(target,'info',return_value=bad),self.assertRaises(RuntimeError):target.verify_container('db')

if __name__=='__main__':unittest.main(verbosity=2)
