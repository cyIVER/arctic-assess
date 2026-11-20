"""UNIT_ONLY: injected cloud/SSH/process boundary; never live provider access."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import guard

NOW=1800000000.0

def fixture():
    return {'schema':1,'vm':guard.VM,'lane':'literal-no-model-isolation',
            'guard_created':NOW-30,'external_stop':NOW+3570,'controller_id':'unit-controller',
            'controller':{'pid':34567,'uid':0,'start_ticks':123,'exe':'/usr/bin/python3.12',
                          'cmd_sha256':'a'*64,'script':{'path':'/opt/artex-live-guard/controller.py','sha256':'b'*64},
                          'checkpoint':{'path':'/opt/artex-live-guard/approval-checkpoint.json','sha256':'c'*64}},
            'network':{'network':'projects/syncfall-ir-range/global/networks/default',
                       'subnetwork':'projects/syncfall-ir-range/regions/us-central1/subnetworks/default','networkIP':'10.128.0.2'},
            'preflight':{'path':'/run/artex-live-guard/preflight.json','sha256':'d'*64}}

class Runner:
    def __init__(self):
        self.calls=[]
        self.vm={'id':guard.VM['id'],'name':guard.VM['name'],'status':'RUNNING','serviceAccounts':[],
                 'networkInterfaces':[dict(fixture()['network'],name='nic0',accessConfigs=[],ipv6AccessConfigs=[])],
                 'disks':[{'source':'projects/syncfall-ir-range/zones/us-central1-a/disks/vindler-lab-01','autoDelete':False,'boot':True}],
                 'scheduling':{'automaticRestart':False,'instanceTerminationAction':'STOP',
                               'terminationTime':datetime.datetime.fromtimestamp(NOW+3570,datetime.timezone.utc).isoformat()}}
        self.disk={'id':guard.VM['disk_id'],'name':guard.VM['name']}
        self.guest={'default_docker_quiescent':True,'checkpoint_sha256':'d'*64}
        self.fail=False
    def __call__(self,args,timeout):
        self.calls.append((args,timeout))
        if self.fail: raise subprocess.TimeoutExpired(args,timeout)
        if 'instances' in args: out=self.vm
        elif 'disks' in args: out=self.disk
        elif args[0]=='/usr/bin/ssh': out=self.guest
        else: raise AssertionError(args)
        return subprocess.CompletedProcess(args,0,json.dumps(out),'')

class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.scope=fixture(); self.runner=Runner(); self.identities=[]
    def identity(self,c):
        self.identities.append(copy.deepcopy(c)); return object()
    def status(self):
        return guard.VPSGuardReadback(self.scope,runner=self.runner,clock=lambda:NOW,
                                      controller_check=self.identity,controller_release=lambda token:None).status()
    def test_positive_fresh_real_readback_commands(self):
        result=self.status()
        self.assertEqual(result,dict(alive=True,provider_state='RUNNING',vm=guard.VM,
            stop_at=NOW+3570,controller_id='unit-controller',guard_created=NOW-30,
            default_docker_quiescent=True,preflight_checkpoint_sha256='d'*64))
        self.assertEqual(len(self.identities),2)
        self.assertEqual(len(self.runner.calls),3)
        self.assertIn('instances',self.runner.calls[0][0]); self.assertIn('disks',self.runner.calls[1][0])
        self.assertEqual(self.runner.calls[2][0][0],'/usr/bin/ssh')
    def test_default_missing_scope_blocked(self):
        with self.assertRaises(guard.Blocked): guard.VPSGuardReadback(None,runner=self.runner).status()
        self.assertEqual(self.runner.calls,[])
    def test_provider_fail_closed(self):
        cases=[('wrong_vm',lambda v:v.update(id='wrong')),('state',lambda v:v.update(status='TERMINATED')),
               ('SA',lambda v:v.update(serviceAccounts=[{'email':'forbidden'}])),
               ('public_IP',lambda v:v['networkInterfaces'][0].update(accessConfigs=[{'natIP':'1.2.3.4'}])),
               ('ipv6',lambda v:v['networkInterfaces'][0].update(ipv6Address='::1')),
               ('extra_NIC',lambda v:v['networkInterfaces'].append(v['networkInterfaces'][0].copy())),
               ('network',lambda v:v['networkInterfaces'][0].update(networkIP='10.0.0.99')),
               ('deadline',lambda v:v['scheduling'].update(terminationTime='2030-01-01T00:00:00Z')),
               ('restart',lambda v:v['scheduling'].update(automaticRestart=True)),
               ('delete',lambda v:v['disks'][0].update(autoDelete=True))]
        for name,mutate in cases:
            with self.subTest(name=name):
                original=copy.deepcopy(self.runner.vm); mutate(self.runner.vm)
                with self.assertRaises(guard.Blocked): self.status()
                self.runner.vm=original
    def test_expiry_overflow_and_wrong_scope(self):
        for k,v in [('external_stop',NOW-1),('external_stop',float('inf')),('external_stop',NOW+5500),
                    ('guard_created',float('nan')),('vm',dict(guard.VM,id='wrong'))]:
            with self.subTest(k=k,v=v):
                self.scope=fixture(); self.scope[k]=v
                with self.assertRaises(guard.Blocked): self.status()
    def test_no_cache_on_query_failure(self):
        self.status(); self.runner.fail=True
        with self.assertRaises(guard.Blocked): self.status()
    def test_no_pid_and_bad_default_and_disk(self):
        def bad(c): raise guard.Blocked('identity')
        with self.assertRaises(guard.Blocked):
            guard.VPSGuardReadback(self.scope,runner=self.runner,clock=lambda:NOW,controller_check=bad).status()
        self.assertEqual(self.runner.calls,[])
        self.runner.guest['default_docker_quiescent']=False
        with self.assertRaises(guard.Blocked): self.status()
        self.runner.guest['default_docker_quiescent']=True;self.runner.disk['id']='wrong'
        with self.assertRaises(guard.Blocked): self.status()

if __name__=='__main__': unittest.main()
