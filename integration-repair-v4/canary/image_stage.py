"""One helper-only image build; no pull, no tag overwrite, immutable readback."""
import json
import os
import re
import time
from guest import BASE,HELPER,pinned,guard,dockerfile,need

def derive(c,r,root,clock=time.time):
    context=root/'build';context.mkdir(mode=0o700)
    helper_sha=c['reviews']['helper']['sha256']
    helper=pinned(c['reviews']['helper']['path'],helper_sha)
    (context/'artex-worker-tools').write_bytes(helper);os.chmod(context/'artex-worker-tools',0o555)
    (context/'Dockerfile').write_text(dockerfile());os.chmod(context/'Dockerfile',0o644)
    tag='artex-canary-h2:'+root.name.removeprefix('artex-canary-')
    prefix=[c['docker_cli'],'--host',c['daemon']]
    need(not r.run(prefix+['image','ls','--quiet',tag]).strip(),'new tag already exists')
    r.run(prefix+['image','inspect',BASE],cap=65536)
    guard(c,r,clock())
    r.run(prefix+['build','--pull=false','--network=none','--tag',tag,'--iidfile',str(root/'image.id'),str(context)],timeout=min(120,c['deadline']-clock()-30),cap=1048576)
    image=(root/'image.id').read_text().strip();need(re.fullmatch('sha256:[a-f0-9]{64}',image),'actual image ID')
    iv=json.loads(r.run(prefix+['image','inspect',image],cap=65536))[0]
    need(iv['Id']==image and iv['Config']['Volumes']=={'/app/data':{}} and iv['Config']['User']=='1001:1002','derived image readback')
    return {'id':image,'tag':tag,'volumes':iv['Config']['Volumes'],'helper_sha256':helper_sha}
