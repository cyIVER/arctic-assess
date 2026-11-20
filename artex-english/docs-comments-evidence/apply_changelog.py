import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import guard
b=json.loads((guard.E/'baseline.json').read_text())['source/CHANGELOG.md']
lines=b.splitlines(keepends=True)
headings={'拦截':'Interception','新增的功能':'Added','漏洞推送':'Vulnerability Notifications','修复的问题':'Fixed','设计说明':'Design Notes','测试基础设施':'Test Infrastructure','流量':'Traffic','工具':'Tools','部署':'Deployment','发现':'Findings','数据库':'Database','贡献者':'Contributors','任务列表':'Task List','修改的功能':'Changed','探索图与规划态势概览':'Exploration Graph and Planning Overview','资产拦截':'Asset Interception','操作审查':'Operation Review','任务归档':'Task Archiving','账户与合规':'Accounts and Compliance','许可与依赖':'License and Dependencies','探索链路播报板':'Exploration Feed','意图管理':'Intent Management','聊天':'Chat','网络':'Network','触发器':'Triggers','任务':'Tasks','资产':'Assets','部署与更新':'Deployment and Updates','已知限制':'Known Limitations','依赖':'Dependencies','探索图':'Exploration Graph','技能':'Skills','对话':'Conversations','运维':'Operations','删除的功能':'Removed','约束':'Constraints','任务与资产':'Tasks and Assets','构建':'Build'}
translations={}
for f in ['changelog-translations.json','changelog-translations-older.json']:translations.update(json.loads((guard.E/f).read_text()))
translations['320']=translations['320'].replace('each call records','each `add_hint` call records')
translations['333']=translations['333'].replace(chr(0),r'\u0000')
translations['696']=translations['696'].replace('invalid IP assets','assets with invalid `ip` values')
translations['826']=translations['826'].replace('a model prefix','the `[模型]` prefix')
for n,l in enumerate(lines,1):
 if str(n) in translations:lines[n-1]=translations[str(n)]+'\n'
 elif l.startswith('#'):
  prefix,_,text=l.rstrip('\n').partition(' ')
  if text in headings:lines[n-1]=prefix+' '+headings[text]+'\n'
new=''.join(lines)
a,z=guard.structure(b),guard.structure(new)
for k in a:
 if a[k]!=z[k]:
  print('MISMATCH',k)
  if isinstance(a[k],list):
   for i,(x,y) in enumerate(zip(a[k],z[k])):
    if x!=y:print(i,repr(x),repr(y))
  else: print(a[k],z[k])
assert a==z,'Structure/inline code mismatch; no source written'
(guard.R/'source/CHANGELOG.md').write_text(new)
print('Applied',len(translations),'entry translations; structure exact')
print('Remaining CJK lines',[(n,l) for n,l in enumerate(new.splitlines(),1) if guard.CJK.search(l)])
