from pathlib import Path
import re,json
r=Path(__file__).resolve().parent.parent/'source/agent'
def replace(file,pairs):
 p=r/file;s=p.read_text()
 for a,b in pairs.items():
  assert a in s,(file,a);s=s.replace(a,b)
 p.write_text(s)
replace('prompt_test.go',{'中间产物输出规约':'Artifact output rules'})
replace('prompt_prefix_test.go',{'意图 id: 11':'Intent id: 11','开始执行上面这条意图：只做它、只产生事实、assets、finding、做完即停。':'Execute the intent above: do only this intent, produce only facts, assets, and findings, then stop.'})
replace('worker.go',{
'【你领到的意图（本次唯一任务：只做这一条、只产生事实、做完即停）】：':'[Assigned intent (your sole task this run: do only this intent, produce only facts, then stop)]:',
'意图 id: %d（写回 record_fact / report_finding 时传它）':'Intent id: %d (pass it to record_fact / report_finding)',
'【全局探索态势（只读，帮你把自己这条意图放进大局看）】：':'[Global exploration situation (read-only context for your assigned intent)]:',
'下面是整个任务当前的探索概况。用途有两个：一是知道别人已发现什么，别重复；二是让你探自己这条意图时，能联想到它和全局的关系。':'Below is the current task-wide exploration overview. Use it to avoid duplicating others\' discoveries and to understand how your assigned intent relates to the wider situation.',
'**发散是好事**：探本意图时尽管深想、多联想。唯一的界线是——别真的动手去执行别的意图（那是别的 worker 的事，由规划者调度）。但凡你联想到有价值的线索（跨资产的联动、疑似另一条利用链的入口、全局层面的可疑点），**务必写进 fact 交规划者**——这是你重要的产出，不是可有可无。宁可多报一条让规划者判断，也别自己咽下去。':'**Broad thinking is useful**: think deeply and connect clues while exploring this intent. The boundary is action: do not execute other intents (other workers handle them under the planner). **Record valuable leads as a fact for the planner**, including cross-asset connections, possible entry points to other exploitation chains, or task-wide suspicions. This is an important deliverable, not optional. Prefer sharing an extra lead for the planner to assess over withholding it.',
'本意图 asset_ids 对应的目标资产：':'Target assets corresponding to this intent\'s asset_ids:',
'开始执行上面这条意图：只做它、只产生事实、assets、finding、做完即停。':'Execute the intent above: do only this intent, produce only facts, assets, and findings, then stop.',
'开始执行 system 里领到的意图：只做它、只产生事实、assets、finding、做完即停。':'Execute the intent assigned in the system prompt: do only this intent, produce only facts, assets, and findings, then stop.',
'继续执行。':'Continue execution.',
'继续执行上一次人工对话输入的新意图。不要重复已经完成的动作。':'Continue executing the new intent from the previous human chat input. Do not repeat completed actions.',
'【人工对话输入的新意图】':'[New intent from human chat input]',
'请立即按这条人工输入执行，完成后再根据上下文决定原任务是否需要继续。':'Execute this human input immediately; afterward, use the context to decide whether the original task should continue.',
'请优先执行这条人工输入。':'Prioritize this human input.'})
replace('goals.go',{'任务目标：':'Task objective:','任务描述（背景信息，可能含靶标范围/flag 数量/交战说明；仅供参考，不要臆造其中未提及的内容）：':'Task description (background that may include target scope/flag count/engagement instructions; reference only, do not invent unmentioned details):'})
replace('constraints.go',{
'【操作约束（最高优先级，凌驾于下方一切探索/拓面启发式；每生成一条意图、每执行一个动作前都必须先自检是否违反，违反即不得进行）】：':'[Operation constraints (highest priority, overriding all exploration/expansion heuristics below; check before generating every intent or taking every action, and do not proceed if it would violate a constraint)]:',
'允许的操作：':'Allowed operations:', '禁止的操作：':'Prohibited operations:',
'（发现约束之外的新目标/新端口/新主机，不等于获得授权：除非它落在上述允许范围内，否则记为 out-of-scope 事实并跳过，不得为其派生意图或执行动作。）':'(Discovering a new target/port/host outside the constraints does not grant authorization: unless it falls within the allowed scope above, record an out-of-scope fact and skip it. Do not derive intents or take actions for it.)'})
# Translate each full string containing CJK in this file in source order.
p=r/'finding_workflow.go';s=p.read_text()
translations=[
'\n\n**Finding ID contract**: finding_id is the independent finding-record ID; finding_node_id is the exploration node ID. The id returned by list_findings / list_task_findings / node_detail / get_task_node_detail remains an exploration node ID; read the independent ID from finding_id in the same result. get_finding_traffic / bind_finding_traffic use the independent finding_id. The legacy update_finding_report finding_id argument still takes finding_node_id. Do not use the number on the first line of report_finding with evidence tools, or guess other numbers after an ID error.',
'\nBy default, the reporting agent verifies and binds traffic before writing the report. The reporter should retain verification commands, key output, existing real traffic IDs and their purpose in evidence so the reporting agent can check them against execution traces. Do not query extra packets merely for binding. Explicit immediate binding remains supported: traffic_refs or evidence_hint_id may carry verified references; the latter reads structured references from the specified hint in this task. If any reference is invalid, the entire report_finding call fails. TCP/no-packet cases do not require these optional arguments. Returned finding_id and finding_node_id identify the independent record and exploration node respectively.',
'\nWhen handing off a confirmed vulnerability, preserve verified traffic IDs, roles, notes, and order in the corresponding hint traffic_refs (top-level for a single hint, in the corresponding hints element for a batch), and describe the specific vulnerability it proves in text. Do not hand off only prose while discarding existing traffic references. Unverified candidates must not be passed as evidence.',
'\n\n**Traffic evidence handoff (optional)**: by default, the reporting agent performs automatic binding after the finding is recorded and before writing its report. Retain verification commands, key output, existing real traffic IDs and their purpose in evidence; include intent_id in task context for traceability. Do not query extra packets merely for binding. Auto / Planner reporting on behalf of an executor must retain existing references. add_hint / add_task_hint can hand off traffic_refs; explicit immediate binding remains compatible with report_finding traffic_refs / evidence_hint_id. Record TCP/no-packet cases normally. Never guess IDs or repeat probes solely to obtain packets.',
'\nFor platform chat without task context, do not call report_finding directly. Hand off to the corresponding existing task with add_task_hint, let its task agent record the finding, and verify the result with list_task_findings.',
'\nBefore declaring goals complete, finish reporting/handing off existing evidence from this run. Do not end the task or cancel workers merely because a text finding is recorded while evidence handoff remains incomplete. No-packet cases do not require waiting or forced capture.',
'\n\n**Automatic traffic association before reporting (enabled)**: verify and bind traffic for this triggered finding, then write the report. First obtain explicit finding_id and finding_node_id from report_finding JSON or get_task_node_detail / list_task_findings. Read the finding detail, corresponding intent execution trace, and existing evidence manifest, prioritizing real IDs handed off by the reporter. If verification was HTTP and traffic tools are available, filter candidates with traffic_search and verify each request/response supports the finding with traffic_get; domain and time only filter candidates, not prove ownership. Bind confirmed evidence in reproduction order with bind_finding_traffic(finding_id, traffic_refs), choosing baseline / proof / verification / supporting and explaining its purpose. Operate only on this finding: do not create duplicate findings or probe the target again. After successful binding, reread get_finding_traffic for the latest version, read the required bodies, and pass the version actually read as evidence_version to update_finding_report (whose finding_id still takes finding_node_id). Do not append existing bindings again. For TCP, uncaptured traffic, unavailable tools, or no exact match, skip automatic binding and write normally from text/command evidence, explaining why. Never guess to fill traffic gaps. Do not claim binding succeeded if it failed; retain existing evidence and explain missing bindings in the report.',
'Optional: verified traffic references supporting the specific vulnerability in this hint, preserving order. After handoff, report_finding can carry these references via evidence_hint_id.',
'Real traffic ID', 'What conclusion this traffic supports',
'evidence_hint_id=%d must identify a hint node in this task (inherited hints cannot be used directly for binding)'
]
pat=r'"(?:[^"\\]|\\.)*"'
matches=[m for m in re.finditer(pat,s) if re.search('[\u3400-\u9fff]',m.group())]
assert len(matches)==len(translations),(len(matches),len(translations))
for m,new in reversed(list(zip(matches,translations))): s=s[:m.start()]+json.dumps(new)+s[m.end():]
p.write_text(s)
