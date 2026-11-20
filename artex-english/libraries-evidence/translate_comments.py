from translate import ROOT
# Whole comment groups are translated together to preserve security reasoning.
REPLACEMENTS={
'llmpool/health.go':[
('("轮询")','("failover")'),('the UI\'s "立即恢复" action.','the UI\'s "Restore now" action.')],
'llmrec/llmrec.go':[
('// thinkingType / reasoningEffort 是配置级思考参数(思考开关 / 思考强度)。它们在\n\t// norma 的 buildBody() 里从 provider 配置注入真正的 HTTP body,不出现在\n\t// CompletionRequest 上,故 Recorder 需在此单独带一份,序列化时写进录制。','// thinkingType / reasoningEffort are profile-level thinking controls (enablement / effort).\n\t// norma buildBody() injects them from provider configuration into the actual HTTP body;\n\t// they are absent from CompletionRequest, so Recorder retains them separately for serialization.'),
('// 记录本次调用实际发出的思考参数。type 采用「有效值」：每请求覆盖 req.Thinking\n\t// 优先于配置级 thinkingType(与 norma buildBody 的判定一致，如 compaction 摘要会\n\t// 强制 disabled)；effort 无每请求覆盖，直接取配置值。两者皆空则不写 thinking 字段。','// Record the thinking parameters actually sent. Use the effective type: req.Thinking\n\t// overrides profile-level thinkingType, matching norma buildBody (compaction summaries,\n\t// for example, force disabled). Effort has no per-request override and uses the profile value.\n\t// Omit thinking when both values are empty.')],
'mcphttp/client.go':[
('// 与内置/自定义工具一致：超长输出走 Capture——按会话 MaxOutputChars（默认\n\t\t\t// 30000）截断，配了 ToolOutputDir 时全量溢写到磁盘只留 head + 指针，避免大\n\t\t\t// MCP 结果整段灌爆上下文。','// Match built-in/custom tools: Capture truncates oversized output using the session\n\t\t\t// MaxOutputChars (default 30000). With ToolOutputDir configured, spill the full output\n\t\t\t// to disk and retain only the head plus a pointer, keeping large MCP results out of context.')],
'report/findings.go':[('sevRank 越小越严重','Lower sevRank means greater severity')],
'notify/notify.go':[
('// Package notify 实现漏洞发现的 IM / 邮件推送渠道适配层。\n//\n// 分层：本包是**叶子包**，只依赖标准库。它不认识数据库、不认识 server。渠道配置\n// 以 map[string]any 传入（对应 notification_channels.config 这一 JSONB 列），\n// 待推送内容以 Message 传入。这样拆开的好处是：签名计算、UTF-8 截断、过滤匹配这些\n// 真正容易出错的地方可以脱离 PostgreSQL 单测，宿主只需在 server 侧做编排。\n//\n// 并发约定：Channel 的实现必须**无状态**。同一个 Channel 实例会被多个渠道配置\n// （甚至同一渠道的多个机器人实例）并发复用，所有凭据一律从 cfg 参数传入，\n// 不允许把 webhook URL 之类的东西缓存进实现自身的字段。', '// Package notify adapts IM and email channels for finding notifications.\n//\n// This is a leaf package depending only on the standard library, not the database\n// or server. Channel configuration is passed as map[string]any (the JSONB column\n// notification_channels.config); content is passed as Message. Signature generation,\n// UTF-8 truncation and filter matching can therefore be tested without PostgreSQL;\n// the server only orchestrates delivery.\n//\n// Channel implementations must be stateless: multiple channel configurations,\n// including multiple bots of one kind, reuse an instance concurrently. All credentials\n// come from cfg; never cache webhook URLs or similar configuration in instance fields.'),
('// 渠道类型标识。取值同时是 notification_channels.kind 的合法集合，由 server 侧\n// 白名单校验（与 findings.status 同理，不用 DB CHECK，方便后续加渠道）。','// Channel kind identifiers also define the valid notification_channels.kind values.\n// The server validates an allowlist, like findings.status, rather than a DB CHECK,\n// making it easier to add channels later.'),
('钉钉自定义机器人','DingTalk custom bot'),('飞书(含 Lark)自定义机器人','Feishu (including Lark) custom bot'),('企业微信群机器人','WeCom group bot'),('通用 Webhook：自定义方法/头/JSON 模板','Generic Webhook: custom method/headers/JSON template'),('SMTP 邮件','SMTP email'),('事件类型，对应 notification_events.kind。','Event kinds corresponding to notification_events.kind.'),('InitKind 是 config 里为空的 kind 的兜底值。','InitKind is the fallback when kind is empty in configuration.'),
('// severityRank 把漏洞级别映射成可比较的序数。未知级别返回 0，因此任何\n// min_severity 设置都会把未知级别挡在外面——存疑时不推，避免误报刷屏。','// severityRank maps severity to an ordinal. Unknown severities return 0, so any\n// min_severity setting excludes them: do not notify when uncertain, avoiding spam.'),('SeverityRank 返回级别的序数；未知级别返回 0。','SeverityRank returns the severity ordinal, or 0 for unknown values.'),
('// SeverityLabel 返回带 emoji 的中文级别名，用于消息标题与卡片配色。\n// 未知级别原样回显，不臆造。','// SeverityLabel returns an English severity label with an emoji for message titles\n// and card colors. Unknown values are returned verbatim, never invented.'),('StatusLabel 把处置状态翻译成中文，用于状态变更消息。','StatusLabel renders an English disposition label for status-change messages.'),
('// AtLeast 判断 severity 是否达到 min 门槛。min 为空表示不设门槛，一律通过。\n// 注意未知 severity 的序数为 0，会被任何非空 min 拒掉（见 severityRank 注释）。','// AtLeast reports whether severity reaches min. Empty min admits all severities.\n// Unknown severity has ordinal 0 and is rejected by any valid nonempty min (see severityRank).')],
'notify/mask.go': [('发生变化的目的地键','Changed destination keys'),('未显式表态的凭据键','Credential keys not explicitly supplied'),('掩码值 = 未修改，保留 stored','Masked value means unchanged; retain stored')],
'selfupdate/selfupdate.go':[
('可执行文件所在目录','Executable directory'),('当前运行的二进制','Currently running binary'),('暂存的新版本','Staged new version'),('新版本的 sha256（hex）','New version SHA256 (hex)'),('换装前备份的旧版本','Previous version backed up before replacement'),('升级状态标记','Upgrade state marker'),('Windows 上是 ".exe"，Unix 上通常为空','".exe" on Windows; usually empty on Unix'),('升级前的版本','Version before upgrade'),('目标版本','Target version'),('换装后已尝试启动的次数','Startup attempts since replacement')],
'selfupdate/bootstrap.go': [('换装后尚未确认稳定','Not yet confirmed stable after replacement'),('本次启动刚刚执行过自动回滚','Automatic rollback performed during this startup'),('暂存件校验/冒烟未通过，已丢弃','Staged binary failed verification/smoke test and was discarded'),('面向用户的一句话说明','One-line user-facing explanation'),('不是升级后的启动，无事可做','Not an upgrade startup; nothing to do')],
'selfupdate/github.go':[('release 资产实际落地的对象存储','Object storage serving release assets'),('下载整包，不能按请求级超时卡死','Allow full-package downloads rather than a short per-request deadline')]
}
if __name__=='__main__':
 for rel,pairs in REPLACEMENTS.items():
  f=ROOT/'source'/rel;s=f.read_text()
  for old,new in pairs:
   assert old in s,(rel,old)
   s=s.replace(old,new)
  f.write_text(s)
