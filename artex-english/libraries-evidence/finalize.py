import json,re,collections,hashlib
from pathlib import Path
from translate import ROOT
from comment_tools import TOKEN
from audit import audit
OUT=ROOT/'libraries-evidence'
changes,issues,old_inventory,runtime=audit()
classified=[]
original=json.loads((OUT/'originals.json').read_text())
for rel in original:
 f=ROOT/'source'/rel;s=f.read_text();lines=s.splitlines();types={}
 for m in TOKEN.finditer(s):
  if not re.search('[\u3400-\u9fff]',m.group()):continue
  first=s.count('\n',0,m.start())+1
  for n in range(first,first+m.group().count('\n')+1):
   if not re.search('[\u3400-\u9fff]',lines[n-1]):continue
   l=lines[n-1]
   if m.group().startswith(('//','/*')):
    kind='remaining_test_comment' if rel.endswith('_test.go') else 'remaining_production_comment'
    if 'docs/资产模型与自动关联设计.md' in l:kind='intentional_existing_document_path_reference'
   elif not rel.endswith('_test.go'):kind='remaining_production_literal'
   elif re.search(r'\bt\.(?:Errorf|Fatalf|Error|Fatal|Skip|Skipf|Logf)\(',l):kind='remaining_test_diagnostic'
   elif any(t in l for t in ['Name:', 'Summary:', 'VulnClass:', 'strings.Repeat(', '[]byte(', 'Question:', 'Answer:', 'note', 'SQL注入', '内网测试', '老数据正文', '正文 padding', '"漏洞"', '"中"']):kind='intentional_target_evidence_or_unicode_test_fixture'
   else:kind='remaining_test_literal_review'
   types.setdefault(n,[]).append(kind)
 for n,ks in sorted(types.items()):
  classified.append(dict(path='source/'+rel,line=n,text=lines[n-1],classifications=sorted(set(ks))))
(OUT/'remaining-classified.json').write_text(json.dumps(classified,ensure_ascii=False,indent=2))
counts=collections.Counter(k for x in classified for k in x['classifications'])
next_scope=collections.defaultdict(collections.Counter)
for x in classified:
 for k in x['classifications']:
  if k.startswith('remaining_'):next_scope[x['path']][k]+=1
(OUT/'next-scope.json').write_text(json.dumps({p:dict(c) for p,c in sorted(next_scope.items())},indent=2))
final_names=['libraries-verified','notify-verified','compile-leaf']
receipts={n:json.loads((OUT/(n+'.json')).read_text()) for n in final_names}
# Counts are terminal test events, not package events, independently parsed from complete JSONL.
required={'TestEnglishNotificationLabels','TestEnglishNotificationRenderersPreserveUnicodeEvidence','TestEnglishReportPreservesEvidence','TestEnglishFindingExportsRetainUnicodeData','TestEnglishUpdateDisabled','TestEnglishSideQuestionSafetyInstructions','TestEnglishTrafficSearchContract'}
seen=set(); aggregate={k:{a:0 for a in ['pass','fail','skip']} for k in ['top_level','subtests']};skip_details=[]
for n in final_names:
 for line in (OUT/(n+'.jsonl')).read_text().splitlines():
  x=json.loads(line)
  if x.get('Test') and x['Action'] in ['pass','fail','skip']:
   seen.add(x['Test']);aggregate['subtests' if '/' in x['Test'] else 'top_level'][x['Action']]+=1
  if x.get('Action')=='output' and any(t in x.get('Output','') for t in ['SKIP','not configured','database unavailable','database unavailable','ARTEX_PG_DSN','connection refused']):skip_details.append(x)
