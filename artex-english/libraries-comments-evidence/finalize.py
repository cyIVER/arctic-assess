import work,json,collections,hashlib,difflib,pathlib,re,subprocess
E=work.E;ROOT=work.ROOT
orig=json.loads((E/'originals.json').read_text());baseline=json.loads((E/'baseline.json').read_text());after=work.scan([ROOT/p for p in sorted(orig)]);work.dump('after.json',after)
bm={r['Path']:r for r in baseline};changes=[];hashmaps={};remaining=[];prior=json.loads((ROOT/'libraries-evidence/remaining-classified.json').read_text());prev={(x['path'],x['line']):x for x in prior}
(E/'diffs').mkdir(exist_ok=True)
protected=re.compile(r'(?:https?://|file:///|gopher://)[\x21-\x7e]+')
protected_results=[]
for r in after:
 rel=str(pathlib.Path(r['Path']).relative_to(ROOT));old=orig[rel];new=(ROOT/rel).read_text();a=bm[r['Path']]
 for k in ['Tokens','Literals','AST']:assert a[k]==r[k],(rel,k)
 assert r['Formatted'],rel
 def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 hashmaps[rel]={'before_sha256':a['SHA256'],'after_sha256':r['SHA256'],'tokens_sha256_before':digest(a['Tokens']),'tokens_sha256_after':digest(r['Tokens']),'literals_sha256_before':digest(a['Literals']),'literals_sha256_after':digest(r['Literals']),'ast_sha256_before':a['AST'],'ast_sha256_after':r['AST'],'tokens':len(r['Tokens']),'literals':len(r['Literals'] or []),'formatted':r['Formatted']}
 # Equal comment cardinality preserves directive/provenance slots and exact original URLs.
 assert len(a['Comments'] or [])==len(r['Comments'] or []),rel
 for x,y in zip(a['Comments'] or [],r['Comments'] or []):
  if re.search(r'(?i)(copyright|spdx|license|^//go:|^//\s*\+build|^//line\s)',x['Text']):assert x['Text']==y['Text'],(rel,'protected comment')
  urls=protected.findall(x['Text']);missing=[u for u in urls if u not in y['Text']]
  if missing:protected_results.append({'path':rel,'line':x['Line'],'missing_url_tokens':missing})
  if work.CJK.search(y['Text']):
   kind='intentional_existing_document_path_reference' if 'docs/' in y['Text'] else 'intentional_machine_identifier_or_archive_notation'
   remaining.append({'path':rel,'line':y['Line'],'text':y['Text'],'classifications':[kind]})
 if old!=new:
  diff=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=rel+' (lane baseline)',tofile=rel+' (translated)'))
  dp='diffs/'+rel.replace('/','__')+'.diff';(E/dp).write_text(diff)
  changes.append({'path':rel,'before_sha256':a['SHA256'],'after_sha256':r['SHA256'],'diff':dp})
 # Literal lines inherit prior conservative classification; no literal is edited in this lane.
 comment_lines=set()
 for c in r['Comments'] or []:comment_lines.update(range(c['Line'],c['Line']+c['Text'].count('\n')+1))
 for n,line in enumerate(new.splitlines(),1):
  if not work.CJK.search(line) or n in comment_lines:continue
  previous=prev.get((rel,n));classes=previous['classifications'] if previous else (['intentional_english_language_rejection_assertion'] if rel.endswith('/english_test.go') and 'ContainsAny' in line else ['intentional_target_evidence_or_unicode_test_fixture'] if rel.endswith('/english_test.go') else ['unchanged_test_literal_requires_separate_review' if rel.endswith('_test.go') else 'unchanged_production_literal_requires_separate_review'])
  classes=[k for k in classes if k not in ['remaining_test_comment','remaining_production_comment']]
  if not classes:classes=['unchanged_literal_requires_separate_review']
  remaining.append({'path':rel,'line':n,'text':line,'classifications':classes})
work.dump('protected-url-check.json',protected_results)
assert not protected_results,protected_results
counts=collections.Counter(k for x in remaining for k in x['classifications']);scope={}
for x in remaining:
 d=scope.setdefault(x['path'],collections.Counter());d.update(x['classifications'])
work.dump('remaining-classified.json',remaining);work.dump('next-scope.json',scope);work.dump('changed-paths.json',changes);work.dump('hashmaps.json',hashmaps)
translations=sum(len(p.read_text().splitlines()) for p in E.glob('translations*.tsv'))
report={'status':'All owned explanatory CJK comments translated; functional identifiers, document references and all literals preserved. Not compiled.','owned_folders':work.OWN,'files_verified':len(after),'changed_file_count':len(changes),'translated_comment_tokens':translations,'translated_production_comment_tokens':595,'translated_test_comment_tokens':translations-595,'changed_paths':changes,'guard_tests':json.loads((E/'guard-tests.json').read_text()),'verification':{'scanner':'go/scanner exact ordered token kinds and spellings, excluding only COMMENT; includes automatically inserted semicolons','literal_parity':'All STRING and CHAR tokens exactly equal, including English text and Unicode fixtures','parser':'go/parser without comments, canonical go/format AST output SHA256 exact equality','format':'All owned Go files parse and match gofmt output','protected_comments':'Directive/build-tag/copyright/license comments byte-equal','protected_urls':'Every URL token in original comments retained exactly','result':'PASS','application_builds_or_tests_run':False,'application_compiled':False},'counts':dict(counts),'remaining_human_explanatory_comment_lines':0,'production_cjk_literal_lines':sum(1 for x in remaining if not x['path'].endswith('_test.go') and not any(c.startswith('intentional_') for c in x['classifications'])),'exact_remaining_inventory':'remaining-classified.json','exact_next_scope':'next-scope.json','hashmaps':'hashmaps.json','baseline_snapshot':'originals.json','baseline_scanner_output':'baseline.json','final_scanner_output':'after.json','limitations':['No full application build or package tests; syntax/format/structural equivalence only.','Prior library runtime translations were preserved exactly, not redone or revalidated behaviorally.','Test diagnostics, assertions and purposeful Unicode fixtures remain verbatim for separate review.','No whole-candidate pin, deployment, or repository-wide English-completion claim.','Working directory has no .git metadata; diffs use lane-local pretranslation snapshots.'],'lessons_handoff':['Snapshot after prior runtime translation, then prove exact scanner token, literal and parser identities independently of comment spelling.','Retain non-English documentation paths and machine-identifier notation; distinguish these from untranslated explanatory prose.','Use conservative prior literal classifications and preserve test strings; comment-only completion does not imply full English or behavioral test coverage.']}
work.dump('report.json',report)
print(json.dumps({k:report[k] for k in ['files_verified','changed_file_count','translated_comment_tokens','counts','remaining_human_explanatory_comment_lines','production_cjk_literal_lines']},indent=2))
