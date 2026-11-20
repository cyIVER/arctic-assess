#!/usr/bin/env python3
"""Guest-only target installer. Foreground deadline guard; never downloads images.
Run only on the authorized guest with the task's private Docker daemon.
"""
import argparse, ipaddress, json, pathlib, re, signal, subprocess, time, urllib.parse
DEADLINE=None
USE_CONFIG_IDS=False

def runtime_image(role):
    im=PINS['images'][pinned_role(role)]
    return im['config_digest'] if USE_CONFIG_IDS else im['pinned']

def pinned_role(role):
    return 'dvwa' if role=='web' else role
ROOT=pathlib.Path(__file__).resolve().parent
HOST='unix:///home/vindleradmin/artex-standalone-phase-a-standing/docker.sock'
LABEL='lab.owner=dvwa-target-20261119'
BACK='dvwa-target-20261119-backend'
FRONT='artex-native-owned-internal'
SUBNET='172.29.89.0/24'
WEB='dvwa-target-20261119-web'
DB='dvwa-target-20261119-db'
PINS=json.loads((ROOT/'pins.json').read_text())

def docker(*args, data=None, timeout=40, check=True):
    if DEADLINE is not None:
        remaining=DEADLINE-60-time.time()
        if remaining<=0: raise RuntimeError('deadline safety reserve reached')
        timeout=min(timeout,remaining)
    p=subprocess.run(['docker','--host',HOST,*args],input=data,text=True,capture_output=True,timeout=timeout)
    if check and p.returncode: raise RuntimeError('Docker operation failed: '+args[0]+' '+p.stderr[:800])
    return p

def info(kind,name,timeout=40):
    return json.loads(docker(kind,'inspect',name,timeout=timeout).stdout)[0]

def exists(kind,name,timeout=40):
    return docker(kind,'inspect',name,check=False,timeout=timeout).returncode==0

def owned(obj):
    return (obj.get('Config',{}).get('Labels') or obj.get('Labels') or {}).get('lab.owner')=='dvwa-target-20261119'

def run_args(role):
    name=DB if role=='db' else WEB
    a=['run','--detach','--pull=never','--platform=linux/amd64','--name',name,'--label',LABEL,'--network',BACK,'--network-alias','db' if role=='db' else 'dvwa-target',
       '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--restart=no','--pids-limit=160','--cpus=0.75','--memory=768m' if role=='db' else '--memory=384m',
       '--memory-swap=768m' if role=='db' else '--memory-swap=384m','--log-driver=local','--log-opt=max-size=5m','--log-opt=max-file=2','--shm-size=16m']
    if role=='db':
        a+=['--user=mysql','--tmpfs','/var/lib/mysql:rw,nosuid,nodev,noexec,size=512m,mode=1777','--tmpfs','/run/mysqld:rw,nosuid,nodev,noexec,size=8m,mode=1777','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=32m,mode=1777',
            '-e','MARIADB_ROOT_PASSWORD=dvwa-lab-only-root','-e','MARIADB_DATABASE=dvwa','-e','MARIADB_USER=dvwa','-e','MARIADB_PASSWORD=p@ssw0rd']
    else:
        a+=['--user=www-data','--sysctl','net.ipv4.ip_unprivileged_port_start=0']
        for dest,size,mode in [('/tmp','32m','1777'),('/var/run/apache2','8m','0755'),('/var/lock/apache2','4m','0755'),('/var/log/apache2','16m','0755'),('/var/lib/php/sessions','8m','0700'),('/var/www/html/hackable/uploads','32m','0755')]:
            a+=['--tmpfs',f'{dest}:rw,nosuid,nodev,noexec,size={size},mode={mode},uid=33,gid=33']
        a+=['-e','DB_SERVER=db','-e','DB_DATABASE=dvwa','-e','DB_USER=dvwa','-e','DB_PASSWORD=p@ssw0rd','-e','DEFAULT_SECURITY_LEVEL=low']
    a.append(runtime_image(role))
    return a

def validate_args(a):
    # A fixed reviewed allowlist, not a general-purpose Docker argument filter.
    if a not in (run_args('web'),run_args('db')): raise ValueError('unreviewed launch arguments')

