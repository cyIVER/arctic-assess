import json, re, hashlib, difflib, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
E=ROOT/'agent-final-evidence'
base=json.loads((E/'baseline.json').read_text())
current={str(p.relative_to(ROOT)):p.read_text() for folder in ['agent','guard'] for p in (ROOT/'source'/folder).glob('*.go')}
hashof=lambda s:hashlib.sha256(s.encode()).hexdigest()
changed={p:s for p,s in current.items() if base.get(p)!=s}
diff=''.join(''.join(difflib.unified_diff(base.get(p,'').splitlines(True),s.splitlines(True),fromfile='before/'+p,tofile='after/'+p)) for p,s in sorted(changed.items()))
(E/'translation.diff').write_text(diff)
(E/'hashes.json').write_text(json.dumps({'baseline_sha256':{p:hashof(s) for p,s in sorted(base.items())},'final_sha256':{p:hashof(s) for p,s in sorted(current.items())},'changed_paths':list(sorted(changed))},indent=2))
remaining=[]
for p,s in sorted(current.items()):
 for n,line in enumerate(s.splitlines(),1):
  if not re.search('[\u3400-\u9fff]',line):continue
  if 'docs/' in line:
   c='functional_document_path';why='Actual referenced document path is an identifier, retained exactly; surrounding comment is English.'
  elif p.endswith('provider.go'):
   c='functional_multilingual_quota_detection';why='Quota detection must continue recognizing real Chinese provider errors.'
  elif p.endswith('terminalreason_test.go'):
   c='functional_unicode_evidence_fixture';why='Partial model output and rune-safe truncation fixtures must remain Unicode, not translated.'
  elif p.endswith('blackboard_inheritance_test.go'):
   c='functional_icp_registration_fixture';why='ICP registry-format test data, not generated human-facing prose.'
  elif p.endswith('provider_quota_test.go'):
   c='functional_multilingual_quota_fixture';why='Positive control for Chinese provider-quota recognition.'
  elif p.endswith('review_context_test.go'):
   c='functional_user_target_evidence_fixture';why='Original task instructions, constraints and forbidden-context markers test isolation; do not translate user/evidence data.'
  elif p.endswith('_test.go'):
   c='functional_unicode_override_fixture';why='User/custom template override and Unicode budget fixture; original supplied content must remain unchanged.'
  else:
   c='remaining_untranslated';why='Needs follow-up.'
  remaining.append(dict(path=p,line=n,text=line,classification=c,rationale=why))
