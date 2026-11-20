"""Offline server tests using retained toolchain/cache; no database provisioning."""
import json, os, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parent.parent
E = R / 'server-evidence'
P = R.parents[1] / 'artex-worker-admission/receipts/p2-red-environment.json'
env = dict(os.environ)
env.update(json.loads(P.read_text()))
env['GOFLAGS'] = '-mod=readonly'
# Do not inherit a live runtime/database binding or discover global configuration.
for key in list(env):
    if key.startswith('ARTEX_'):
        env.pop(key)
mode = sys.argv[1]
pattern = sys.argv[2] if len(sys.argv) > 2 else '^TestChatMention(EnglishLegacyCompatibility|Parsing|BoundedJSON)$'
cmd = [env['GOROOT'] + '/bin/go', 'test', '-p', '2', '-json', './server', '-run', pattern, '-count=1', '-timeout=90s']
p = subprocess.run(cmd, cwd=R/'source', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
(E/(mode+'.jsonl')).write_bytes(p.stdout)
rows=[]
for line in p.stdout.decode().splitlines():
    try: rows.append(json.loads(line))
    except ValueError: pass
terminal = [r for r in rows if r.get('Test') and r.get('Action') in ('pass','fail','skip')]
summary = {'command':cmd, 'environment':{k:env[k] for k in json.loads(P.read_text())}, 'returncode':p.returncode, 'top_level':{a:sum(r['Action']==a and '/' not in r['Test'] for r in terminal) for a in ('pass','fail','skip')}, 'subtests':{a:sum(r['Action']==a and '/' in r['Test'] for r in terminal) for a in ('pass','fail','skip')}, 'tests':[{'name':r['Test'],'action':r['Action']} for r in terminal]}
(E/(mode+'.json')).write_text(json.dumps(summary,indent=2))
print(p.stdout.decode()[-16000:]); print(json.dumps(summary))
sys.exit(p.returncode)
