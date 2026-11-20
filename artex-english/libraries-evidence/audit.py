import json,re,hashlib,difflib,collections
from pathlib import Path
from comment_tools import TOKEN
from translate import ROOT
OUT=ROOT/'libraries-evidence'
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def literals(s):return [m.group() for m in TOKEN.finditer(s) if not m.group().startswith(('//','/*'))]
def structure(s):
 s=TOKEN.sub(lambda m:'' if m.group().startswith(('//','/*')) else '@LITERAL@',s)
 return re.sub(r'\s+','',s)
def audit():
 original=json.loads((OUT/'originals.json').read_text());changes=[];issues=[];inventory=[]; runtime=[]
 for rel,old in original.items():
  f=ROOT/'source'/rel;new=f.read_text()
  if old!=new:
   changes.append({'path':'source/'+rel,'before_sha256':sha(old),'after_sha256':sha(new)})
   (OUT/'diffs').mkdir(exist_ok=True)
   (OUT/'diffs'/(rel.replace('/','__')+'.diff')).write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='baseline/'+rel,tofile='candidate/'+rel)))
   if not rel.endswith('_test.go'):
    if structure(old)!=structure(new):issues.append({'path':rel,'issue':'nonliteral/noncomment token change'})
    a,b=literals(old),literals(new)
    if len(a)!=len(b):issues.append({'path':rel,'issue':'literal count changed'})
    else:
     for x,y in zip(a,b):
      if x==y:continue
      # Every changed literal has the same format verbs, in the same order.
      verbs=lambda t:re.findall(r'%(?:\[[0-9]+\])?[-+# 0]*(?:[0-9]+|\*)?(?:\.(?:[0-9]+|\*))?[vTtbcdoOqxXUeEfFgGspw%]',t)
      if verbs(x)!=verbs(y):issues.append({'path':rel,'issue':'format verbs changed','before':x,'after':y})
  for n,l in enumerate(new.splitlines(),1):
   if re.search('[\u3400-\u9fff]',l):
    classification='remaining_comment' if l.lstrip().startswith('//') else ('test_fixture_or_test_diagnostic_needs_review' if rel.endswith('_test.go') else 'inline_comment_needs_review')
    inventory.append(dict(path='source/'+rel,line=n,text=l,classification=classification))
  if not rel.endswith('_test.go'):
   for m in TOKEN.finditer(new):
    if not m.group().startswith(('//','/*')) and re.search('[\u3000-\u9fff\uff00-\uffef]',m.group()):runtime.append({'path':rel,'literal':m.group()})
 for f in (ROOT/'source').rglob('english_test.go'):
  if f.parent.name not in 'notify report selfupdate sidequestion traffic'.split():continue
  if str(f.relative_to(ROOT/'source')) not in original:changes.append({'path':str(f.relative_to(ROOT)),'before_sha256':None,'after_sha256':sha(f.read_text())})
 (OUT/'changed-paths.json').write_text(json.dumps(changes,indent=2));(OUT/'inventory-after.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2));(OUT/'audit.json').write_text(json.dumps(dict(issues=issues,remaining_production_nonenglish_literals=runtime,classification_counts=dict(collections.Counter(x['classification'] for x in inventory))),ensure_ascii=False,indent=2));print('Changed',len(changes),'Issues',issues,'Runtime non-English literals',runtime,'Remaining classified lines',len(inventory))
 return changes,issues,inventory,runtime
if __name__=='__main__':audit()
