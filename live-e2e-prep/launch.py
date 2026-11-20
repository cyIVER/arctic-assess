#!/usr/bin/python3
"""Parent-reviewed source bootstrap; CLI is nonmutating preflight ONLY.
No PYTHONPATH, no pycache, no approval creation, no transport key handling.
"""
import json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare import check_stage

def preflight(root,manifest_sha,config_path,now=None):
    check_stage(root,manifest_sha)
    sys.path.insert(0,str(Path(root)/'canary'))
    import guest,admission_v3
    c=admission_v3.protected_json(config_path)
    guest.validate(c,time.time() if now is None else now)
    guest.guard(c,guest.Runner(),time.time() if now is None else now)
    return c

def launch_seam(c,driver_module):
    # Exactly the reviewed production call, not a stand-in canary/report.
    return driver_module.run(c)

def bootstrap_argv(root,manifest_sha,config_path):
    # Parent executes only AFTER separate .25 session enforcement, context,
    # runtime pin and review binding checks. Current v4 budget incompatibility
    # is not waived by this argv; driver.validate remains authoritative.
    script=("import sys,runpy;sys.dont_write_bytecode=True;"
        "sys.path.insert(0,'/opt/artex-live-prep');"
        "from prepare import check_stage;check_stage("+repr(str(root))+","+repr(manifest_sha)+");"
        "sys.path.insert(0,"+repr(str(Path(root)/'canary'))+");"
        "sys.argv=['driver.py','--live','--config',"+repr(config_path)+"];"
        "runpy.run_path("+repr(str(Path(root)/'canary/driver.py'))+",run_name='__main__')")
    return ['/usr/bin/python3','-I','-B','-c',script]

if __name__=='__main__':
    try:
        if len(sys.argv)!=4:raise ValueError('usage: launch.py STAGED_ROOT STAGE_MANIFEST_SHA PROTECTED_CONFIG')
        c=preflight(*sys.argv[1:])
        print(json.dumps({'status':'PREFLIGHT_ONLY_NOT_LAUNCHED','runtime_proof':False,'argv':bootstrap_argv(*sys.argv[1:])}))
    except Exception as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e),'runtime_proof':False}));sys.exit(2)
