"""Trusted literal probes: synthetic data only; never model input or findings."""
import json
import shlex

def command(code):return 'python3 -c '+shlex.quote(code)

CONFINEMENT=r'''
import os,json,socket
s=dict(x.split(':',1) for x in open('/proc/self/status') if ':' in x)
assert os.getuid()==1001 and os.getgid()==1002
assert all(int(s[k].strip(),16)==0 for k in ('CapEff','CapPrm','CapBnd'))
assert s['NoNewPrivs'].strip()=='1'
assert os.statvfs('/').f_flag & os.ST_RDONLY
assert set(os.listdir('/sys/class/net'))=={'lo'}
assert all(x.split()[1]=='00000000' for x in list(open('/proc/net/route'))[1:])
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'caps':{k:s[k].strip() for k in ('CapEff','CapPrm','CapBnd')},'nnp':s['NoNewPrivs'].strip(),'root_readonly':bool(os.statvfs('/').f_flag & os.ST_RDONLY),'interfaces':os.listdir('/sys/class/net'),'pid_ns':os.readlink('/proc/self/ns/pid'),'ipc_ns':os.readlink('/proc/self/ns/ipc'),'net_ns':os.readlink('/proc/self/ns/net')}))
'''
APPDATA=r'''
import os,errno,json
assert os.path.isdir('/app/data') and os.listdir('/app/data')==[]
assert os.statvfs('/app/data').f_flag & os.ST_RDONLY
try: os.open('/app/data/new-canary',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
except OSError as e: assert e.errno==errno.EROFS; n=e.errno
else: raise AssertionError('unexpected write')
print(json.dumps({'errno':n,'entries':os.listdir('/app/data'),'readonly':True}))
'''
ABSENCE=r'''
import os,json
paths=['/var/run/docker.sock','/run/docker.sock','/control.sock','/native.key','/artex-public-host-private-canary']
assert all(not os.path.exists(p) for p in paths)
assert 'ARTEX_HOST_PUBLIC_CANARY' not in os.environ
assert not any(k in os.environ for k in ('OPENAI_API_KEY','DATABASE_URL','PGPASSWORD','HTTPS_PROXY','ALL_PROXY'))
assert not any('/artex-canary-' in x or 'docker.sock' in x or 'native.key' in x for x in open('/proc/self/mountinfo'))
print(json.dumps({'absent_paths':paths,'host_public_env_absent':True,'forbidden_mounts':[]}))
'''
QUOTA=r'''
import os,errno,json,time,sys,stat
names=[];n=0;enospc=False;end=time.monotonic()+4
try:
 for i in range(20):
  assert time.monotonic()<end
  name='/work/canary-fill-%02d'%i
  with open(name,'xb',buffering=0) as f:
   owned=os.fstat(f.fileno());names.append((name,owned.st_dev,owned.st_ino))
   for j in range(7):
    b=b'x'*1048576
    while b:
     w=f.write(b);n+=w;b=b[w:]
except OSError as e:
 if e.errno!=errno.ENOSPC:raise
 enospc=True
finally:
 original_error=sys.exc_info()[0];cleanup_errors=[]
 for name,dev,ino in names:
  try:
   s=os.stat(name,follow_symlinks=False)
   if not stat.S_ISREG(s.st_mode) or (s.st_dev,s.st_ino)!=(dev,ino):raise RuntimeError('filler replaced; refusing unlink')
   os.unlink(name)
  except FileNotFoundError:pass
  except BaseException as e:cleanup_errors.append(e)
 if cleanup_errors and original_error is None:raise cleanup_errors[0]
assert enospc and n<67108864 and n>50331648
assert os.statvfs('/work').f_blocks*os.statvfs('/work').f_frsize==67108864
print(json.dumps({'enospc':enospc,'bytes_written':n,'remaining_fillers':[x for x in os.listdir('/work') if x.startswith('canary-fill-')],'capacity':67108864}))
'''
FIFO=r'''
import os,json
os.mkfifo('/work/canary-fifo',0o600)
print(json.dumps({'fifo_created':True}))
'''
SETSID="setsid sh -c 'sleep 60' >/dev/null 2>&1 & printf '%s\\n' '{\"setsid_spawned\":true}'"

