"""Exact literal collision/replacement and actual archive race regressions."""
import hashlib,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import guest,probes
class DataV3Tests(unittest.TestCase):
 def test_literal_collision_preserves_valuable_file(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'canary-fill-00';p.write_bytes(b'VALUABLE_PREEXISTING')
   with self.assertRaises((OSError,AssertionError)):
    exec(compile(probes.QUOTA.replace('/work',d),'actual-quota-literal','exec'),{})
   self.assertTrue(p.exists(),'literal deleted pre-existing collision')
   self.assertEqual(p.read_bytes(),b'VALUABLE_PREEXISTING')
 def test_literal_refuses_replaced_owned_filler_preserves_original_error(self):
  import builtins
  real=builtins.open
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'canary-fill-00'
   class F:
    def __enter__(self):self.f=real(p,'xb',buffering=0);return self
    def fileno(self):return self.f.fileno()
    def write(self,b):raise RuntimeError('ORIGINAL_FAILURE')
    def __exit__(self,*a):self.f.close();p.rename(p.with_suffix('.held'));p.write_bytes(b'VALUABLE_REPLACEMENT')
   def opened(name,*a,**kw):return F() if str(name)==str(p) and a and a[0]=='xb' else real(name,*a,**kw)
   with patch('builtins.open',side_effect=opened),self.assertRaisesRegex(RuntimeError,'ORIGINAL_FAILURE'):
    exec(compile(probes.QUOTA.replace('/work',d),'actual-quota-literal','exec'),{})
   self.assertTrue(p.exists(),'cleanup deleted replaced inode')
   self.assertEqual(p.read_bytes(),b'VALUABLE_REPLACEMENT')
 def test_archive_swap_after_open_refused_by_same_fd_identity(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);w=d/'work';w.mkdir();p=w/'valuable';p.write_bytes(b'ORIGINAL');real=os.open;swapped=[]
   def opened(path,*a,**kw):
    fd=real(path,*a,**kw)
    if str(path)=='valuable' and not swapped:
     p.rename(w/'held');p.write_bytes(b'REPLACEMENT');swapped.append(True)
    return fd
   with patch('guest.os.open',side_effect=opened),self.assertRaisesRegex(guest.Blocked,'archive leaf changed'):
    guest.checkpoint(w,d/'archive.tar')
   self.assertEqual(p.read_bytes(),b'REPLACEMENT');self.assertTrue(swapped)
 def test_archive_never_reopens_leaf_by_path_after_metadata_check(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);w=d/'work';w.mkdir();p=w/'valuable';p.write_bytes(b'ORIGINAL')
   real=Path.read_bytes
   def raced(path):
    if path==p:p.unlink();p.write_bytes(b'REPLACEMENT')
    return real(path)
   with patch.object(Path,'read_bytes',raced):v=guest.checkpoint(w,d/'archive.tar')
   self.assertEqual(v['members']['valuable'],hashlib.sha256(b'ORIGINAL').hexdigest())
if __name__=='__main__':unittest.main()
