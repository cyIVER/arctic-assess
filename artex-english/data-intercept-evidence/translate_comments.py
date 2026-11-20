from pathlib import Path
import json
R=Path(__file__).resolve().parent.parent
m={
'规则 message 或模型判定理由(前缀 [模型])':'Rule message or model decision reason (current or legacy model prefix)',
'建行时的默认交互式 shell 开关；ON CONFLICT 不覆盖用户后续手动开关':'Default interactive-shell setting on insert; ON CONFLICT preserves later user toggles',
'建行时的单次 run 墙钟上限(秒)；nil=用种子默认(1200)，0=不限时':'Initial per-run wall-clock limit in seconds; nil uses seed default (1200), 0 means unlimited',
'LLM 出站代理(http/https/socks5);空=用环境变量':'LLM outbound proxy (http/https/socks5); empty uses environment variables',
'绑定的 LLM 配置;nil=跟随任务/会话 pin,再回退全局激活':'Bound LLM profile; nil follows task/conversation pin, then global active profile',
'单次运行最大轮次;0=不限制':'Maximum turns per run; 0 means unlimited',
'worker 单次运行墙钟上限(秒);0=不限制':'Worker per-run wall-clock limit in seconds; 0 means unlimited',
'是否启用网络搜索(受系统全局开关门控)':'Enable web search (gated by the global system switch)',
'是否启用交互式 shell(持久 PTY 会话工具族)':'Enable interactive shell (persistent PTY session tool family)',
'收尾提示词(超时/步数耗尽时的 settlement 提示);空=用代码内置默认':'Wrap-up prompt for timeout/turn exhaustion; empty uses the built-in default',
'收尾阶段自身的轮数预算;0=用代码内置默认(按 agent)':'Wrap-up turn budget; 0 uses the per-agent built-in default',
'llm_profile_id 可空:未绑定时为 NULL':'llm_profile_id is nullable: NULL when unbound',
'仅意图假删除(state=\'deleted\')时非空':'Nonempty only for soft-deleted intents (state=\'deleted\')',
'可选任务名称;空=未命名':'Optional task name; empty means unnamed',
'父任务 id(编排 spawn 记录;空=顶层)':'Parent task ID (orchestration spawn record; empty for top-level tasks)',
'进入终态(done/failed/timeout)的时刻;非终态为 nil':'Time of entering a terminal state (done/failed/timeout); nil otherwise',
'0=不限时':'0 means no time limit',
'首次真正开始运行的时刻(非 created_at);nil=尚未运行':'First actual run start time (not created_at); nil if not started',
'= first_run_at + timeout_seconds;nil=不限或未运行':'= first_run_at + timeout_seconds; nil if unlimited or not started',
'已盖过章：不动':'Already stamped: leave unchanged',
'漏洞名称(可读标题);为空时前端回退展示 VulnClass':'Finding name (display title); empty falls back to VulnClass in the frontend',
'详细报告(Markdown);仅 GetFinding 填充,列表查询不带':'Detailed Markdown report; populated only by GetFinding, omitted from list queries',
'待处理':'Pending','处理中':'In progress','已确认(真实漏洞,未修复)':'Confirmed (real finding, not fixed)','已处理':'Resolved','已修复':'Fixed','误报':'False positive','忽略':'Ignored','重复':'Duplicate','风险接受':'Risk accepted',
'严重':'Critical','高':'High','中':'Medium','低':'Low',
'提交成功后是 no-op':'No-op after successful commit',
'最老的待发投递距今毫秒数':'Age of the oldest pending delivery in milliseconds',
'被拒原因（不含资产标识）；Allowed=true 时为空':'Denial reason (excluding asset identity); empty when Allowed=true',
'可读原因':'Human-readable reason',
'自定义工具执行规格(kind!=builtin)':'Custom tool execution specification (kind!=builtin)',
'schema 延迟(走 SearchExtraTools/ExecuteExtraTool)':'Deferred schema (via SearchExtraTools/ExecuteExtraTool)',
'各触发条件的独立用户消息':'Separate user message for each trigger condition',
'选中的工具 key 列表(DB 存 JSON 文本)':'Selected tool keys (stored as JSON text)',
'入参(JSON 文本)':'Input arguments (JSON text)','返回内容':'Returned content','工具返回是否为错误':'Whether the tool result is an error',
'任务 id(字符串形式;空/非法 = 不按任务筛选)':'Task ID (string; empty/invalid disables task filtering)',
'名称/类型/摘要/证据/报告正文的模糊检索关键词':'Fuzzy-search keyword for name/type/summary/evidence/report body',
'子树里所有资产 id':'All asset IDs in the subtree','只要「未关联资产」的发现':'Include only findings without linked assets','选中的节点在当前筛选下不存在 → 结果恒空':'Selected node absent under current filters: always empty results',
'资产覆盖度功能是否开启；false 时其余字段为零值':'Whether asset coverage is enabled; false leaves all other fields at zero values',
'0 → 范围未锚定':'0 means scope not anchored','范围内资产数':'Number of in-scope assets','已测(约)':'Tested (approximate)','覆盖度；分母 0 时 null':'Coverage; null when denominator is zero','按资产类型的 总数/已测':'Total/tested counts by asset type'
}
# Comment-only substitutions: never change code, string evidence or fixture values.
receipts=[]
for p in (R/'source/db').glob('*.go'):
 if p.name.endswith('_test.go'):continue
 lines=p.read_text().splitlines(keepends=True);out=[]
 for i,line in enumerate(lines,1):
  # Inline comment split is restricted to lines whose comment contains CJK.
  if '//' in line:
   code,comment=line.split('//',1);original=comment
   for a,b in sorted(m.items(),key=lambda x:-len(x[0])):
    if len(a)<=4:
     if comment.strip()==a:comment=comment.replace(a,b)
    else:comment=comment.replace(a,b)
   if comment!=original:receipts.append({'path':str(p.relative_to(R/'source')),'line':i,'old':original.rstrip(),'new':comment.rstrip()})
   line=code+'//'+comment
  out.append(line)
 if ''.join(out)!=p.read_text():p.write_text(''.join(out))
(R/'data-intercept-evidence/comment-translations.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
print('Translated',len(receipts),'comment lines')
