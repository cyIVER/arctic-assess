import importlib.util,json,os,pathlib,subprocess,sys,tempfile,time,hashlib,shutil,threading,re,traceback
E=pathlib.Path(__file__).resolve().parent
R=E.parent/'source';ROOT=E.parents[2];SCR=pathlib.Path('/home/iveri/.hermes/cache/scratch')
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def pin():
 files=[p for d in ['db','intercept','config'] for p in (R/d).glob('*') if p.is_file()]+[R/'go.mod',R/'go.sum']
 # Lexical token fingerprint: retain literals atomically; ignore comments/spacing only.
 pat=re.compile(r'`[^`]*`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/|\s+|[A-Za-z_][A-Za-z_0-9]*|[^\s]',re.S)
 return {str(p.relative_to(R)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'lexical_noncomment_sha256':hashlib.sha256(json.dumps([v for v in pat.findall(p.read_text()) if not v.isspace() and not v.startswith('//') and not v.startswith('/*')],ensure_ascii=False).encode()).hexdigest() if p.suffix=='.go' else None} for p in files}
def stats(path):
 return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())

def child():
 env=dict(os.environ);env['GOFLAGS']='-mod=readonly';env['GOMAXPROCS']='2'
 dbnames=['TestOpenSeed','TestInterceptApprovalFilters','TestInterceptExecutionNavigation','TestTaskArchiveDatabaseRoundTrip','TestInterceptSourceEnglishLegacy','TestApprovalSQLRecognizesEnglishLegacy','TestRestoreApprovalEnglishLegacyEvidence','TestTaskArchiveFormatCompatibility']
 innames=['TestEnglishJudgeGeneratedReason','TestEnglishHandleAskSummaryAndCancellation','TestEnglishVerdictCompatibility','TestEnglishGeneratedDefaultsPreserveSuppliedNames','TestEnglishVerdictStrictRejections']
 commands=[([env['GOROOT']+'/bin/go','test','-p','1','-json','./db','./intercept','-run','^('+'|'.join(dbnames+innames)+')$','-count=1','-timeout=180s'],dbnames+innames,'existing'),([env['GOROOT']+'/bin/go','test','-p','1','-json',str(E/'qualification_test.go'),'-run','^TestPrivatePostgresApprovalHistoryArchive$','-count=1','-timeout=180s'],['TestPrivatePostgresApprovalHistoryArchive'],'real-sql')]
 results=[]
 for cmd,required,label in commands:
  before=pin();(E/(label+'-before-pins.json')).write_text(json.dumps(before,indent=2))
  with (E/(label+'.jsonl')).open('w') as log:
   p=subprocess.Popen(cmd,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
   started=time.monotonic()
   try:
    while p.poll() is None:
     if time.monotonic()-started>180: p.terminate();p.wait(timeout=20);raise TimeoutError('Go command 180s bound')
     if shutil.disk_usage(SCR).free<512*1024**2: p.terminate();p.wait(timeout=20);raise RuntimeError('disk below 512MiB')
     time.sleep(.3)
   finally:
    if p.poll() is None:p.terminate();p.wait(timeout=20)
  after=pin();(E/(label+'-after-pins.json')).write_text(json.dumps(after,indent=2))
  rows=[]
  for line in (E/(label+'.jsonl')).read_text().splitlines():
   try:rows.append(json.loads(line))
   except ValueError:pass
  terminal=[r for r in rows if r.get('Test') and r.get('Action') in ['pass','fail','skip']]
  names={r['Test']:r['Action'] for r in terminal}
  result={'command':cmd,'returncode':p.returncode,'top_level':{a:sum(r['Action']==a and '/' not in r['Test'] for r in terminal) for a in ['pass','fail','skip']},'subtests':{a:sum(r['Action']==a and '/' in r['Test'] for r in terminal) for a in ['pass','fail','skip']},'required':{n:names.get(n,'MISSING') for n in required},'tests':[{'name':r['Test'],'action':r['Action']} for r in terminal],'package_failures':[r for r in rows if r.get('Action')=='fail' and not r.get('Test')],'byte_drift':[k for k in before if before[k]['sha256']!=after.get(k,{}).get('sha256')],'lexical_noncomment_drift':[k for k in before if before[k]['lexical_noncomment_sha256']!=after.get(k,{}).get('lexical_noncomment_sha256')]}
  results.append(result);(E/'test-results.json').write_text(json.dumps(results,indent=2))
  if p.returncode or any(names.get(n)!='pass' for n in required) or any(r['Action']!='pass' for r in terminal):return 1
 return 0

if __name__=='__main__':
 if len(sys.argv)>1:sys.exit(child())
 os.umask(0o077)
 state=pathlib.Path(tempfile.mkdtemp(prefix='english-pg-state-',dir=SCR));sock=pathlib.Path(tempfile.mkdtemp(prefix='epg-',dir=SCR));state.chmod(0o700);sock.chmod(0o700)
 adapter=load('stable_adapter',ROOT/'artex-worker-runtime-v2/run_with_pg.py');fixture=adapter.fixture
 identities=[]
 def stable(pid):
  value=adapter.identity(pid);identities.append({'pid':pid,'uid':value[0],'start_ticks':value[1],'exe':value[2]});return value
 fixture.identity=stable
 env=json.loads((ROOT/'artex-worker-admission/receipts/p2-red-environment.json').read_text());env.update({'GOFLAGS':'-mod=readonly','GOMAXPROCS':'2','QUAL_EVIDENCE':str(E),'GOTMPDIR':str(state/'gotmp'),'TMPDIR':str(state/'gotmp')});(state/'gotmp').mkdir(mode=0o700)
 cache=pathlib.Path(env['GOCACHE']);cache_before=stats(cache);free_before=shutil.disk_usage(SCR).free
 report={'state':str(state),'socket':str(sock),'fixture':'artex-local-pg/run_with_pg.py run_session; stable adapter identity override only','identity_checks':identities,'free_before':free_before,'cache_before':cache_before,'environment':env,'started':time.time()}
 try:
  if free_before<512*1024**2:raise RuntimeError('disk headroom below 512MiB')
  report['returncode']=fixture.run_session(state,ROOT/'artex-local-pg/prefix',sock,[sys.executable,str(E/'run.py'),'child'],300,env)
 except BaseException as e:
  report['error']=repr(e);report['traceback']=traceback.format_exc()
 finally:
  if (state/'last-run.json').exists():report['closure']=json.loads((state/'last-run.json').read_text());report['closure'].pop('dsn',None)
  report.update({'pidfile_absent':not (state/'data/postmaster.pid').exists(),'socket_entries':[p.name for p in sock.iterdir()],'owned_pid_proc_absent':all(not pathlib.Path('/proc',str(x['pid'])).exists() for x in identities),'fixture_bytes':stats(state),'new_cache_bytes':stats(cache)-cache_before,'free_after':shutil.disk_usage(SCR).free,'finished':time.time()})
  report['bounds_ok']=report['fixture_bytes']<=150*1024**2 and report['new_cache_bytes']<=100*1024**2 and report['free_after']>=512*1024**2
  (E/'run-receipt.json').write_text(json.dumps(report,indent=2))
  if (state/'postgres.log').exists():shutil.copyfile(state/'postgres.log',E/'postgres.log')
  print(json.dumps(report,indent=2))
 sys.exit(report.get('returncode',1))