def http_probe(origin,port):
 return command('''import os,json,socket,urllib.request,urllib.error
origin=%r
proxy=os.environ['http_proxy']
opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy}))
# The frozen helper ReverseProxy adds X-Forwarded-For, which the frozen
# gateway rejects. Direct-UDS positives are independently useful; proxy-path
# acceptance is an explicitly unimplemented blocking gate, not credited here.
responses=[]
for method in ('GET','HEAD'):
 s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect('/fixture/gateway.sock')
 s.sendall((method+' / HTTP/1.1\\r\\nHost: '+origin.split('://')[1]+'\\r\\nConnection: close\\r\\n\\r\\n').encode())
 chunks=[]
 while True:
  b=s.recv(4096)
  if not b:break
  chunks.append(b)
 data=b''.join(chunks);assert data.startswith(b'HTTP/1.1 200')
 responses.append({'method':method,'status':200,'bytes':len(data)});s.close()
negative=[]
for method,target,host in [('POST','/',origin.split('://')[1]),('CONNECT','/',origin.split('://')[1]),('GET','http://off-origin.invalid/','off-origin.invalid')]:
 s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect('/fixture/gateway.sock')
 s.sendall((method+' '+target+' HTTP/1.1\\r\\nHost: '+host+'\\r\\nConnection: close\\r\\n\\r\\n').encode())
 data=s.recv(8192);assert data.startswith(b'HTTP/1.1 502');s.close();negative.append({'method':method,'status':502})
s=socket.socket();s.settimeout(.3)
try:s.connect(('127.0.0.1',%d))
except OSError as e:direct_errno=e.errno
else:raise AssertionError('owned upstream directly reachable')
finally:s.close()
print(json.dumps({'proxy':proxy,'responses':responses,'denied':negative,'direct_owned_errno':direct_errno}))
'''%(origin,port))

def environment_proxy(origin):
 return command('''import os,json,urllib.request
origin=%r
proxy=os.environ['http_proxy']
# Explicit ProxyHandler plus empty bypass list: localhost must use the helper.
os.environ['no_proxy']='';os.environ['NO_PROXY']=''
opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy}))
responses=[]
for method in ('GET','HEAD'):
 with opener.open(urllib.request.Request(origin+'/',method=method),timeout=2) as r:
  body=r.read(4096);assert r.status==200
  if method=='HEAD':assert body==b''
  responses.append({'method':method,'status':r.status,'bytes':len(body)})
print(json.dumps({'environment_proxy':True,'responses':responses}))
'''%(origin,))

def requests(origin,port,host_paths=()):
 absence=ABSENCE.replace('assert all(not os.path.exists(p) for p in paths)','paths += '+repr(list(host_paths))+'\nassert all(not os.path.exists(p) for p in paths)')
 return [('confinement','Bash',{'command':command(CONFINEMENT)},'json'),('app-data','Bash',{'command':command(APPDATA)},'json'),('host-absence','Bash',{'command':command(absence)},'json'),('fixture-http','Bash',{'command':http_probe(origin,port)},'json'),('quota-enospc','Bash',{'command':command(QUOTA)},'json'),('setsid-success','Bash',{'command':SETSID},'json'),('timeout-setsid','Bash',{'command':"setsid sh -c 'sleep 60' >/dev/null 2>&1 & sleep 60",'timeout_ms':1000},'error-or-outer-timeout'),('fifo-create','Bash',{'command':command(FIFO)},'json'),('fifo-read','Read',{'file_path':'/work/canary-fifo'},'outer-timeout')]

def facts(result, expected):
 if not isinstance(result,dict) or type(result.get('version')) is not int or result.get('version')!=1:raise ValueError('result envelope')
 r=result['result']
 if expected=='error':
  if r['IsError'] is not True:raise ValueError('expected tool error')
  return {'tool_error':True,'text':[c.get('text','')[:4096] for c in r['Content']]}
 if r['IsError'] is not False:raise ValueError('unexpected tool error')
 texts=[c['text'] for c in r['Content'] if c.get('type')=='text']
 # SDK Bash text includes command/exit metadata: locate exactly one JSON fact line.
 objects=[]
 for text in texts:
  for line in text.splitlines():
   try:v=json.loads(line)
   except ValueError:continue
   if isinstance(v,dict):objects.append(v)
 if len(objects)!=1:raise ValueError('one structured fact object required')
 return objects[0]
