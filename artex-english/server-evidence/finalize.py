"""Finalize exact scoped source pins and conservative remaining-language inventory."""
import collections,hashlib,json,re,os
from pathlib import Path
R=Path(__file__).resolve().parent.parent;E=R/'server-evidence';S=R/'source'
before=json.loads((E/'before-sha256.json').read_text())
after={str(p.relative_to(S)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (S/'server').rglob('*') if p.is_file()}
(E/'after-sha256.json').write_text(json.dumps(after,indent=2))
changed=sorted(k for k,v in after.items() if before.get(k)!=v)
remaining=[]
for p in sorted((S/'server').rglob('*')):
 if not p.is_file():continue
 try: lines=p.read_text().splitlines()
 except UnicodeError:continue
 for n,line in enumerate(lines,1):
  if not re.search('[\u3400-\u9fff]',line):continue
  path=str(p.relative_to(S))
  if p.name=='chat_mentions.go' and ('chatMentionPattern' in line or re.search('"(?:漏洞|IP)":',line)):
   category='functional_exception_legacy_mention_aliases'
  elif p.name=='conversations.go' and 'c.Title ==' in line:
   category='functional_exception_persisted_legacy_default_title'
  elif 'HasPrefix(m, "意图")' in line or 'HasPrefix(m, "提示")' in line:
   category='functional_exception_multilingual_input_recognition'
  elif '[模型]' in line:
   category='legacy_model_reason_fixture' if p.name.endswith('_test.go') else 'review_required_runtime_legacy_marker'
  elif line.lstrip().startswith('//') or ('//' in line and not re.search('"[^"\n]*[\u3400-\u9fff][^"\n]*"',line.split('//',1)[0])):
   category='untranslated_comment'
  elif p.name.endswith('_test.go') or 'testdata/' in path:
   category='test_fixture_or_assertion_review_required_not_all_exempt'
  else:category='untranslated_runtime_prose_or_prompt_review_required'
  remaining.append({'path':path,'line':n,'classification':category,'text':line})
(E/'remaining-nonenglish.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2))
counts=collections.Counter(x['classification'] for x in remaining)
files=collections.Counter(x['path'] for x in remaining)
final=json.loads((E/'final.json').read_text());red=json.loads((E/'red.json').read_text())
# All required terminal tests must actually exist, not merely a zero exit status.
required=['TestChatMentionEnglishLegacyCompatibility','TestChatMentionFrontendGeneratedTokens','TestChatMentionParsing','TestChatMentionBoundedJSON','TestUploadSkillRejectsTraversal','TestValidatePassword']
assert all(any(t['name']==name and t['action']=='pass' for t in final['tests']) for name in required)
fmt=json.loads((E/'format-check.json').read_text())
report={
 'status':'PARTIAL translation; compatible English mention parser implemented and focused offline Go regressions pass',
 'scope':'Only staged source/server/** and new server-evidence/** written. No peer source, frontend, agent/db/library/docs, service, deployment, configuration, credentials, browser, or cloud changes.',
 'changed_paths':changed,'changed_path_count':len(changed),
 'source_pins':{'before':'before-sha256.json','after':'after-sha256.json','before_files':len(before),'after_files':len(after)},
 'translation_receipts':['translations.json','translations-extra.json','comment-translations.json'],
 'tdd':{'red':'red.jsonl','red_summary':red['top_level'],'red_subtests':red['subtests'],'meaningful_failure':'Eight new English category labels produced zero references; legacy parsing and IP controls passed before the minimal alias patch.','green':'mention-green.jsonl','chronology_limit':'Hand-authored cross-stack contract vectors were tested RED before the minimal patch. Actual frontend-generated JSON fixture was generated and tested later; do not claim that generated-fixture test ran RED. Translation-only strings/comments were changed after mention GREEN, not each under separate test-first cycles.'},
 'tests':{'final':'final.json','raw':'final.jsonl','returncode':final['returncode'],'top_level':final['top_level'],'subtests':final['subtests'],'required_test_names_verified':required,'retained_initial_regression_failure':'regression.jsonl: one stale translated assertion expected capitalized Invalid path. Replaced with exact complete English traversal error; status 400 and empty-directory checks remain.','skips':'Two existing database-backed auth unavailable-source tests skipped because PostgreSQL was unavailable/unconfigured. No database provisioning or service changes performed.','unexecuted':'Full database-backed mention expansion, conversation/worker integration, model inference, full server suite, frontend build/browser; not qualified.'},
 'format':{'changed_go_files_formatted':True,'command_receipt':'gofmt.json','tree_scan':'format-check.json','preexisting_unformatted_unchanged':[p for p in fmt['unformatted'] if str(Path(p).relative_to(S)) not in changed]},
 'crossstack':{'fixture':'source/server/testdata/english_mentions.json','generation_receipt':'frontend-tokens.json','production_parser_test':'TestChatMentionFrontendGeneratedTokens','mapping':{'Finding':'finding','Asset':'asset','Company':'company','Endpoint':'endpoint','IP':'ip','App':'app','Domain':'root_domain','Subdomain':'subdomain','Service':'service'},'preserved':'Legacy Chinese aliases, numeric-ID validation, ten-reference bound, alias deduplication, unknown/plain text behavior, unavailable-data denial, and supplied multilingual record labels.','compatibility':'Skill conflicts now contain already exists; archive missing errors now contain Archive not found.'},
 'critical_peer_handoff':['intercept/intercept.go:480-482 still emits [模型] and :612 still emits 工具 <name> 请求审批 (#<id>); outside server ownership. Peer must change generated marker to [Model] and summary to Tool <name> requests approval (#<id>).','db/intercept.go:231,251 and db/task_archives_restore.go:680 recognize legacy [模型]. Peer must retain legacy parsing while adding [Model] if changing producer; server legacy-marker fixtures intentionally remain.'],
 'remaining_nonenglish':{'complete':False,'line_count':len(remaining),'file_count':len(files),'classification_counts':dict(counts),'per_file':dict(sorted(files.items())),'line_inventory':'remaining-nonenglish.json','note':'Conservative review-required test category includes purposeful multilingual fixtures AND untranslated test names/assertions; it is not a blanket exemption. CJK scan excludes non-CJK punctuation and is not proof of all-language coverage.'},
 'security_limits':'No intentional changes to routes, auth binding, admission/validation/detection regex, JSON keys, or native execution behavior. Real skill path/Unicode/GBK/encryption/compression and archive traversal/symlink controls passed; auth DB failure tests skipped, so full security regression qualification is not claimed.',
 'disk':{'free_bytes_final':os.statvfs(R).f_bavail*os.statvfs(R).f_frsize,'no_cache_copy':True,'no_download_install':True},
 'lessons_handoff':['Translate wire category labels only with backend English aliases and retained historical aliases.','Keep exact English generated-output assertions separate from multilingual evidence fixtures.','Actual frontend-emitted token fixtures can qualify parser mapping offline without a frontend build, but do not prove database resolution or UI runtime behavior.','Model approval marker changes require matching DB source classification, not only frontend compatibility.']}
(E/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
review='# Server English candidate review\n\n**Partial translation, not completion.**\n\n'
review+=f"Changed {len(changed)} server paths. Final actual offline Go execution: {final['top_level']} top-level; {final['subtests']} subtests. No failed final tests. Two PostgreSQL-dependent tests skipped.\n\n"
review+='English mention tokens map to all nine backend kinds, retaining legacy aliases, supplied labels, validation, bounds and deduplication. Actual frontend-generated tokens are retained and tested. Initial hand-authored English contract tests failed before the alias patch; the generated fixture test was added afterward.\n\n'
review+=f"Remaining CJK: {len(remaining)} lines across {len(files)} files. See remaining-nonenglish.json for every exact path/line/text and conservative classification. Much runtime prose, prompts, comments and test naming remains untranslated.\n\n"
review+='Approval producer and DB marker-classification changes remain in peer-owned intercept/db files; see report.json critical_peer_handoff. No source files outside server were written. No deployments, listeners, databases, models, credentials, global profiles, package installation or downloads were started. Cached Go compilation and focused tests actually ran; gofmt alone is not compilation evidence.\n\n'
review+='## Changed paths\n'+''.join('- `'+p+'`\n' for p in changed)
review+='\n## Remaining by file\n'+''.join(f'- `{p}`: {n} CJK lines\n' for p,n in sorted(files.items()))
(E/'REVIEW.md').write_text(review)
print(json.dumps({'changed':len(changed),'remaining_lines':len(remaining),'remaining_files':len(files),'categories':dict(counts),'final':final['top_level'],'subtests':final['subtests']},indent=2))
