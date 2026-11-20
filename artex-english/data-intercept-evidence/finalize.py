from pathlib import Path
import collections,hashlib,json,re,shutil,subprocess
R=Path(__file__).resolve().parent.parent;E=R/'data-intercept-evidence';S=R/'source'
before=json.loads((E/'before-sha256.json').read_text());after={str(p.relative_to(S)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['db','intercept'] for p in (S/d).rglob('*') if p.is_file()};changed=sorted(k for k,v in after.items() if before.get(k)!=v)
(E/'after-sha256.json').write_text(json.dumps(after,indent=2))
rows=[]
for rel in sorted(after):
 for n,line in enumerate((S/rel).read_text().splitlines(),1):
  if not re.search('[\u3400-\u9fff]',line):continue
  if '_test.go' in rel:kind='test_fixture_or_assertion_review_required_not_blanket_exempt'
  elif rel=='intercept/prompt.go' and ('strings.HasPrefix(reason, "实际操作：")' in line or 'prefix, consequenceSeparator, ruleSeparator = "实际操作："' in line):kind='functional_legacy_model_classification_or_reply_parsing'
  elif '--' in line and re.search('[\u3400-\u9fff]',line.split('--',1)[1]):kind='untranslated_comment'
  elif line.lstrip().startswith(('//','--')) or ('//' in line and re.search('[\u3400-\u9fff]',line.split('//',1)[1])):kind='untranslated_comment'
  elif rel=='db/company_scope.go' and 'strings.Contains(raw, "备案")' in line:kind='functional_multilingual_scope_detection'
  elif '[模型]' in line:kind='functional_legacy_model_classification_or_reply_parsing'
  elif rel=='db/db.go' and 'const name = "[内置] 删除类接口路径"' in line:kind='functional_historical_seed_identity_idempotence_key'
  else:kind='untranslated_runtime_or_SQL_prose_review_required'
  rows.append({'path':rel,'line':n,'text':line,'classification':kind})
(E/'remaining-nonenglish.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
final=json.loads((E/'final.json').read_text());red=json.loads((E/'red.json').read_text())
required=['TestEnglishJudgeGeneratedReason','TestEnglishHandleAskSummaryAndCancellation','TestEnglishVerdictCompatibility','TestInterceptSourceEnglishLegacy','TestApprovalSQLRecognizesEnglishLegacy','TestRestoreApprovalEnglishLegacyEvidence','TestEnglishGeneratedDefaultsPreserveSuppliedNames','TestEnglishVerdictStrictRejections','TestDeleteEndpointPathPattern','TestParseVerdictRejectsIncompleteOrAmbiguousReplies','TestParseVerdictKeepsCompleteChineseExplanation']
terminal={t['name']:t['action'] for t in final['tests']}
assert all(terminal.get(n)=='pass' for n in required)
perpackage={}
for line in (E/'final.jsonl').read_text().splitlines():
 try:r=json.loads(line)
 except ValueError:continue
 if r.get('Test') and r.get('Action') in ('pass','fail','skip'):
  group=perpackage.setdefault(r['Package'],{'top_level':collections.Counter(),'subtests':collections.Counter()});group['subtests' if '/' in r['Test'] else 'top_level'][r['Action']]+=1
report={
 'status':'PARTIAL translation: generated runtime DB/interception prose and judge prompts translated; many database comments/test prose remain. Critical approval English/legacy compatibility implemented and offline regressions pass.',
 'scope':'Only source/db/**, source/intercept/**, and new data-intercept-evidence/** written. No peer originals or other source directories modified. No services, PostgreSQL provisioning, downloads, installs, model calls, browser/session, cloud or credentials changes.',
 'changed_paths':changed,'changed_path_count':len(changed),
 'source_pins':{'before':'before-sha256.json','after':'after-sha256.json','before_files':len(before),'after_files':len(after)},
 'translations':['translations.json','prompt-translations.json','seed-translations.json','comment-translations.json'],
 'critical_contract':{'summary':'Tool <name> requests approval (#<id>)','new_model_marker':'[Model]','legacy_marker':'[模型]','classification_paths':['db/intercept.go interceptSource','db/intercept.go approvalDecisionSource SQL expression','db/task_archives_restore.go restoreInterceptRows','db/schema.sql existing empty-decision_source backfill expression'],
 'preservation':'Rule source precedence and explicit persisted decision_source retained. Archived settled reason text, IDs and timestamps preserved through actual restore helper with captured SQL payload. Multilingual user/target/custom-policy evidence remains unchanged. Pending archive timeout behavior remains fail-closed; only its newly generated reason is translated. No historical text-laundering migration added or executed.'},
 'tdd':{'red_receipt':'red.jsonl','red_top_level':red['top_level'],'red_subtests':red['subtests'],'meaningful_failures':'Actual Judge emitted localized marker/action labels; actual HandleAsk emitted localized approval summary; actual ParseVerdict rejected valid English explanations; interceptSource and production SQL lacked English marker. Legacy/precedence/unknown controls passed.',
 'green_receipt':'green.jsonl','chronology_limits':'Initial five contract tests were run RED before production changes. Archive-helper capture and extra generated-default/strict-English regressions were added after implementation and are regression evidence, not test-first RED. Individual translation-only strings/comments/prompts were not each changed under separate TDD cycles.'},
 'tests':{'final':'final.json','raw':'final.jsonl','returncode':final['returncode'],'top_level':final['top_level'],'subtests':final['subtests'],'per_package':perpackage,'required_names_verified':required,'package_failures':final['package_failures'],
 'skips':'139 top-level and 9 subtest skips because no approved configured isolated PostgreSQL fixture was available. No PostgreSQL startup/provisioning attempted. Two top-level PASS containers have only skipped DB subtests (TestRetestFixedTriageOnlyAfterSuccessfulCompletion and TestSideTaskArchiveVersions); these establish no DB behavior.',
 'limits':'Judge, HandleAsk, and archive restore are real production entrypoints with a synthetic database/sql driver at the external SQL seam. These do not prove PostgreSQL execution, schema application, persistence roundtrip, model inference, HTTP/UI integration, or end-to-end approval execution. Production SQL classifier text is checked structurally, not executed against PostgreSQL.',
 'assertion_updates':'Two existing DB-only expectations translated to match generated archive warning and task-company provenance, retaining IDs/source/status/evidence checks; they remain skipped, not qualified.'},
 'format':{'receipt':'format-final.json','changed_go_files_formatted':True},
 'remaining_nonenglish':{'complete':False,'line_count':len(rows),'file_count':len(set(r['path'] for r in rows)),'classification_counts':dict(collections.Counter(r['classification'] for r in rows)),'per_file':dict(collections.Counter(r['path'] for r in rows)),'exact_line_inventory':'remaining-nonenglish.json','caveat':'CJK-only inventory is not proof of all-language coverage. Tests include purposeful multilingual evidence AND untranslated test names/comments, so their category is not a blanket exemption. Existing historical V3 seed name is retained to preserve name-key idempotence, not presented as completed English display output.'},
 'disk':{'free_bytes_final':shutil.disk_usage(R).free,'no_large_cache_copy':True,'cache_limit':'Task-local cache directory symlinks retained compiler cache buckets. Bucket writes can therefore land in retained shared cache; this is not a fully isolated cache. No copies/downloads/installations or cache deletion performed.'},
 'issues':['Automatic single-file lint helpers lack Go module context and reported undefined/import errors; supported offline package test run compiled both full owned packages successfully.','Two overlapping exact translation mappings initially produced mixed phrases in three lines; corrected before final regression and inventory.'],
 'lessons_handoff':['English approval markers require compatibility in producer, live classifier SQL, Go classifier, archive restore, schema backfill, and frontend.','Judge prompt output headings are a parse contract: translate the prompt and add English parsing without removing historical parsing or strict completeness checks.','Do not translate persisted seed identity keys as display prose without an idempotence-compatible identity plan.','Synthetic SQL capture can qualify real entrypoint payload preservation offline but is not PostgreSQL/persistence evidence.','Apply overlapping translation phrases longest-first and inspect remaining runtime CJK before claiming complete translation.']
}
(E/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'changed_paths':len(changed),'remaining_lines':len(rows),'classifications':report['remaining_nonenglish']['classification_counts'],'tests':final['top_level'],'subtests':final['subtests'],'disk_free':report['disk']['free_bytes_final']},indent=2))
review=f'''# Database/interception English review

## Outcome
Partial translation. New approval summaries are `Tool <name> requests approval (#<id>)`; new generated model reasons use `[Model]`. The classifier accepts `[Model]` and historical `[模型]`, including live history, archive restore, and the existing schema source backfill. Generated database errors, fallback display labels, notification logs, retest helper instructions, seed descriptions, and judge prompts are English. Many database comments/test prose remain untranslated; do not mark the whole ARTEX translation complete.

## Verification
- Same-entrypoint RED: top-level {red['top_level']}; subtests {red['subtests']}. See `red.jsonl`.
- Final offline Go run: top-level {final['top_level']}; subtests {final['subtests']}; return code {final['returncode']}, no package failures. Complete receipts: `final.jsonl` and `final.json`.
- Actual `Judge`, `HandleAsk`, `ParseVerdict`, `interceptSource`, and `restoreInterceptRows` entrypoints exercised. English and legacy positives, rule precedence, unknown-source negatives, cancellation-denies-execution, strict parser rejections, multilingual evidence, record IDs and historical timestamps covered. SQL seam is synthetic, not a live PostgreSQL fixture.
- Database-backed skips are not passes. Two PASS parent tests contain only skipped DB subtests. No real PostgreSQL persistence/schema application or model/UI end-to-end qualification.
- Initial contract tests were RED before implementation. Additional archive capture and strict English/generated-default tests were added later as regressions; do not claim RED for those.
- Existing generated-warning/provenance assertions updated in two DB tests but not executed due to fixture absence.

## Scope and preservation
Only `source/db/**`, `source/intercept/**`, and this new evidence directory changed. No original/peer source edited, migrations added for text laundering, database rewritten, service provisioned, credential/config binding read manually, browser changed, dependencies downloaded, or model called. Security regexes, tool names, SQL identifiers, routes, limits and source/rule precedence retained. Historical V3 seed name remains an identity/idempotence exception.

## Remaining work
Exact file/line/text inventory with classifications: `remaining-nonenglish.json` ({len(rows)} lines across {report['remaining_nonenglish']['file_count']} files). Production runtime CJK outside compatibility/identity exceptions: {report['remaining_nonenglish']['classification_counts'].get('untranslated_runtime_or_SQL_prose_review_required',0)} review-required lines. Remaining comments and test prose are **not** claimed translated or exempt. CJK scanning does not establish all-language completeness.

## Evidence
`before-sha256.json` / `after-sha256.json` pin all owned source files. `report.json` lists every changed path, test terminal count, scope, caveat and handoff lesson. Translation receipts preserve exact phrase mappings; three overlapping substitutions were repaired before the final run. `format-final.json` records successful formatting of changed Go files.

## Environment limits
Offline cached Go toolchain/modules; no installation or large cache copy. Task cache bucket symlinks reuse retained cache and may write those buckets, so cache isolation is not claimed. Final free disk: {report['disk']['free_bytes_final']} bytes. No disk or persistence errors encountered. Save procedural lessons through the parent handoff only; no global/profile skills edited.
'''
(E/'REVIEW.md').write_text(review)
