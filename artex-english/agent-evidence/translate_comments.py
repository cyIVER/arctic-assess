from pathlib import Path
r=Path(__file__).resolve().parent.parent/'source/agent'
p=r/'wrapup.go';s=p.read_text()
pairs={
'// 收尾提示词(wrap-up / settlement prompt):当 agent 因【步数耗尽(MaxTurns)】或\n// 【超时(run_seconds/MaxDuration)】被终止时,SDK 的 settlement 阶段会注入这段提示,\n// 让 agent 先把已识别但未写回的内容落库、再输出一句总结,避免烂尾。':'// The SDK injects the wrap-up/settlement prompt when the agent exhausts its\n// turn budget (MaxTurns) or times out (run_seconds/MaxDuration), so it persists\n// identified but unsaved results and ends with a one-sentence summary.',
'// 每个 agent 的收尾提示词可在后台按需覆盖(存 agents.wrapup_prompt),留空则用这里的\n// 内置默认。仅【提示词正文】可编辑;禁用哪些工具、收尾自身给几轮预算属代码固定策略。':'// Admins can override each agent wrap-up prompt in agents.wrapup_prompt; empty\n// uses the built-in default. Only prompt text is editable here; disabled tools\n// and settlement budget policy are controlled by code.',
'// 内置默认收尾提示词,按 agent key 索引。worker 复用历史上硬编码的 settleWrapUpPrompt\n// (定义在 worker.go),planner/mainagent 各有一版;未命中的(自定义 agent)走通用兜底。':'// Built-in wrap-up prompts by agent key. Workers reuse settleWrapUpPrompt in\n// worker.go; planner/mainagent have their own. Unknown/custom keys use a generic fallback.',
'// wrapupTurnDefaults: 各 agent 收尾阶段【自身】的轮数预算内置默认(可被后台 >0 覆盖)。\n// 均给 10 轮,保证收尾阶段有足够步数落库。未命中走 genericWrapupTurns。':'// wrapupTurnDefaults gives each settlement phase its own turn budget (positive\n// admin values override it). All get 10 turns to persist results; unknown keys\n// use genericWrapupTurns.',
'// ---------- 任务级超时收尾词（见 docs/任务级超时与收尾设计.md）----------':'// ---------- Task-level timeout wrap-up (see docs/任务级超时与收尾设计.md) ----------',
'// 与 per-run 收尾词是【两套】：per-run 是"你这一次 run 的预算用完了"；任务超时是\n// "整个任务到点、即将结束"。语义常相反（尤其 planner：per-run 说"别停继续规划"，\n// 任务超时说"到点停止规划、做最后判定"）。只给 worker/planner 配置。':'// Separate from per-run wrap-up: one run exhausting its budget does not mean\n// the whole task is ending. Planner semantics differ: continue planning after\n// a run, but stop dispatching and assess final goals at task timeout. Worker/planner only.',
'// WrapupTaskTimeoutOverride / …TurnsOverride：任务超时收尾词与轮数的 DB 覆盖\n// （wire 到 agents.task_timeout_wrapup_prompt / _max_turns，仅 worker/planner）。':'// WrapupTaskTimeoutOverride / ...TurnsOverride provide DB overrides for task\n// timeout prompts and budgets (agents.task_timeout_wrapup_prompt / _max_turns; worker/planner only).',
'// TaskTimeoutWrapupDefault 返回某 agent 的任务超时内置默认收尾词（供后台占位/恢复默认）。':'// TaskTimeoutWrapupDefault returns the built-in task timeout prompt for admin placeholders/reset.',
'// 未配置(mainagent/chat)返回空串':'// Empty for unconfigured mainagent/chat.',
'// resolveTaskTimeoutWrapup：DB 覆盖(非空) > 内置默认。空串表示该 agent 无任务超时词\n// （非 worker/planner），此时调用方应回退 per-run 词。':'// resolveTaskTimeoutWrapup prefers nonempty DB overrides to built-ins. Empty\n// means no task timeout prompt (not worker/planner); callers fall back to per-run.',
'// 默认沿用 per-run 轮数':'// Default to the per-run turn budget.',
'//   - clamped=true  → 本次 run 被任务 deadline 夹逼：因 Timeout 收尾=任务到点→任务超时词；\n//     因 MaxTurns 收尾=夹逼窗口内步数先耗尽、任务还剩几分钟→回落 per-run 词。\n//   - clamped=false → 任务还早：两种 reason 都用 per-run 词（即退化为 wrapupSettlement）。':'//   - clamped=true: this run is bounded by the task deadline. Timeout means\n//     task expiry; MaxTurns means turns ran out first, so use the per-run prompt.\n//   - clamped=false: both reasons use the per-run prompt (wrapupSettlement).',
'// 交给 harness 的 PromptByReason 在收尾时按【实际】reason 现场挑，无 build 时错配。':'// PromptByReason lets the harness select from the actual settlement reason, not a build-time guess.',
'// 兜底(也是非 clamped 时两种 reason 的取值)':'// Fallback; both reasons use this when not clamped.',
'// 任务到点':'// Task deadline reached.',
'// 步数先耗尽、任务还剩时间':'// Turns exhausted while task time remains.'
}
for a,b in pairs.items():assert a in s,a;s=s.replace(a,b)
p.write_text(s)
# Translate shared comment fragments only, preserving referenced document paths.
for name in ['worker.go','goals.go','mainagent.go','planner.go','prompt.go']:
 p=r/name;s=p.read_text().replace('段 [A]','section [A]').replace('段 [B]','section [B]').replace('段 [C]','section [C]').replace('中间产物输出规约','artifact output rules')
 p.write_text(s)
