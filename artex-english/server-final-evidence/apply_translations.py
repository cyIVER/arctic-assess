import json,re
from pathlib import Path
R=Path(__file__).resolve().parent.parent
mapping=json.loads((R/'server-final-evidence/translations.json').read_text())
# Exact translated phrases only, never global Chinese-token substitutions.
# Preserve multilingual-input recognition, legacy aliases, evidence and saved prompts.
hits={}
for p in sorted((R/'source/server').glob('*.go')):
 text=p.read_text();before=text
 for old,new in sorted(mapping.items(),key=lambda x:-len(x[0])):
  n=text.count(old)
  if n: text=text.replace(old,new);hits.setdefault(str(p.relative_to(R/'source')),[]).append({'old':old,'new':new,'count':n})
 if text!=before:p.write_text(text)
(R/'server-final-evidence/translation-hits.json').write_text(json.dumps(hits,ensure_ascii=False,indent=2))
print('Changed',len(hits),'files')
