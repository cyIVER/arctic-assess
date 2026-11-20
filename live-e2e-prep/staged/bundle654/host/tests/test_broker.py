import json, os, pathlib, socket, tempfile, threading, unittest
from hostbroker.broker import Broker, Policy, Scope, Refused
from hostbroker.gateway import Budget
BINDING=dict(PhaseID='phase',Generation=1,TaskID=1,ExplorationID=2,IntentID=3,Role='worker',SessionID='session',ExecutorID='executor',NetworkPolicyID='fixture')
class FakeDocker:
    def __init__(self):self.calls=[];self.live=set();self.failure=None
    def run(self,args,payload=b'',**kw):
        self.calls.append((args,payload,kw))
        if args[:2]==['image','inspect']:return b'{"/app/data":{}}'
        if args[0]=='inspect':
            create=next(c[0] for c in reversed(self.calls) if c[0][0]=='create')
            mounts=[]
            for arg in create:
                if arg.startswith('type=bind,src='):
                    source=arg.split(',src=')[1].split(',dst=')[0];dest=arg.split(',dst=')[1].split(',')[0]
                    mounts.append(dict(Type='bind',Source=source,Destination=dest,RW=dest=='/work'))
            return json.dumps(dict(mounts=mounts,tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=16m,mode=1777','/app/data':'ro,noexec,nosuid,nodev,size=64k,mode=0555'})).encode()
        if args[0]=='create':self.live.add(args[args.index('--name')+1]);return b'container-id\n'
        if args[0]=='start':
            if self.failure:raise self.failure
            return json.dumps({'version':1,'result':{'Content':[{'type':'text','text':'isolated'}],'IsError':False}}).encode()
        if args[:2]==['rm','--force']:self.live.discard(args[-1]);return b''
        if args[0]=='ps':return ('\n'.join(self.live)).encode()
        raise AssertionError(args)
class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);os.chmod(self.root,0o700);self.work=self.root/'work';self.work.mkdir(mode=0o700);self.sockdir=self.root/'fixture';self.sockdir.mkdir(mode=0o700)
        self.fixture_socket=socket.socket(socket.AF_UNIX);self.fixture_socket.bind(str(self.sockdir/'gateway.sock'));os.chmod(self.sockdir/'gateway.sock',0o600)
        self.fake=FakeDocker();self.budget=Budget();self.scope=Scope(BINDING,str(self.work),str(self.sockdir),self.budget)
        self.policy=Policy('sha256:'+'a'*64,str(self.root),os.getuid(),os.getgid(),'/usr/bin/docker','unix:///private-task/docker.sock')
        self.b=Broker(self.policy,[self.scope],driver=self.fake,reviewed=True)
    def tearDown(self):self.fixture_socket.close();self.tmp.cleanup()
    def req(self,**kw):return dict(Binding=BINDING.copy(),Tool='Bash',Input={'command':'arbitrary pipeline | is allowed inside future sandbox'},ToolUseID='use-1',**kw)
    def test_fixed_argv_clean_private_env_all_outcome_cleanup(self):
        result=self.b.execute(self.req());self.assertEqual(result['version'],1);self.assertEqual(self.fake.live,set())
        create=next(c[0] for c in self.fake.calls if c[0][0]=='create')
        for flag in ['--read-only','--cap-drop=ALL','--network=none','--pid=private','--ipc=private','--security-opt=no-new-privileges','--pids-limit=64','--memory=256m'] :self.assertIn(flag,create)
        self.assertEqual(create[-3:],['--entrypoint','/usr/local/bin/artex-worker-tools','sha256:'+'a'*64])
        self.assertNotIn('CONTROLLER_CANARY',str(self.fake.calls));self.assertEqual([c[0][0] for c in self.fake.calls],['image','create','inspect','start','rm','ps'])
        self.assertEqual(json.loads(next(c[1] for c in self.fake.calls if c[0][0]=='start'))['input'],self.req()['Input'])
    def test_unknown_identity_and_paths_before_docker(self):
        req=self.req();req['Binding']['IntentID']=999
        with self.assertRaises(Refused):self.b.execute(req)
        req=self.req();req['host_path']='/secret'
        with self.assertRaises(Refused):self.b.execute(req)
        self.assertEqual(self.fake.calls,[])
    def test_cleanup_timeout_cancel_error_and_success(self):
        self.fake.failure=TimeoutError('fake timeout')
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertFalse(self.fake.live);self.assertEqual([c[0][0] for c in self.fake.calls],['image','create','inspect','start','rm','ps'])
        self.budget.cancel();count=len(self.fake.calls)
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertEqual(len(self.fake.calls),count)
    def test_disabled_and_workspace_symlink_no_docker(self):
        b=Broker(self.policy,[self.scope],driver=self.fake)
        with self.assertRaises(Refused):b.execute(self.req())
        self.work.rmdir();self.work.symlink_to(self.root)
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertEqual(self.fake.calls,[])
    def test_duplicate_workspace_across_intents_rejected(self):
        binding=BINDING.copy();binding['IntentID']=4
        other=Scope(binding,str(self.work),str(self.sockdir),Budget())
        with self.assertRaises(Refused):Broker(self.policy,[self.scope,other],driver=self.fake,reviewed=True)
    def test_fixture_directory_cannot_contain_control_material(self):
        (self.sockdir/'controller-key').write_text('synthetic')
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertEqual(self.fake.calls,[])
    def test_phase_quota_shared_between_dynamic_intents(self):
        other_binding=BINDING.copy();other_binding['IntentID']=4
        otherwork=self.root/'other';otherwork.mkdir(mode=0o700)
        other=Scope(other_binding,str(otherwork),str(self.sockdir),Budget())
        b=Broker(self.policy,[self.scope,other],driver=self.fake,reviewed=True)
        for _ in range(32):b.execute(self.req())
        req=self.req();req['Binding']=other_binding;count=len(self.fake.calls)
        with self.assertRaises(Refused):b.execute(req)
        self.assertEqual(len(self.fake.calls),count)
    def test_workspace_cannot_be_entire_data_root(self):
        bad=Scope(BINDING,str(self.root),str(self.sockdir),Budget())
        with self.assertRaises(Refused):Broker(self.policy,[bad],driver=self.fake,reviewed=True)
    def test_quarantine_capacity_if_cleanup_not_confirmed(self):
        original=self.fake.run
        def run(args,*a,**kw):
            if args[0]=='ps':return b'lingering'
            return original(args,*a,**kw)
        self.fake.run=run
        with self.assertRaises(Refused):self.b.execute(self.req())
        count=len(self.fake.calls)
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertEqual(len(self.fake.calls),count)
