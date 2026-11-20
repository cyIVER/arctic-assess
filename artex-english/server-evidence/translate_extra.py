from pathlib import Path
import json,re
R=Path(__file__).resolve().parent.parent
pairs='''纠偏Message must not be empty|Intervention message must not be empty
LLM 配置不存在|LLM profile does not exist
LLM 配置未设置 API Key|LLM profile has no API Key
LLM 配置格式或参数无效|Invalid LLM profile format or parameters
任务 LLM 配置链额度已耗尽|Task LLM profile chain budget exhausted
全局配置|Global configuration
没有可用的 LLM 配置|No available LLM profile
worker 尚未就绪|Worker is not ready
fk_violation(23503,父exploration不存在)|fk_violation(23503,parent exploration does not exist)
%w: 意图 %d 当前没有运行中的 work（可能已结束或未被领取）|%w: intent %d has no running work (it may have finished or not been claimed)
%w: 意图 %d 正在执行 %s 操作|%w: intent %d is performing operation %s
等待意图 %d %s 收尾: %w|Waiting for intent %d %s to settle: %w
%w: 意图 %d 不再是 %s 状态|%w: intent %d is no longer in state %s
意图 %d 当前没有运行中的 work（可能已结束或未被领取）|Intent %d has no running work (it may have finished or not been claimed)
【空转提醒】你上一轮只输出了思考过程，既没有给出正文回复，也没有调用任何工具，|[Empty-turn reminder] Your previous turn produced only reasoning, with neither a response nor any tool call, 
这一轮等于没有产出。请直接执行你刚才想好的下一步：要么调用工具，要么给出结论文字。不要重复思考。|so it produced no actionable output. Execute the next step you already planned: either call a tool or provide your conclusion. Do not repeat your reasoning.
【规划者实时纠偏】|[Live planner intervention]
（这是规划者对本意图的即时指令；本次工具调用未执行，请据此调整下一步。若与你当前打算冲突，以此为准。）|(This is the planner's immediate instruction for this intent; this tool call was not executed. Adjust your next step accordingly. If it conflicts with your current plan, follow this instruction.)
目标已全部达成，直投意图已执行完毕，任务结束|All goals achieved and directly submitted intents completed; task finished
第 %d 轮规划|Planning round %d
任务超时收尾·终局判定(第 %d 轮)|Task timeout wrap-up: final assessment (round %d)
action 必须是 block 或 allow|action must be block or allow
已截断|truncated
skill 已存在: |Skill already exists: 
该 key 已存在(内置或自定义工具)|This key already exists (built-in or custom tool)
该 key 已存在: |This key already exists: 
【任务 #%d %s（目标：%s）】|[Task #%d %s (goal: %s)]
【任务 #%d %s】|[Task #%d %s]
【本会话合并了任务 #%d 的 %d 条触发事件，请一并处理】|[This conversation combines %d trigger events for task #%d; process them together]
── 触发 %d ──|-- Trigger %d --
合并触发 · task#%d · %d 条|Merged triggers · task#%d · %d events
【本会话合并了队列中的 %d 条触发事件（共 %d 个任务），请一并处理】|[This conversation combines %d queued trigger events across %d tasks; process them together]
── 触发 %d（task#%d）──|-- Trigger %d (task#%d) --
合并触发 · 全部 · %d 条|Merged triggers · all · %d events
（出错：| (Error: 
服务端当前时间（每次运行实时刷新；可与固定起始时间相减判断已用时长）|Current server time (refreshed on every run; subtract a fixed start time to determine elapsed time)
服务端数据根目录（所有任务/会话产物的根；各 agent 实际写盘在其下的子目录，如 <DataDir>/<taskID>）|Server data root (root for all task and conversation artifacts; agents write in subdirectories such as <DataDir>/<taskID>)'''
# Preserve printf argument order: task id precedes event count.
pairs=pairs.replace('[This conversation combines %d trigger events for task #%d; process them together]','[Task #%d: this conversation combines %d trigger events; process them together]')
D=dict(x.split('|',1) for x in pairs.splitlines())
changes=[]
for p in (R/'source/server').glob('*.go'):
 text=p.read_text()
 def conv(m):
  token=m.group()
  for a,b in sorted(D.items(),key=lambda x:-len(x[0])):
   if a in token: token=token.replace(a,b);changes.append({'path':str(p.relative_to(R/'source')),'old':a,'new':b})
  return token
 new=re.sub(r'"(?:[^"\\\n]|\\.)*"',conv,text)
 if new!=text:p.write_text(new)
(R/'server-evidence/translations-extra.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
print(len(changes),'literal replacements')
