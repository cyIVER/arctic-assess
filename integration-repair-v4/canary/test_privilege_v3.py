"""UNIT_ONLY privilege contract; never actually change local UID/GID."""
import os, subprocess, sys, unittest
from unittest.mock import patch
import guest, driver

class PrivilegeTests(unittest.TestCase):
 def test_real_popen_caller_identity_and_safe_cwd(self):
  real=subprocess.Popen;seen=[]
  def observe(*a,**kw):
   seen.append(dict(kw));safe=dict(kw)
   for k in ('user','group','extra_groups'):safe.pop(k,None)
   return real(*a,**safe)
  with patch('guest.subprocess.Popen',side_effect=observe):
   fn=getattr(guest,'call_caller',lambda r,a,**kw:r.run(a,**kw))
   self.assertEqual(fn(guest.Runner(),[sys.executable,'-c','print("UNIT_ONLY")']),b'UNIT_ONLY\n')
  self.assertEqual(seen[0].get('user'),1001)
  self.assertEqual(seen[0].get('group'),1002)
  self.assertEqual(seen[0].get('extra_groups'),[])
  self.assertEqual(seen[0].get('cwd'),'/')
  self.assertTrue(seen[0].get('close_fds'))
 def test_target_actual_fork_drops_inherited_fds_no_uid_change(self):
  import fixture_service,json,tempfile
  with tempfile.TemporaryDirectory() as d:
   r,w=os.pipe();extra=os.open(d,os.O_RDONLY|os.O_DIRECTORY);pid=os.fork()
   if pid==0:
    try:
     os.chdir(d);fixture_service.close_child_fds(w)
     live=[]
     for n in os.listdir('/proc/self/fd'):
      try:os.fstat(int(n));live.append(int(n))
      except OSError:pass
     os.write(w,json.dumps({'fds':live,'cwd':os.getcwd()}).encode());os._exit(0)
    except BaseException:os._exit(2)
   os.close(w)
   try:
    data=json.loads(os.read(r,4096));_,status=os.waitpid(pid,0)
    self.assertEqual(status,0);self.assertEqual(data,{'fds':[w],'cwd':d})
   finally:os.close(r);os.close(extra)
 def test_prepare_actual_public_copy_and_peer_policy_unit_only(self):
  import tempfile,socket
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);seen=[]
   class Server:
    def __init__(self,path,key,uid,broker):self.path=path;seen.append(uid)
    def start(self):self.socket=socket.socket(socket.AF_UNIX);self.socket.bind(self.path)
   def paths(p):
    p=str(p)
    return root/Path(p).name if p.startswith('/run/artex-client-') or p.startswith('/run/artex-exec-') else Path(p)
   import hashlib
   c={'root':'/run/artex-canary-0123456789ab','caller':str(guest.HERE/'caller'),'reviews':{'caller':{'sha256':hashlib.sha256((guest.HERE/'caller').read_bytes()).hexdigest()}}}
   with patch('guest.Path',side_effect=paths),patch('guest.os.chown') as chown:
    server,exe,sock,client,public=guest.prepare_caller(c,b'UNIT_ONLY',None,Server)
   try:
    self.assertEqual(seen,[1001]);chown.assert_called_once_with(sock,1001,1002)
    self.assertEqual(client.stat().st_mode&0o777,0o711);self.assertEqual(public.stat().st_mode&0o777,0o755)
    self.assertEqual(exe.stat().st_mode&0o777,0o555);self.assertEqual(sock.stat().st_mode&0o777,0o600)
    self.assertEqual(exe.read_bytes(),(guest.HERE/'caller').read_bytes())
   finally:server.socket.close()
 def test_target_closes_inherited_fds_and_chdirs(self):
  import inspect, fixture_service
  s=inspect.getsource(fixture_service.Target.start)
  self.assertIn('os.chdir(self.state)',s)
  self.assertIn('close_child_fds(w)',s)
 def test_controller_private_and_separate_uds_policy(self):
  import inspect
  s=inspect.getsource(driver.run)
  self.assertIn('root.mkdir(mode=0o700)',s)
  self.assertNotIn("ControlServer(str(root/'control.sock'),key,os.getuid()",s)
  self.assertIn('prepare_caller',s)
  # Linux DAC symbolic exact future modes. No impersonation performed.
  def allowed(mode,owner,group,uid,gids,bit):
   shift=6 if uid==owner else 3 if group in gids else 0
   return bool((mode>>shift)&bit)
  self.assertFalse(allowed(0o700,0,0,1001,[1002],1))
  self.assertTrue(allowed(0o711,0,0,1001,[1002],1))
  self.assertTrue(allowed(0o600,1001,1002,1001,[1002],2))
  self.assertFalse(allowed(0o600,1001,1002,1003,[1002],2))
  self.assertTrue(allowed(0o555,0,0,1001,[1002],1))
if __name__=='__main__':unittest.main()
