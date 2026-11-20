import re,json
from translate import ROOT
# Lexical Go tokenization: string literals precede comment alternatives, so URLs
# and comment-like bytes in raw templates are never treated as comments.
TOKEN=re.compile(r'`[^`]*`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
def comments(s):return [m for m in TOKEN.finditer(s) if m.group().startswith(('//','/*'))]
def restore_original_comments():
 for rel,old in json.loads((ROOT/'libraries-evidence/originals.json').read_text()).items():
  if rel.endswith('_test.go'):continue
  f=ROOT/'source'/rel;s=f.read_text();before=comments(old);after=comments(s)
  assert len(before)==len(after),rel
  for x,y in reversed(list(zip(before,after))):s=s[:y.start()]+x.group()+s[y.end():]
  if s!=f.read_text():f.write_text(s)
if __name__=='__main__':restore_original_comments()
