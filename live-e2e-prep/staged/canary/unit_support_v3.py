"""UNIT_ONLY metadata seam. Never imported by production entrypoints.
Local UID1000 cannot create root-owned fixtures and protected filesystem has
pre-existing group-writable ancestors. Only these exact infrastructure inodes
are substituted, never fixture directories/leaves. No chmod of host ancestors.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import os
import guest
@contextmanager
def unit_permissions():
    paths=[Path('/home/iveri/.hermes/cache'),guest.HERE.parent]
    exempt={(p.stat().st_dev,p.stat().st_ino) for p in paths}
    original=guest.trusted_directory
    def directory(fd):
        s=os.fstat(fd)
        if (s.st_dev,s.st_ino) in exempt:
            guest.need(s.st_uid==os.getuid(),'unit infrastructure owner');return
        return original(fd)
    with patch.object(guest,'TRUSTED_UID',os.getuid()),patch.object(guest,'trusted_directory',directory):yield
