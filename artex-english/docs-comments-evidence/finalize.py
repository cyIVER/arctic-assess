"""Finish the bounded translation handoff; evidence only, no source writes."""
import collections,difflib,hashlib,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import guard
E,R=guard.E,guard.R
base=json.loads((E/'baseline.json').read_text())
checks=json.loads((E/'verification.json').read_text())
changed=json.loads((E/'changed-paths.json').read_text())
hits=json.loads((E/'comment-translation-hits.json').read_text())
remaining=json.loads((E/'remaining-cjk.json').read_text())
classified=[]
for p,old in base.items():
    if not p.endswith('.go'):continue
    s=(R/p).read_text();_,comments,literals=guard.scan(s)
    for start,end,c in comments:
        for offset,line in enumerate(c.splitlines()):
            if not guard.CJK.search(line):continue
            protected=bool(re.search(r'docs/[^\s]*[\u3400-\u9fff]|京ICP备',line))
            classified.append({'path':p,'line':s[:start].count('\n')+offset+1,'category':'preserved_comment_reference_or_UTF8_example' if protected else 'unfinished_explanatory_comment','text':line})
    pos=0
    for lit in literals:
        start=s.find(lit,pos);pos=start+len(lit)
        if guard.CJK.search(lit):
            classified.append({'path':p,'line':s[:start].count('\n')+1,'category':'preserved_multilingual_test_fixture' if p.endswith('_test.go') else 'out_of_scope_runtime_or_SQL_literal','text':lit})
s=(R/'source/CHANGELOG.md').read_text()
for n,line in enumerate(s.splitlines(),1):
    if guard.CJK.search(line):
        assert not guard.CJK.search(re.sub(r'`[^`\n]*`','',line)),(n,line)
        classified.append({'path':'source/CHANGELOG.md','line':n,'category':'preserved_changelog_inline_code_or_reference','text':line})
guard.write('remaining-classified.json',classified)
old=base['source/CHANGELOG.md']
def releases(t):
    out=[]
    for m in re.finditer(r'^## .*$(?:\n(?!## ).*)*',t,re.M):
        block=m[0];out.append({'heading':block.splitlines()[0],'bullet_count':len(re.findall(r'^\s*- ',block,re.M))})
    return out
assert releases(old)==releases(s)
proof={'all_structure_fields_equal':checks['source/CHANGELOG.md'],'per_release_entry_counts_before':releases(old),'per_release_entry_counts_after':releases(s),'inline_code_rule':'Exact per-line multiset: tokens may move within their original prose line for English grammar; none added, removed or changed.','cjk_lines_before':sum(bool(guard.CJK.search(x)) for x in old.splitlines()),'cjk_lines_after':7,'unfinished_prose_outside_inline_code':0}
for name,mutation in [('removed_release',old.replace('## [0.3.15] - 2026-10-07','',1)),('changed_link',old.replace('https://github.com/Autumn-27','https://invalid.example',1)),('removed_entry',old.replace(old.splitlines()[20]+'\n','',1))]:
    try: rejected=guard.structure(old)!=guard.structure(mutation)
    except ValueError: rejected=True
    assert rejected,name