def preflight():
    if not PINS['fits_download_budget']: raise RuntimeError('download budget exceeded')
    for name in (WEB,DB):
        if exists('container',name): raise RuntimeError('name already exists; refusing reuse '+name)
    if exists('network',BACK): raise RuntimeError('backend name already exists; refusing reuse')
    networks=[json.loads(line) for line in docker('network','ls','--format','{{json .}}').stdout.splitlines() if line.strip()]
    front=info('network',FRONT)
    if not front.get('Internal') or front.get('Driver')!='bridge': raise RuntimeError('frontend must be internal bridge')
    for network in networks:
        n=info('network',network['ID'])
        for ipam in n.get('IPAM',{}).get('Config') or []:
            if ipam.get('Subnet') and ipaddress.ip_network(SUBNET).overlaps(ipaddress.ip_network(ipam['Subnet'])): raise RuntimeError('backend subnet overlap')
    for role,im in PINS['images'].items():
        # Immutable reference must already be registered in the private daemon.
        x=info('image',runtime_image(role))
        if x['Id']!=im['config_digest'] or x['Os']!='linux' or x['Architecture']!='amd64': raise RuntimeError('image identity mismatch')
        expected={'/var/lib/mysql'} if role=='db' else set()
        if set(x['Config'].get('Volumes') or {})!=expected: raise RuntimeError('unexpected inherited volumes')

def verify_container(role):
    x=info('container',DB if role=='db' else WEB); h=x['HostConfig']
    if not owned(x) or not x['State']['Running']: raise RuntimeError('ownership/running check failed')
    if h.get('Privileged') or h.get('PidMode')=='host' or h.get('NetworkMode')=='host' or h.get('PortBindings') or h.get('Binds'): raise RuntimeError('unsafe host exposure')
    if not h['ReadonlyRootfs'] or h['RestartPolicy']['Name']!='no' or 'ALL' not in h['CapDrop'] or not any(v.startswith('no-new-privileges') for v in h['SecurityOpt']): raise RuntimeError('hardening missing')
    if h.get('CapAdd') or h['PidsLimit']!=160 or h['NanoCpus']!=750000000 or not h['Memory']: raise RuntimeError('resource/capability mismatch')
    if any(m['Type']!='tmpfs' for m in x.get('Mounts',[])): raise RuntimeError('unexpected persisted or host mount')
    expected={BACK} if role=='db' else {BACK,FRONT}
    if set(x['NetworkSettings']['Networks'])!=expected: raise RuntimeError('unexpected network attachment')
    if x['Image']!=PINS['images'][pinned_role(role)]['config_digest']: raise RuntimeError('running image mismatch')

PHP_HTTP=r'''$q=json_decode(stream_get_contents(STDIN),true);$h="Connection: close\r\n";if($q['cookie'])$h.="Cookie: ".$q['cookie']."\r\n";if($q['body']!==null)$h.="Content-Type: application/x-www-form-urlencoded\r\n";$c=stream_context_create(['http'=>['method'=>$q['body']===null?'GET':'POST','header'=>$h,'content'=>$q['body']??'','follow_location'=>0,'ignore_errors'=>true,'timeout'=>8]]);$b=file_get_contents('http://127.0.0.1/'.$q['path'],false,$c);if($b===false)exit(2);echo json_encode(['headers'=>$http_response_header,'body'=>$b]);'''

def request(path,cookies,body=None):
    payload=json.dumps(dict(path=path,cookie='; '.join(k+'='+v for k,v in cookies.items()),body=body))
    r=json.loads(docker('exec','-i',WEB,'php','-r',PHP_HTTP,data=payload,timeout=15).stdout)
    for h in r['headers']:
        if h.lower().startswith('set-cookie:'):
            k,v=h.split(':',1)[1].strip().split(';',1)[0].split('=',1); cookies[k]=v
    status=int(r['headers'][0].split()[1])
    if status not in (200,302,303): raise RuntimeError('unexpected HTTP status '+str(status))
    return r

def token(body):
    match=re.search(r'name=[\'"]user_token[\'"][^>]*value=[\'"]([^\'"]+)',body)
    if not match: raise RuntimeError('actual HTTP form has no CSRF token')
    return match[1]

