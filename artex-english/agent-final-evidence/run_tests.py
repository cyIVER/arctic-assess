import os, subprocess, json, time
from pathlib import Path
ROOT=Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/artex-english')
E=ROOT/'agent-final-evidence'
CACHE=Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation/artex-worker-build-cache')
env=os.environ.copy()
settings=dict(GOROOT=str(CACHE/'cache/goroot'),GOMODCACHE=str(CACHE/'cache/gomodcache'),GOCACHE=str(CACHE/'local/gocache'),GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOFLAGS='-mod=readonly',GOMAXPROCS='2',TMPDIR=str(E/'scratch'),GOTMPDIR=str(E/'scratch'))
(E/'scratch').mkdir(exist_ok=True)
env.update(settings)
def run(label, pattern):
 cmd=[settings['GOROOT']+'/bin/go','test','-p=1','-json','-count=1','./agent','./guard','-run',pattern]
 start=time.monotonic()
 with (E/(label+'.jsonl')).open('w') as f:
  p=subprocess.run(cmd,cwd=ROOT/'source',env=env,stdout=f,stderr=subprocess.STDOUT,timeout=150)
 data=[]
 for line in (E/(label+'.jsonl')).read_text().splitlines():
  try:data.append(json.loads(line))
  except:pass
 counts={k:{a:sum(x.get('Action')==a and bool(x.get('Test')) and (('/' in x['Test'])==(k=='subtests')) for x in data) for a in ['pass','fail','skip']} for k in ['top_level','subtests']}
 receipt=dict(command=cmd,env=settings,returncode=p.returncode,seconds=time.monotonic()-start,**counts,package_failures=[x for x in data if x.get('Action')=='fail' and not x.get('Test')],tests=[x['Test'] for x in data if x.get('Test') and x.get('Action') in ['pass','fail','skip']])
 (E/(label+'.json')).write_text(json.dumps(receipt,indent=2))
 print(json.dumps(receipt,indent=2))
 if p.returncode:print('\n'.join(x.get('Output','') for x in data if 'FAIL' in x.get('Output','') or 'untranslated' in x.get('Output',''))[:10000])
if __name__=='__main__':
 import sys
 run(sys.argv[1],sys.argv[2])
