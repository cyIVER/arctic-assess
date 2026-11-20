"""Explicit fixture-only migration; no production validator is replaced."""
import copy,json,tempfile
from pathlib import Path
import test_integration as t

def install(root):
 old=t.tuples.fixture
 def current(d):
  c,context,a=old(d);t.bind(c,context,a,t.merged(c));return c,context,a
 t.tuples.fixture=current
 import test_security
 old_setup=test_security.Guest.setUp
 old_status=test_security.Guest.status
 def setup(self):
  old_setup(self)
  created=self.proof['created'];c=self.scope
  c.update(created=created,deadline=created+600,parent_scope_lease={'handle':'UNIT_ONLY_NOT_AUTHORITY','vm':c['vm'],'lane':c['lane'],'created':created,'deadline':created+600})
  self.proof=t.merged(c)
 def status(self):
  self.scope['preflight']['sha256']=t.guard.digest(t.guard.canonical(self.proof))
  return old_status(self)
 test_security.Guest.setUp=setup;test_security.Guest.status=status
 import test_host
 host_setup=test_host.Host.setUp
 scratch=root/'host-scratch';scratch.mkdir(mode=0o700,exist_ok=True);scratch.chmod(0o700)
 def host(self):
  previous=tempfile.tempdir
  try:tempfile.tempdir=str(scratch);host_setup(self)
  finally:tempfile.tempdir=previous
 test_host.Host.setUp=host
