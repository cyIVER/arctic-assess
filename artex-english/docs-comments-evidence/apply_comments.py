import json,sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import guard
translations={}
for f in ['comment-translations.json','comment-translations-server.json']:
    translations.update(json.loads((guard.E/f).read_text()))
hits=[]
for p in guard.files():
    if p.suffix!='.go':continue
    old=p.read_text();new=old
    for start,end,c in reversed(guard.scan(old)[1]):
        if c not in translations:continue
        assert not re.search(r'//\s*(go:|\+build|line )|^/\*line ',c)
        t=translations[c]
        assert re.findall(r'https?://\S+',c)==re.findall(r'https?://\S+',t)
        new=new[:start]+t+new[end:]
        hits.append({'path':str(p.relative_to(guard.R)),'line':old[:start].count('\n')+1,'old':c,'new':t})
    assert guard.scan(old)[0]==guard.scan(new)[0]
    assert guard.scan(old)[2]==guard.scan(new)[2]
    if old!=new:p.write_text(new)
guard.write('comment-translation-hits.json',hits)
print('Translated',len(hits),'comments in',len(set(x['path'] for x in hits)),'files')