assert required<=seen,required-seen
report={'status':'production runtime strings translated; comments and test diagnostics remain (partial task completion)', 'owned_folders':'config enrich evidence llmpool llmrec mcphttp notify report selfupdate sidequestion traffic cmd'.split(), 'changed_paths':changes,'production_nonenglish_literal_scan':runtime,'nonliteral_noncomment_token_and_format_verb_issues':issues,'remaining_classification_counts':dict(counts),'exact_remaining_inventory':'remaining-classified.json','exact_next_scope':'next-scope.json','final_test_results':receipts,'aggregate_final_terminal_events':aggregate,'required_english_tests_verified':sorted(required),'limitations':['Four evidence DB tests and one llmrec DB test skipped, not passed; no PostgreSQL startup.','mcphttp/enrich compiled only; SSE listener integration not executed.','Notification live HTTP/SMTP delivery tests intentionally not executed: no listeners or external requests.','cmd/artex banner/log text changed but CLI binary not built or executed; no whole-application build.','Initial runtime-red included selfupdate/traffic test setup compile errors; corrected RED preserved separately.','Initial broad library suite failed on untranslated expectation substrings; expectations updated without changing fixtures.','A new filename regression initially expected literal # but existing sanitizer strips it; assertion corrected to existing __12.md behavior, implementation unchanged.','Tool auto-lint uses host Go/outside-module context and reports missing symbols/modules; authoritative cached offline Go test receipts are separate.','No claim of universal non-English removal: production comments, test comments/diagnostics and conservative test-literal review remain.'], 'pin_review_required':['All new source SHA256 values are in changed-paths.json; per-file unified diffs are in diffs/.','traffic/traffic.go TrafficSearchDescription and tool property/help descriptions changed; regenerate/review native catalog source pins and candidate source manifest before integration build/admission.','Do not reuse any old binary validation claim; this lane only ran focused cached offline package tests.'], 'lessons_handoff':['Translate exact literal units before generic nouns to avoid partially translated sentences; scan lexical literals afterward.','Use Go-aware lexical separation so comment translation cannot edit URLs or raw templates; verify nonliteral token identity and format verbs.','Keep multilingual target evidence and Unicode fixtures verbatim; assert generated renderer labels independently.','Record full Go JSONL and split top/subtest PASS/FAIL/SKIP; package success can conceal database skips.','Preserve security explanations and budgets in prompts; translate tool-disabled instructions without changing execution or request controls.']}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(OUT/'skip-details.json').write_text(json.dumps(skip_details,indent=2))
review=f'''# ARTEX library English translation — partial completion

## Outcome
- Translated all detected CJK human runtime literals in the owned production folders: errors/logs/config provenance, LLM failover, notification labels/buttons/templates, report Markdown/CSV, updater phases/errors, side-question prompts, traffic tool descriptions/output and CLI banner/log text.
- Lexical audit found **no remaining CJK/fullwidth production string literals** and **no nonliteral/noncomment token or format-verb changes** against this lane's original snapshot. This is a scope-local lexical claim, not universal language certification.
- Changed **{len(changes)} source paths**. See `changed-paths.json` for before/after SHA256 pins and `diffs/` for individual patches. Other owners' folders, frozen baseline/inventory, UI and root documents were not changed.

## Actual verification
Final independent Go JSONL terminal-event totals: **{aggregate['top_level']['pass']} top-level PASS, {aggregate['top_level']['fail']} FAIL, {aggregate['top_level']['skip']} SKIP; {aggregate['subtests']['pass']} subtest PASS, {aggregate['subtests']['fail']} FAIL, {aggregate['subtests']['skip']} SKIP**.
- `libraries-verified.json[l]`: eight package suites; 104 top PASS, 5 top SKIP; 23 sub PASS.
- `notify-verified.json[l]`: selected no-listener notification render/validation/masking/signature/escaping tests; 59 top PASS, 38 sub PASS.
- `compile-leaf.json[l]`: enrich/mcphttp compile-only (`-run '^$'`); zero executed tests, not behavioral acceptance.
- Seven English contract/regression tests are verified present. First label/report/safety/update/traffic RED receipts predate implementation. Renderer/CSV/filename additions are later regression coverage, not claimed test-first RED.
- Earlier failed/setup receipts are retained, not overwritten. See report.json limitations.
- Four evidence tests and one llmrec usage test skipped for unavailable DB. No PostgreSQL was started; skipped SQL effects are **unqualified**, not PASS. See `skip-details.json`.
- No network downloads/global installations, model calls, full application build, CLI execution, listener-backed integrations or native admission performed. Existing notification transport tests requiring listeners were excluded, and mcphttp SSE test was not run.

## Remaining language / exact next scope
This is **not all-language completion**. `remaining-classified.json` contains exact path/line/text/classification rows; `next-scope.json` groups every remaining translation/review class by file. Counts (classes may share a line):
'''+''.join(f'- {k}: {v}\n' for k,v in sorted(counts.items()))+'''
Priority next: remaining production comments in notify/{http,mask,markdown,render,email,dingtalk,feishu,telegram,wecom,webhook,filter,html}.go and selfupdate/{bootstrap,stage,selfupdate,github}.go; traffic recovery comments; then test comments/diagnostics and conservative test-literal review. Preserve intentional multilingual target/evidence/Unicode fixtures, document path identifiers, proper names and protocol/config identifiers.

## Integration gate
Traffic tool catalog prose changed. Regenerate/review native catalog/source pins and a new candidate source manifest before an integrated build/admission. Do not reuse old binary claims. Do not weaken security, tool-disabled side-question instructions, output limits, error classifications or Unicode support to remove text.

## Lessons handoff only
Exact-string translation before generic nouns avoids partial translations. Lexically separate strings/comments to protect URLs/raw templates; compare nonliteral tokens and format verbs. Keep target evidence unchanged and test English-generated labels independently. Preserve raw JSONL, distinguish package success from DB skips, and maintain separate compile-only, transport, SQL and end-to-end claims. No skill/global/profile edits were made.
'''
(OUT/'REVIEW.md').write_text(review)
print(json.dumps({'changed_paths':len(changes),'aggregate':aggregate,'remaining':dict(counts),'audit_issues':issues,'runtime_literals':runtime},indent=2))