def health_setup():
    cookies={}
    r=request('setup.php',cookies)
    if 'Database Setup' not in r['body'] or 'PHPSESSID' not in cookies: raise RuntimeError('setup/session check failed')
    request('setup.php',cookies,urllib.parse.urlencode({'create_db':'Create / Reset Database','user_token':token(r['body'])}))
    r=request('setup.php',cookies)
    if 'Setup successful' not in r['body']: raise RuntimeError('HTTP database setup did not succeed')
    # Check real persisted SQL records via the actual DB container, not a mock.
    sql="SELECT COUNT(*) FROM dvwa.users; SELECT COUNT(*) FROM dvwa.users WHERE user='admin' AND password=MD5('password'); SELECT COUNT(*) FROM dvwa.guestbook;"
    result=docker('exec',DB,'mariadb','--user=dvwa','--password=p@ssw0rd','--batch','--skip-column-names','-e',sql).stdout.split()
    if result!=['5','1','1']: raise RuntimeError('actual SQL seed verification failed')
    r=request('login.php',cookies)
    request('login.php',cookies,urllib.parse.urlencode({'username':'admin','password':'password','Login':'Login','user_token':token(r['body'])}))
    r=request('index.php',cookies)
    if 'Welcome to Damn Vulnerable Web Application' not in r['body'] or 'Logout' not in r['body']: raise RuntimeError('authenticated HTTP page missing')
    print('VERIFIED: HTTP setup with session/CSRF, SQL users=5/admin=1/guestbook=1, authenticated HTTP homepage',flush=True)

def stop_owned():
    global DEADLINE
    DEADLINE=None
    errors=[]
    for name in (WEB,DB):
        try:
            if exists('container',name,timeout=3):
                if not owned(info('container',name,timeout=3)): raise RuntimeError('refuse stop: ownership mismatch')
                docker('stop','--time','8',name,timeout=12)
                if info('container',name,timeout=3)['State']['Running']: raise RuntimeError('stop not confirmed')
        except (RuntimeError,subprocess.TimeoutExpired) as error:
            errors.append(name+': '+str(error))
    if errors: raise RuntimeError('stop verification failed: '+'; '.join(errors))
    print('STOPPED: exact owned containers only; no resources removed',flush=True)

def main():
    global DEADLINE, USE_CONFIG_IDS
    p=argparse.ArgumentParser();p.add_argument('--action',choices=['plan','install','stop'],default='plan');p.add_argument('--deadline-epoch',type=int);p.add_argument('--use-config-ids',action='store_true',help='Explicit offline tar-import mode; parent must verify tar provenance against pins.json');a=p.parse_args()
    USE_CONFIG_IDS=a.use_config_ids
    if a.action=='plan':
        print(json.dumps({'socket':HOST,'backend_subnet':SUBNET,'web':run_args('web'),'db':run_args('db')},indent=2));return
    if a.action=='stop': stop_owned();return
    now=time.time()
    if not a.deadline_epoch or not now+180<a.deadline_epoch<=now+1800: raise SystemExit('absolute parent-approved deadline required (180..1800 seconds remaining)')
    DEADLINE=a.deadline_epoch
    for sig in (signal.SIGTERM,signal.SIGHUP):
        signal.signal(sig,lambda *_: (_ for _ in ()).throw(SystemExit('stop signal')))
    preflight()
    try:
        docker('network','create','--driver','bridge','--internal','--subnet',SUBNET,'--label',LABEL,BACK)
        n=info('network',BACK)
        if not owned(n) or not n['Internal']: raise RuntimeError('backend verification failed')
        for role in ('db','web'):
            args=run_args(role);validate_args(args);docker(*args)
        docker('network','connect','--alias','dvwa-target',FRONT,WEB)
        verify_container('db');verify_container('web')
        # Wait only for DB initialization and HTTP readiness. Setup/reset is performed exactly once.
        for i in range(30):
            if time.time()>=a.deadline_epoch-60: raise RuntimeError('deadline before readiness')
            try:
                docker('exec',DB,'mariadb','--user=dvwa','--password=p@ssw0rd','--batch','--skip-column-names','-e','SELECT 1',timeout=5)
                request('setup.php',{});break
            except (RuntimeError,subprocess.TimeoutExpired): time.sleep(2)
        else: raise RuntimeError('target readiness timed out')
        health_setup()
        print('READY privately: http://dvwa-target/ from existing application network. Foreground guard must remain alive.',flush=True)
        while time.time()<a.deadline_epoch-60: time.sleep(min(1,max(0,a.deadline_epoch-60-time.time())))
    finally: stop_owned()

if __name__=='__main__': main()