proof['post_edit_structural_mutation_tests_rejected']=['removed_release','changed_link','removed_entry']
guard.write('changelog-proof.json',proof)
patch=''.join(''.join(difflib.unified_diff(v.splitlines(True),(R/p).read_text().splitlines(True),fromfile='before/'+p,tofile='after/'+p)) for p,v in base.items() if p in changed)
(E/'owned-changes.patch').write_text(patch)
counts=dict(collections.Counter(x['category'] for x in classified))
report={'status':'partial_comments_complete_historical_changelog','changed_source_paths':changed,'changed_source_files':len(changed),'go_files_checked':len(checks)-1,'comments_translated':len(hits),'comment_files_changed':len({x['path'] for x in hits}),'historical_changelog':{'versions':'0.3.15 through 0.3.2','entry_lines_translated':270,'cjk_lines_before':proof['cjk_lines_before'],'cjk_lines_after':7,'unfinished_prose_outside_inline_code':0,'structure_unchanged':True,'unreleased_bytes_unchanged':True},'verification':{'commands':['python docs-comments-evidence/guard.py baseline','python docs-comments-evidence/apply_changelog.py','python docs-comments-evidence/apply_comments.py','python docs-comments-evidence/guard.py verify','python docs-comments-evidence/finalize.py'],'result':'PASS: all 228 Go files retain exact non-comment bytes and literal bytes; all changelog structural checks pass.','pre_edit_self_tests':'Same bytes accepted, translated comments accepted, deliberate identifier mutation and deliberate literal mutation rejected.','parser_or_compiler_executed':False,'parser_blocker':'No cached goparse found in task artifacts/scratch or PATH; Go builds/downloads forbidden. Scanner is a dependency-free Python state machine, not go/parser. Requested same-byte parse-positive fixture was NOT executed.','compile_claim':None,'structural_mutation_tests':'Removed release, changed link and removed entry rejected after translation.'},'remaining_classification_counts':counts,'unfinished_scope_manifest':'docs-comments-evidence/remaining-classified.json','unfinished_scope':'All records categorized unfinished_explanatory_comment require further translation. Preserved reference/UTF-8 comment examples are exceptions. Runtime/SQL literals and multilingual test fixtures remain unchanged and outside comment-only ownership. Intercept has no remaining CJK comments.','limitations':['Bounded time: comment translation is partial, not complete.','No Go syntax parse or compile executed; exact non-comment-byte equivalence is verified instead.','No repository .git present at task root; source baseline/hashes and owned diff supply evidence.'],'lessons_handoff':['Use comment-span replacements, never global CJK replacements: SQL and multilingual fixtures must remain byte-identical.','Pin per-line inline-code multisets and release boundaries before translating historical prose; English may reorder inline references without changing tokens.','Locate a cached Go parser before assigning parse verification under a no-build constraint.']}
report['evidence_files']=sorted(str(p.relative_to(R)) for p in E.iterdir() if p.is_file())+['docs-comments-evidence/report.json','docs-comments-evidence/REVIEW.md']
guard.write('report.json',report)
(E/'REVIEW.md').write_text('''# Comments and historical changelog review

## Outcome
Historical changelog 0.3.15–0.3.2 is translated, with zero CJK prose outside preserved inline code. Existing English Unreleased is byte-identical. All release headings/dates, heading levels, entry indentation/counts, URLs, inline-code multisets per original line, fences and line count are unchanged. See `changelog-proof.json` for per-release counts and mutation tests.

161 comments were translated in 20 Go files. All 228 owned Go files, including tests, retain **every non-comment byte and every literal byte exactly**, not merely normalized tokens. Directives are unchanged. See `verification.json`, before/after SHA256 manifests and `owned-changes.patch`.

## Verification limits
The Python lexical guard passed its positive and deliberate identifier/literal mutation fixtures before source edits. Structural negative tests also reject removed release headings, changed URLs and removed entries. No cached goparse executable was located; builds were forbidden. **No Go parse or compile was executed, and the requested same-byte parse-positive fixture remains unperformed.** Do not label this as compiled or fully syntax-qualified evidence.

## Unfinished language scope
Comment translation is partial. `remaining-classified.json` gives exact current paths, lines, category and text, including unfinished explanatory comments, protected documentation references/UTF-8 examples, unchanged multilingual test fixtures and out-of-scope runtime/SQL literals. All interception CJK is in preserved literals, not comments. Seven changelog lines retain only protected inline identifiers, examples, paths or evidence.

## Handoff
`report.json` lists exact changed source paths and counts. Only CHANGELOG and comments in owned Go files were changed; all new evidence is under this directory. Frozen baseline/reports from prior workers were not edited. There is no git repository at this task root, so the recorded owned-subset baseline and diff are the comparison source. Continue from the unfinished-comment category without changing behavior strings, SQL, fixtures, directives or other workers' files.

Lessons: replace comment spans, not global CJK matches; pin historical structure and inline code before edits; locate a cached parser before promising parse verification under no-build constraints.
''')
print(json.dumps({'counts':counts,'changed_source_files':len(changed),'go_files_checked':len(checks)-1,'release_entries':proof['per_release_entry_counts_before']},indent=2))
