"""UNIT_ONLY actual admission/path regressions. No real approval or activation."""
import hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import guest
import test_live_inputs as legacy

class AdmissionV3Tests(unittest.TestCase):
 def test_actual_pinned_rejects_writable_ancestor_after_positive(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);d.chmod(0o700);p=d/'p';p.write_bytes(b'UNIT_ONLY');p.chmod(0o600);h=hashlib.sha256(p.read_bytes()).hexdigest()
   self.assertEqual(guest.pinned(str(p),h),b'UNIT_ONLY')
   d.chmod(0o777)
   with self.assertRaises(guest.Blocked):guest.pinned(str(p),h)
 def test_actual_pinned_rejects_untrusted_owner(self):
  import types
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p';p.write_bytes(b'UNIT_ONLY');p.chmod(0o600);h=hashlib.sha256(p.read_bytes()).hexdigest()
   self.assertEqual(guest.pinned(str(p),h),b'UNIT_ONLY')
   original=os.fstat
   def changed(fd):
    s=original(fd)
    if s.st_ino==p.stat().st_ino:return types.SimpleNamespace(**{k:getattr(s,k) for k in dir(s) if k.startswith('st_')}|{'st_uid':1001})
    return s
   with patch('guest.os.fstat',side_effect=changed),self.assertRaises(guest.Blocked):guest.pinned(str(p),h)
 def test_strict_numeric_bool_schema_actual_snapshot(self):
  with tempfile.TemporaryDirectory() as d:
   c=legacy.CurrentInputTests().fixture(d);self.assertIs(guest.validate_snapshot(c,1000),c)
   with self.assertRaises(guest.Blocked):guest.validate_snapshot(c|{'schema':True},1000)
 def test_stage_created_directories_explicitly_protected(self):
  with tempfile.TemporaryDirectory() as d:
   c=legacy.CurrentInputTests().fixture(d)
   for p in Path(c['isolation_root']).rglob('*'):
    if p.is_dir():self.assertEqual(p.stat().st_mode&0o022,0,str(p))
 def test_current_requires_external_parent_context_before_commands(self):
  from test_guest import FakeCLI
  import driver
  with tempfile.TemporaryDirectory() as d:
   c=legacy.CurrentInputTests().fixture(d);r=FakeCLI([])
   with self.assertRaises(guest.Blocked):driver.run(c,runner=r,clock=lambda:1000)
   self.assertEqual(r.events,[])
if __name__=='__main__':unittest.main()
