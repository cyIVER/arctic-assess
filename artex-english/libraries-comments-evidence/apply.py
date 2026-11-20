import work,collections,subprocess,json,re,pathlib
E=work.E;ROOT=work.ROOT
inv=json.loads((E/'comment-inventory-before.json').read_text());orig=json.loads((E/'originals.json').read_text())
m={}
for f in sorted(E.glob('translations*.tsv')):
 for line in f.read_text().splitlines():
  k,v=line.split('\t',1);k=int(k);assert k not in m;k0=inv[k];assert k0['Text'].startswith('//');assert not work.CJK.search(v) or k in (827,926,891,896)
  m[k]=('//\t' if k0['Text'].startswith('//\t') else '// ')+v
# Preserve machine identifiers and path notation even in explanatory examples.
m[397]=m[397].replace('/bot<realToken>/sendMessage','/bot<真Token>/sendMessage')
by=collections.defaultdict(list)
for k,v in m.items():by[inv[k]['path']].append((inv[k],v))
for rel,edits in by.items():
 b=orig[rel].encode()
 for c,v in sorted(edits,key=lambda x:x[0]['Start'],reverse=True):
  assert b[c['Start']:c['End']].decode()==c['Text']
  b=b[:c['Start']]+v.encode()+b[c['End']:]
 p=ROOT/rel;p.write_bytes(b)
subprocess.run(['gofmt','-w',*[str(ROOT/p) for p in sorted(by)]],check=True)
after=work.scan([ROOT/rel for rel in sorted(orig)]);before=json.loads((E/'baseline.json').read_text());bm={r['Path']:r for r in before}
for r in after:
 a=bm[r['Path']]
 for key in ('Tokens','Literals','AST'):assert a[key]==r[key],(r['Path'],key)
 assert r['Formatted'],r['Path']
work.dump('after.json',after)
print('translated comment tokens',len(m),'changed files',len(by),'all scanner tokens, literals and AST identities match')
print('untranslated production',[(i,c['path'],c['Line']) for i,c in enumerate(inv) if not c['path'].endswith('_test.go') and i not in m])