(E/'remaining-nonenglish.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2))
old=json.loads((ROOT/'agent-evidence/remaining-nonenglish.json').read_text())
reconcile=[]
for row in old:
 p='source/'+row['path'];present=row['text'] in current.get(p,'').splitlines()
 reconcile.append(dict(prior_path=row['path'],prior_line=row['line'],prior_classification=row['classification'],prior_text=row['text'],exact_original_line_retained=present,status='retained; see new functional classification' if present else 'translated or same-meaning expectation updated'))
(E/'prior-classification-reconciliation.json').write_text(json.dumps(reconcile,ensure_ascii=False,indent=2))
tests={p.stem:json.loads(p.read_text()) for p in E.glob('*.json') if p.stem in ['english-red','english-green','focused','final-safe','side-safe','final-verified']}
for label in tests:
 events=[]
 for l in (E/(label+'.jsonl')).read_text().splitlines():
  try:events.append(json.loads(l))
  except:pass
 tests[label]['failure_output']=[x for x in events if x.get('Action')=='output' and ('FAIL' in x.get('Output','') or ('_test.go:' in x.get('Output','') and label!='english-red'))]
 tests[label]['skip_output']=[x for x in events if x.get('Action')=='skip' or (x.get('Action')=='output' and ('Skip' in x.get('Output','') or 'no database' in x.get('Output','') or 'no test database' in x.get('Output','') or 'unavailable' in x.get('Output','') and 'test.go:' in x.get('Output','')))]
structure=json.loads((E/'structure.json').read_text())
report=dict(status='Owned agent/guard English generated prose and comment translation complete; build and independent review pending',changed_paths=list(sorted(changed)),changed_path_count=len(changed),new_test='source/agent/english_tools_final_test.go',ownership='Only source/agent/** modified; source/guard/** preserved. New agent-final-evidence/** receipts; prior reports untouched.',accomplished=['English descriptions and nested argument documentation across all 25 domain tool catalog seeds. Machine tool names, keys, schema structure, required fields and enum values preserved.','English tool refusals/errors, exploration write summaries, coverage hints, trace help, terminal/cancellation explanations, provider diagnostics and connection-test wording.','English retester and graph-compression prompts with original evidence thresholds, scope restrictions, output protocol and budgets retained. Original eight already-translated role bodies were not rewritten.','Translated remaining explanatory comments; actual non-English document paths retained as identifiers.','Kept Unicode user content, evidence fixtures, template overrides, ICP data and quota detection. Updated only matching legacy expected prose without dropping assertions.'],tests=tests,production_structure_check={k:v for k,v in structure.items() if k!='literal_changes'},nonenglish_remaining=dict(counts_by_classification=dict(collections.Counter(x['classification'] for x in remaining)),total_lines=len(remaining),untranslated_production_or_comments=[x for x in remaining if x['classification']=='remaining_untranslated'],inventory='remaining-nonenglish.json',prior_reconciliation='prior-classification-reconciliation.json'),artifacts=dict(hashes='hashes.json',diff='translation.diff',baseline='baseline.json',structure='structure.json'),limits=['No full application build, deployment, UI activation, model-enabled test, migration or independent natural-language/security review.','Final-safe and side-safe are focused offline regressions, not database persistence or end-to-end proof. PostgreSQL-dependent cases in the earlier broad run skipped; no database was provisioned.','Intermediate focused run failed six existing terminal tests: five old Chinese message assertions, plus the existing 40-rune short-label limit. Updated only translated expectations, shortened English labels to retain that limit, then passed final-safe.','Scope deviation: the initial focused regex was too broad and selected TestNativeRPCSyntheticNoTarget and TestCapturePropagatesThroughNormaProvider, whose existing tests start transient local httptest loopback listeners. Both returned; tests use deferred Close and the test process exited. No external provider/model endpoint was called. Final-safe explicitly excludes listener-bearing and native tests.','Go package compilation/tests used the retained toolchain/cache, GOPROXY=off, GOSUMDB=off, GOTOOLCHAIN=local, readonly modules. No dependencies installed/downloaded, no whole-app build. Scratch stayed under new evidence directory.','Filesystem was near full (1.5G available initially, 1.2G at last check). No disk failure or deletion occurred.'],catalog_identity_warning='Tool descriptions and schema descriptions changed, so any catalog hash/binding digest/native phase permit derived from their previous text is stale. Recompute/review identities and obtain fresh explicit approval before model-enabled UI use; do not reuse or silently remint prior approved permits. This pass did not activate or modify admission/budget/security behavior.',cross_stack_handoff=['Server must emit English Task: # context; intercept/database producer and parser compatibility for [Model] and Tool approval summaries remain owned by other workers.','source/agent/side_questions_test.go expectation aligned to already-English source/sidequestion/service.go; source/sidequestion was read only.','Existing persisted/custom prompt/tool overrides are deliberately not migrated: source English seeds do not rewrite a deployed database.'],lessons_handoff=['Inspect focused test bodies before selecting broad prefixes: offline can still start local httptest listeners, and DB skips are not passes. Use explicit listener-free test allowlists for no-listener tasks.','Translate whole natural-language literals, preserving protocol keys and multilingual evidence/detectors. Compare Go token structure and pre-existing non-Han literals separately; language scans must classify legitimate residual Unicode.','English expansion can violate existing rune limits; shorten translated labels rather than relaxing tests or limits.'])
(E/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'changed_paths':list(sorted(changed)),'remaining':report['nonenglish_remaining'],'test_counts':{k:{a:v[a] for a in ['returncode','top_level','subtests']} for k,v in tests.items()}},ensure_ascii=False,indent=2))
