import pathlib,json,hashlib,gzip,datetime,shutil,os
R=pathlib.Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation')
O=R/'coordination-20261119/gate-app-readiness-retry'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads((R/p).read_text())
def verify(name,manifest,root):
 m=load(manifest); base=R/root; actual={}; missing=[]; unsafe=[]
 for k in m:
  p=base/k
  if p.is_symlink():unsafe.append(k)
  elif p.is_file():actual[k]=sha(p)
  else:missing.append(k)
 extras=[]
 for dp,dn,fn in os.walk(base,followlinks=False):
  dn[:]=[d for d in dn if d not in ['.git','node_modules','gocache','__pycache__']]
  for f in fn:
   k=str((pathlib.Path(dp)/f).relative_to(base))
   if k not in m:extras.append(k)
 return {'name':name,'manifest':manifest,'root':root,'declared_count':len(m),'verified_count':sum(actual.get(k)==v for k,v in m.items()),'missing':missing,'unsafe_symlinks':unsafe,'changed':[k for k in actual if actual[k]!=m[k]],'extra_paths':extras,'manifest_pin':hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'manifest_file_sha256':sha(R/manifest)}
checks=[verify('admission','artex-worker-admission/source-manifest.json','artex-worker-admission/source'),verify('operational baseline','artex-worker-admission/baseline-source-manifest.json','artex-worker-operational/source')]
a=load('artex-worker-admission/source-manifest.json');b=load('artex-worker-admission/baseline-source-manifest.json')
delta={'added':sorted(a.keys()-b.keys()),'removed':sorted(b.keys()-a.keys()),'modified':sorted(k for k in a.keys()&b.keys() if a[k]!=b[k]),'unchanged':sum(a[k]==b[k] for k in a.keys()&b.keys())}
u=load('artex-ui-asset-final/source-inventory.json'); print('UI inventory structure',type(u).__name__,list(u)[:8])
# source-inventory uses original path/hash map or wrapped map; never infer missing hashes.
um=u.get('files',u) if isinstance(u,dict) else None
if not isinstance(um,dict) or not all(isinstance(v,str) and len(v)==64 for v in um.values()):raise ValueError('Unexpected asset manifest')
assets=R/'artex-ui-asset-final/assets'; mismatches=[];total=0
for k,v in um.items():
 p=assets/k
 if not p.is_file() or p.is_symlink() or sha(p)!=v:mismatches.append(k)
 else:total+=p.stat().st_size
actual_ui=sorted(str(p.relative_to(assets)) for p in assets.rglob('*') if p.is_file())
ui={'root':str(assets),'declared_count':len(um),'verified_count':len(um)-len(mismatches),'mismatches':mismatches,'extra_files':sorted(set(actual_ui)-um.keys()),'total_bytes':total,'canonical_pin':hashlib.sha256(json.dumps(um,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
receipt=load('artex-ui-asset-final/local-build-receipt.json'); binary=[]
for name,v in receipt['binaries'].items():
 p=pathlib.Path(v['path']); rec={'name':name,'receipt_sha256':v['sha256'],'path':str(p),'exists_now':p.is_file()}
 # Do not follow volatile production symlink beyond task root.
 if p.is_file() and not any(q.is_symlink() for q in [p,*list(p.parents)[:2]]):rec['actual_sha256']=sha(p)
 if 'durable_compressed_artifact' in v:
  d=v['durable_compressed_artifact'];p=pathlib.Path(d['path']);h=hashlib.sha256();n=0
  with gzip.open(p,'rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);n+=len(chunk)
  rec.update({'compressed_actual_sha256':sha(p),'compressed_receipt_sha256':d['sha256'],'streamed_uncompressed_sha256':h.hexdigest(),'uncompressed_bytes':n,'matches_receipt':h.hexdigest()==v['sha256']})
 binary.append(rec)
parse_errors=[]
for p in ['artex-ui-asset-final/report.json','artex-ui-asset-final/session-result.json','artex-worker-assessment-runner/runner-source-manifest.json']:
 try:load(p)
 except Exception as e:parse_errors.append({'path':p,'error':str(e),'bytes':(R/p).stat().st_size,'sha256':sha(R/p)})
report={'snapshot_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'local_only':True,'activation_authorized':False,'verdict':'HOLD_RUNTIME_QUALIFICATION','disk_free_bytes':shutil.disk_usage(R).free,'source_checks':checks,'source_delta':delta,'assets':ui,'binaries':binary,'parse_errors':parse_errors}
(O/'snapshot-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
