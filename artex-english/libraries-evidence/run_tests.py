import os, subprocess, json, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
CACHE=ROOT.parent.parent/'artex-worker-build-cache'
env=os.environ.copy()
env.update(GOROOT=str(CACHE/'cache/goroot'),GOMODCACHE=str(CACHE/'cache/gomodcache'),GOCACHE=str(CACHE/'local/gocache'),GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOFLAGS='-mod=readonly',GOMAXPROCS='2')
# No PostgreSQL startup, services, downloads, or application binary build.
import sys
name=sys.argv[1]; args=sys.argv[2:]
cmd=[env['GOROOT']+'/bin/go','test','-p=1','-json','-count=1']+args
start=time.time()
r=subprocess.run(cmd,cwd=ROOT/'source',env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
out=ROOT/'libraries-evidence';(out/(name+'.jsonl')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
counts={k:{a:0 for a in ['pass','fail','skip']} for k in ['top_level','subtests']}; failures=[]; skipped=[]
for l in r.stdout.splitlines():
 try:x=json.loads(l)
 except ValueError:continue
 if x.get('Test') and x['Action'] in counts['top_level']:
  counts['subtests' if '/' in x['Test'] else 'top_level'][x['Action']]+=1
  if x['Action']=='skip':skipped.append(x['Package']+'/'+x['Test'])
 if not x.get('Test') and x['Action']=='fail':failures.append(x['Package'])
summary=dict(command=cmd,env={k:env[k] for k in ['GOROOT','GOMODCACHE','GOCACHE','GOPROXY','GOSUMDB','GOTOOLCHAIN','GOFLAGS','GOMAXPROCS']},returncode=r.returncode,seconds=time.time()-start,**counts,package_failures=failures,skipped=skipped)
(out/(name+'.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2)); print(r.stderr);print(''.join(l+'\n' for l in r.stdout.splitlines() if '--- FAIL' in l or 'english_test.go' in l))
