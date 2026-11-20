"""Focused offline tests; no live DB/config binding, installs or services."""
import json,os,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent
E=R/'data-intercept-evidence'
base=json.loads((R.parents[1]/'artex-worker-admission/receipts/p2-red-environment.json').read_text())
env=dict(os.environ);env.update(base)
for key in list(env):
 if key.startswith('ARTEX_'):env.pop(key)
env['GOFLAGS']='-mod=readonly';env['GOCACHE']=str(E/'gocache');env['GOTMPDIR']=str(E/'tmp');Path(env['GOTMPDIR']).mkdir(exist_ok=True)
# Reuse existing compiled artifacts via symlinks, never copy the large cache.
cache=Path(env['GOCACHE']);cache.mkdir(exist_ok=True)
for p in Path(base['GOCACHE']).glob('*'):
 if p.is_dir() and not (cache/p.name).exists():(cache/p.name).symlink_to(p,target_is_directory=True)
cmd=[env['GOROOT']+'/bin/go','test','-p','2','-json','./db','./intercept','-run',sys.argv[2] if len(sys.argv)>2 else 'Test(English|InterceptSourceEnglishLegacy|ApprovalSQLRecognizesEnglishLegacy)','-count=1','-timeout=60s']
p=subprocess.run(cmd,cwd=R/'source',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
(E/(sys.argv[1]+'.jsonl')).write_bytes(p.stdout)
rows=[]
for line in p.stdout.decode().splitlines():
 try:rows.append(json.loads(line))
 except ValueError:pass
terminal=[r for r in rows if r.get('Test') and r.get('Action') in ('pass','fail','skip')]
summary={'command':cmd,'offline':True,'GOCACHE':env['GOCACHE'],'cache_note':'Task cache directory with symlinks to retained cache buckets; no large copies.','returncode':p.returncode,'top_level':{a:sum(r['Action']==a and '/' not in r['Test'] for r in terminal) for a in ('pass','fail','skip')},'subtests':{a:sum(r['Action']==a and '/' in r['Test'] for r in terminal) for a in ('pass','fail','skip')},'package_failures':[r for r in rows if r.get('Action')=='fail' and not r.get('Test')],'tests':[{'name':r['Test'],'action':r['Action']} for r in terminal]}
(E/(sys.argv[1]+'.json')).write_text(json.dumps(summary,indent=2));print(p.stdout.decode()[-10000:]);print(json.dumps(summary));sys.exit(p.returncode)
