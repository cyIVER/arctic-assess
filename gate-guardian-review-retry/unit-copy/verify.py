"""Local-only verification receipt; no live/cloud/SSH commands are invoked."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    loader=unittest.TestLoader();suite=loader.discover(str(HERE),pattern='test_*.py')
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    print(output.getvalue(),end='')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.iterdir())
            if p.is_file() and (p.suffix=='.py' or p.name=='README.md')}
    receipt={'schema':1,'scope':'UNIT_ONLY_LOCAL_NO_CLOUD_OR_SSH_OR_TCP_SERVER',
             'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skipped':len(result.skipped),'loader_errors':loader.errors,'success':result.wasSuccessful(),
             'artifacts':hashes,'output':output.getvalue(),
             'live_status':'BLOCKED_EXTERNAL_PARENT_INSTALL_REVIEW_CONTROLLER_PROVIDER_GUEST_AND_TIMEOUT_GATES'}
    (HERE/'evidence.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (HERE/'artifact-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    sys.exit(0 if result.wasSuccessful() and not loader.errors else 1)
