import os,pathlib,sys,tempfile,threading,time,unittest
from hostbroker.broker import DockerCLI,Policy,Refused
class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.tmp.name)/'fake-cli'
        self.path.write_text('#!'+sys.executable+'\nimport os,sys,time\nmode=sys.argv[-1]\nif mode=="timeout":time.sleep(3)\nif mode=="large":sys.stdout.buffer.write(b"x"*200000)\nif mode=="env":print(os.getenv("CONTROLLER_CANARY","absent"))\n')
        self.path.chmod(0o700);self.cli=DockerCLI(Policy('sha256:'+'b'*64,self.tmp.name,os.getuid(),os.getgid(),str(self.path),'unix:///private/docker.sock'))
    def tearDown(self):self.tmp.cleanup()
    def test_clean_env_real_fake_cli(self):
        old=os.environ.get('CONTROLLER_CANARY');os.environ['CONTROLLER_CANARY']='synthetic-secret'
        try:self.assertEqual(self.cli.run(['env'],timeout=1,cancel=threading.Event(),max_bytes=1024),b'absent\n')
        finally:
            if old is None:os.environ.pop('CONTROLLER_CANARY',None)
            else:os.environ['CONTROLLER_CANARY']=old
    def test_outer_deadline_and_cancel_real_fake_cli(self):
        for cancel,timeout in [(threading.Event(),.1),(threading.Event(),2)]:
            timer=threading.Timer(.05,cancel.set) if timeout==2 else None
            if timer:timer.start()
            start=time.monotonic()
            with self.assertRaises(Refused):self.cli.run(['timeout'],timeout=timeout,cancel=cancel,max_bytes=1024)
            self.assertLess(time.monotonic()-start,1)
            if timer:timer.join()
    def test_outer_bytes_charge_even_rejected_output(self):
        counts=[]
        with self.assertRaises(Refused):self.cli.run(['large'],timeout=1,cancel=threading.Event(),max_bytes=1024,charge=counts.append)
        self.assertGreater(sum(counts),0)
