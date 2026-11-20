import pathlib,json,subprocess,hashlib,re,difflib
ROOT=pathlib.Path(__file__).resolve().parent.parent
E=ROOT/'libraries-comments-evidence'
OWN='config enrich evidence llmpool llmrec mcphttp notify report selfupdate sidequestion traffic cmd'.split()
CJK=re.compile('[\u3400-\u9fff]')
def dump(name,obj): (E/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def scan(paths):
 p=subprocess.run([str(E/'scanner'),*map(str,paths)],capture_output=True,text=True,check=True)
 return json.loads(p.stdout)
def init():
 paths=sorted(p for d in OWN for p in (ROOT/'source'/d).rglob('*.go'))
 original={str(p.relative_to(ROOT)):p.read_text() for p in paths};dump('originals.json',original)
 fixture=E/'fixture.go';fixture.write_text('package fixture\n// original 中文\nconst X = "保留"\n')
 a=scan([fixture])[0]
 fixture.write_text('package fixture\n// English comment\nconst X = "保留"\n');b=scan([fixture])[0]
 fixture.write_text('package fixture\n// English comment\nconst X = "changed"\n');c=scan([fixture])[0]
 keys=['Tokens','Literals','AST'];assert all(a[k]==b[k] for k in keys);assert all(a[k]!=c[k] for k in keys)
 fixture.write_text('package fixture\n// English comment\nconst X = "保留"\n')
 dump('guard-tests.json',{'original_fixture_pass':True,'comment_only_pass':True,'deliberate_literal_code_change_rejected':True,'checks':keys})
 data=scan(paths);dump('baseline.json',data)
 inventory=[]
 for r in data:
  rel=str(pathlib.Path(r['Path']).relative_to(ROOT))
  for c in r['Comments'] or []:
   if CJK.search(c['Text']):inventory.append({'path':rel,**c})
 dump('comment-inventory-before.json',inventory)
 with (E/'comments.txt').open('w') as f:
  for i,c in enumerate(inventory):f.write(f"{i} {c['path']}:{c['Line']} {c['Text']}\n")
 print('files',len(paths),'CJK comment tokens',len(inventory))
if __name__=='__main__':init()
