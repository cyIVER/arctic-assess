from pathlib import Path
import json,re,hashlib,difflib,collections
root=Path(__file__).resolve().parent.parent;ev=root/'agent-evidence';src=root/'source'
old=json.loads((ev/'original-subset.json').read_text())
current={str(f.relative_to(src)):f.read_text() for d in ('agent','guard') for f in (src/d).rglob('*') if f.is_file()}
changed=sorted(k for k,v in current.items() if old.get(k)!=v)
diff=''.join(''.join(difflib.unified_diff(old.get(k,'').splitlines(True),current[k].splitlines(True),fromfile='original/'+k,tofile='candidate/'+k)) for k in changed)
(ev/'translation.diff').write_text(diff)
remaining=[]
for name,text in sorted(current.items()):
 for i,line in enumerate(text.splitlines(),1):
  if not re.search('[\u3400-\u9fff]',line):continue
  if name=='agent/provider.go' and any(x in line for x in ['"余额不足"','"额度不足"']):kind='functional_exception';why='Multilingual provider quota/error detection; preserve original response matching.'
  elif name=='agent/provider_quota_test.go':kind='functional_exception';why='Purposeful multilingual provider error fixture; must remain recognizable.'
  elif name.endswith('_test.go') and '//' not in line.lstrip()[:2]:kind='functional_exception';why='Existing intentional Unicode input/evidence or legacy message assertion; preserved. Legacy assertions for untranslated production messages must be updated only with the matching future translation.'
  elif re.search(r'(?:docs/[^\s]*[\u3400-\u9fff])',line):kind='functional_exception';why='Literal existing documentation path; do not rename an out-of-scope file or break references.'
  elif line.lstrip().startswith('//') or ('//' in line and '"' not in line.split('//',1)[1]):kind='remaining_comment';why='Not translated within bounded pass; needs follow-up, not an approved language exception.'
  else:kind='remaining_production_text';why='Not translated within bounded pass; must translate with focused tests preserving identifiers, semantics and Unicode evidence.'
  remaining.append(dict(path=name,line=i,text=line,classification=kind,rationale=why))
(ev/'remaining-nonenglish.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2))
counts=collections.Counter(x['classification'] for x in remaining)
byfile=collections.Counter(x['path'] for x in remaining if x['classification'].startswith('remaining_'))
receipts={p.stem:json.loads(p.read_text()) for p in ev.glob('*.json') if p.stem in ['english-red','english-green','english-green-fixed','orchestration-red','orchestration-green','runtime-red','final-focused','final-verified','final-complete']}
report={
'status':'partial: all built-in editable agent prompt bodies translated; remaining domain tool catalog descriptions/messages/comments require follow-up',
'ownership':'Only source/agent/**, source/guard/** and new agent-evidence/** written. No server/frontend/db/library/deployment changes.',
'changed_paths':changed,'changed_path_count':len(changed),
'original_subset_pins':'original-subset-pins.json','original_subset_snapshot':'original-subset.json','original_file_count':len(old),'diff':'translation.diff',
'accomplished':['English Auto, solo pentest, assistant fallback, reporter, goals, planner, worker and mainagent prompt bodies; English requested instead of Chinese in fallback/reporter output policies.','English scope-decomposition and artifact/traffic tails, wrap-up and task-timeout prompts, worker launch/resume/user-input framing, planner event/wakeup/todo framing, constraints framing, finding evidence handoff guidance, reporter tool descriptions and schema descriptions.','English guard denial/cancellation/approval-timeout framing explicitly identifies ARTEX platform control, not target defense, preserving raw policy/user reasons.','Existing Unicode user prompt overrides, original evidence, target payloads, quota detection and multilingual fixtures retained.','Existing tests retain all assertions; only generated artifact heading and generated intent label expectations translated.'],
'production_structure_check':json.loads((ev/'structure.json').read_text()),
'tests':receipts,'final_test_receipt':'final-complete.json','test_limits':['Focused offline agent/guard packages only; no model calls, network requests, DB fixture, server, frontend build, whole-app build or end-to-end run.','Go file-write lint diagnostics ran outside module context; authoritative package test compilation succeeds in retained Go 1.26.3 toolchain.','Initial RED receipts are genuine missing-English assertion failures. An intermediate GREEN attempt exposed missing finding_node_id documentation; fixed implementation, not assertion. Another exposed old artifact-header expectations; translated expected heading without removing assertions.'],
'nonenglish_remaining':{'inventory':'remaining-nonenglish.json','counts_by_classification':dict(counts),'pending_files':dict(byfile)},
'cross_stack_handoff':['Read frontend-evidence/report.json. Model reason marker must be [Model]; approval summary must be Tool <name> requests approval (#<id>), with old parser aliases retained where required. No producers of these markers found in owned agent/guard source; server/intercept owners must qualify them.','Reporter trigger prompt now describes Task: #<id>; server must emit corresponding English context. Tool-returned data/user content must remain unmodified.','Existing stored/custom prompts are deliberately not rewritten: seed changes affect new/default prompts, not existing DB overrides. Candidate source translation does not migrate a deployed database.'],
'exact_next_scope':[{'path':k,'pending_CJK_lines':v} for k,v in sorted(byfile.items())],
'next_priority':'Finish agent/tools.go, agent/tools_insert.go, agent/toolcatalog.go, agent/terminalreason.go, agent/cancelcause.go, agent/compaction.go, agent/provider.go, agent/chat.go, agent/retester.go, agent/noa.go; remaining comments in modified role files. Add English tool-schema/error/summary tests before each slice. Preserve quota regex/input fixtures and translate matching legacy expectation strings only alongside production text.',
'lessons_handoff':['English UI alone is insufficient: editable seed bodies, code-owned tails, resumed inputs and dynamically appended evidence guidance all reach the model.','Do not translate original Unicode evidence/DB overrides or semantic multilingual detection patterns to make a language scan empty.','Masking literal values in Go scanner tokens detects accidental control-flow/identifier/budget edits; preserve string-concatenation structure too. It is not proof of natural-language semantic equivalence.'],
'completion_limit':'Bounded pass stopped partial rather than bulk substituting or weakening security/protocol tests. Full requested all-English conversion is not complete.',
'final_sha256':{k:hashlib.sha256(current[k].encode()).hexdigest() for k in changed}
}
(ev/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'changed_paths':changed,'remaining':dict(counts),'pending_files':dict(byfile)},indent=2))
