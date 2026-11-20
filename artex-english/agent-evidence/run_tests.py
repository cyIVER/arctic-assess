import os, pathlib, subprocess, sys, json, time
root = pathlib.Path(__file__).resolve().parent.parent
base = root.parent.parent / 'artex-worker-build-cache'
env = dict(os.environ)
env.update(GOROOT=str(base/'cache/goroot'), GOMODCACHE=str(base/'cache/gomodcache'), GOCACHE=str(base/'local/gocache'), GOPROXY='off', GOSUMDB='off', GOTOOLCHAIN='local', GOFLAGS='-mod=readonly', GOMAXPROCS='2')
# Only narrow package tests; never download modules or build the application.
label = sys.argv[1]
args = sys.argv[2:]
cmd = [str(base/'cache/goroot/bin/go'), 'test', '-p=1', '-json', '-count=1', *args]
start=time.time()
p = subprocess.run(cmd, cwd=root/'source', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=150)
out = pathlib.Path(__file__).parent
(out/(label+'.jsonl')).write_bytes(p.stdout)
events=[]
for line in p.stdout.decode().splitlines():
 try: events.append(json.loads(line))
 except ValueError: pass
terminal=[e for e in events if e.get('Test') and e.get('Action') in ('pass','fail','skip')]
summary={'command':cmd,'env':{k:env[k] for k in ('GOROOT','GOMODCACHE','GOCACHE','GOPROXY','GOSUMDB','GOTOOLCHAIN','GOFLAGS','GOMAXPROCS')},'returncode':p.returncode,'seconds':time.time()-start,'top_level':{a:sum(e['Action']==a and '/' not in e['Test'] for e in terminal) for a in ('pass','fail','skip')},'subtests':{a:sum(e['Action']==a and '/' in e['Test'] for e in terminal) for a in ('pass','fail','skip')},'package_failures':[e for e in events if not e.get('Test') and e.get('Action')=='fail'],'tests':[e.get('Test') for e in terminal]}
(out/(label+'.json')).write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2));print(p.stdout.decode()[-7000:]);sys.exit(p.returncode)
