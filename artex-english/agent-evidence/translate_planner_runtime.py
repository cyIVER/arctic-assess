from pathlib import Path
import re,json
p=Path(__file__).resolve().parent.parent/'source/agent/planner.go';s=p.read_text()
values=[
'\n\n[Your planning todos (retained across wake-ups, written last round)]:\n',
'Proceed from this list: dispatch only the next steps whose prerequisites are completed or whose required facts already exist. Update the list with TodoWrite, marking fact-satisfied steps completed. Do not redispatch steps already pending/in_progress.',
'\n\n[Actual changes triggering this round (read first, then decide whether to add directions)]:',
'\n- The human (main agent) added a goal: %s — a new unmet goal; add exploration directions if no corresponding intent exists.',
'\n- The human (main agent) added %d goals: %s — all are new unmet goals; add directions for each not yet covered by an intent.',
'\n- The human (main agent) added a strategic hint: %s — attached to the exploration graph; adjust/add directions accordingly if not already covered.',
'\n- The human (main agent) added %d strategic hints: %s — all attached to the exploration graph; adjust/add directions for each accordingly.',
'\n- The human deleted this goal: %s — it is removed; reassess remaining goals/directions and do not dispatch intents for it.',
'\n- The human changed a goal from [%s] to [%s] — adjust exploration to the new goal; stop dispatching the old direction if no longer applicable.',
'\n- The worker for intent #%d (%s) reported a finding: %s',
'\n- The user deleted intent #%d. Intent: %s; deletion reason: %s. This intent is deleted and will no longer execute; replan accordingly.',
'\n- The worker for intent #%d (%s) finished. Conclusion: %s',
'; new fact ids produced by this intent: %s ',
'\n(Use node_detail / get_worker_output / list_findings for complete detail.)',
'(failed to retrieve output)', '(this work has no output record yet)',
' ... (truncated; see get_worker_output for full content)',
'\n\n[This round\'s situation (prefetched graph_overview, identical to calling that tool; retrieve detail with node_detail/list_facts as needed)]:\n',
'\n\n[Task final wrap-up (special instructions for this round, overriding normal planning above)]:',
'the graph changed',
'A concrete change just occurred (see Actual changes triggering this round below). Plan the next step accordingly:',
'This wake-up is a **periodic heartbeat/no concrete change signal**: the graph may not have changed. Review running intents as well: use steer_work for prolonged lack of progress or drift, kill_work when the entire direction is wrong, then assess goals and decide whether to add directions:',
'This is a **periodic heartbeat** wake-up, and **there are no open or running intents**: no active workers or queued directions, so exploration has stalled. You **must** produce one or more goal-advancing intents this round that **do not duplicate** existing graph intents (zero intents is not allowed). First assess from the situation below whether the goal is achieved; if not, add directions immediately:',
'\n\nAssess the goals from the situation above. Mark them individually with prove_goal only when **genuinely achieved** (objective results obtained/target vulnerability confirmed). **Hard minimum: if the objective is unmet and there are no open or running intents (frontier_open=0 and running_intents empty), you must produce at least one intent advancing it this round. No active work or queued direction exists to wait for; zero intents stalls the task. Only when open/running intents are making progress or the objective is achieved may this round produce no new intents.**'
]
ms=[m for m in re.finditer(r'"(?:[^"\\]|\\.)*"',s) if re.search('[\u3400-\u9fff]',m.group())];assert len(ms)==len(values),(len(ms),len(values))
for m,new in reversed(list(zip(ms,values))):s=s[:m.start()]+json.dumps(new)+s[m.end():]
s=s.replace('strings.Join(ev.Goals, "；")','strings.Join(ev.Goals, "; ")').replace('strings.Join(ev.Hints, "；")','strings.Join(ev.Hints, "; ")')
p.write_text(s)
