from pathlib import Path
import json
R=Path(__file__).resolve().parent.parent
blocks={
'auth.go': [
('下限与 setup 页的前端校验一致——校验只放在前端等于没放，直接打 API 就能','Match the setup page minimum; frontend-only validation can be bypassed by calling the API.'),
('绕过。上限是 bcrypt 的硬限制：超过 72 字节 GenerateFromPassword 会返回','The maximum is bcrypt\'s hard limit: above 72 bytes, GenerateFromPassword returns'),
('ErrPasswordTooLong，提前挡掉好过让用户收到一句含义不明的「密码加密失败」。','ErrPasswordTooLong. Reject early rather than returning an ambiguous hashing error.'),
('errDataSourceUnavailable 是密码相关读操作失败时统一的回复。这些 handler 绝不能','errDataSourceUnavailable is the uniform response when password-related reads fail. Never'),
('把"读不到"当成"没有设置"：authInit 曾因此在数据库报错时放行，让未认证请求覆盖','treat a failed read as an unset password: authInit previously admitted unauthenticated'),
('掉已有的管理员密码。','requests during database errors, allowing existing administrator passwords to be overwritten.'),
('validatePassword 返回空串表示通过，否则返回可直接展示给用户的中文原因。','validatePassword returns an empty string on success, otherwise a user-facing English reason.'),
('读失败必须回 503 而不是 initialized:false：前端在 initialized:false 时会把用户','Read failures must return 503, not initialized:false. That value sends users to /setup'),
('送到 /setup 去设置密码（login/page.tsx），把数据库故障包装成 200 等于把用户往','to set a password (login/page.tsx). Disguising database failures as HTTP 200 risks'),
('覆盖已有密码的路上推。','directing users toward overwriting an existing password.'),
('用 INSERT ... ON CONFLICT DO NOTHING 而不是 upsert：上面那次 GetSetting 只是','Use INSERT ... ON CONFLICT DO NOTHING rather than upsert. GetSetting above is only'),
('快速失败路径，真正"仅首次可设"的保证落在主键约束上。bcrypt 要跑几十毫秒，','a fast-fail check; the primary-key constraint guarantees first-time-only initialization. bcrypt'),
('这期间别的请求完全可能先把密码设好，而读检查本身也可能因故障而失效。','takes tens of milliseconds, allowing concurrent initialization; reads may also fail.')],
'workspace.go':[('目录在前，各自按名称排序。','Directories first; sort each group by name.')],
'skill_zip.go':[
('Go 的 archive/zip 只内置 Store(0) 和 Deflate(8) 两种解压器，遇到别的方法会返回','Go archive/zip only includes Store(0) and Deflate(8); other methods return'),
('"zip: unsupported compression algorithm"。压缩软件在非默认档位下经常写出别的方法','"zip: unsupported compression algorithm". Nondefault archive settings often use other methods'),
('(7-Zip 的 bzip2、WinZip 的 zstd)，所以这里把纯 Go 能解的两种补上；真的解不了的','(7-Zip bzip2, WinZip zstd), so register the two supported pure-Go decompressors here.'),
('(Deflate64 / LZMA / XZ / PPMd / 加密包) 在解压前就报出中文提示，而不是把底层','Unsupported formats (Deflate64 / LZMA / XZ / PPMd / encrypted archives) are rejected before'),
('错误原样甩给用户。','extraction with a user-facing message rather than a raw low-level error.'),
('PKWARE 早期给 zstd 分配的编号','Early PKWARE method number assigned to zstd'),
('macOS 打包残留','macOS packaging metadata'),
('zipEntryName returns the entry path as UTF-8. Windows 上的 7-Zip / WinRAR / 资源管理器','zipEntryName returns the entry path as UTF-8. Windows 7-Zip / WinRAR / Explorer may'),
('在不置 UTF-8 标志位时会把中文文件名按 GBK 写进 zip，Go 原样保留这些字节，于是名字','write Chinese filenames as GBK without the UTF-8 flag. Go preserves those bytes, which'),
('既不是合法 UTF-8 也过不了路径校验 —— 这里按 GBK 兜底解码。','are not valid UTF-8 and fail path validation; fall back to GBK decoding here.')],
'chatupload.go':[
('Abs 是落盘的绝对路径(m.dir 已是绝对)。建任务前暂存(scope=staging)时前端要用它把','Abs is the absolute on-disk path (m.dir is already absolute). For pre-task staging'),
('提示词写进描述;task/session 走 composeAgentMessage 在后端拼路径,不依赖此字段。','(scope=staging), the frontend uses it in the description. task/session compose paths in the backend via composeAgentMessage, without this field.'),
('(建任务前暂存:任务尚无 ID,','(pre-task staging: no task ID yet,'),
('文件先落这里,前端按返回的 abs 绝对路径写进任务描述)','files are stored here first; the frontend puts the returned absolute abs path in the task description)')],
'dto.go':[
('可选任务名称;空=未命名','Optional task name; empty means unnamed'),('运行中 Worker 数（state=running 的意图）','Running worker count (intents with state=running)'),
('该任务已登记的漏洞数（findings 表，按严重度分档）','Registered findings for this task (findings table, grouped by severity)'),('资产覆盖度功能开关(创建时定)','Asset coverage feature flag (fixed at creation)'),
('FindingSeverityDTO 是任务列表里按严重度分档的漏洞计数（严重/高/中/低）。','FindingSeverityDTO counts task-list findings by severity (critical/high/medium/low).'),
('意图假删除(state=\'deleted\')时的删除原因','Deletion reason for a soft-deleted intent (state=\'deleted\')'),
('总览「目标管理」','overview goal-management'),('总览「约束管理」','overview constraint-management'),('漏洞名称;为空时前端回退展示 vulnclass','Finding name; frontend falls back to vulnclass when empty'),
('详细报告(Markdown);仅详情接口返回,列表为空','Detailed Markdown report; only returned by detail endpoints, empty in lists'),('global 发现 page','global findings page'),
('绑定的 LLM 配置;null=跟随任务/全局','Bound LLM profile; null follows task/global configuration'),('P3 触发后处理策略(仅自定义 agent 有意义)。','P3 post-trigger handling policy (only meaningful for custom agents).'),
('轮询(故障转移)参数：priority 越大越先被选中(激活配置恒为链首)；','Failover parameters: higher priority is selected first (the active profile always leads the chain).'),
('pool_exclude=true 则不作为故障转移目标，但仍可被 agent/任务显式绑定。','pool_exclude=true excludes a failover target but still allows explicit agent/task binding.'),
('收发模式：true=流式(SSE) | false=非流式。没有 omitempty —— false 必须出现在','Transport mode: true=streaming (SSE), false=non-streaming. No omitempty: false must be'),
('响应里，否则前端读不到「非流式」，开关会回落成默认的流式。','present in responses or the frontend falls back to streaming.'),
('单次回复输出上限(0=不发送，由服务端默认值决定)，以及它用哪个请求字段名','Per-response output limit (0=omit, using server default), plus its request field name'),
("(''=max_tokens | 'max_completion_tokens'，仅 openai 格式有意义)。","(''=max_tokens | 'max_completion_tokens'; only meaningful for openai format)."),
('自定义会话头名：非空时每次请求带该 HTTP 头，头值=当前会话/意图的 session id。','Custom session header: when nonempty, each request includes this HTTP header with the current conversation/intent session id.'),
("''=不发送。用于按 session-id 头做提示缓存/粘性路由的网关。","''=omit. For gateways using a session-id header for prompt caching or sticky routing."),
('本配置对重试的覆盖(建连/空响应/同 provider 安全窗口)。每项 attempts:','Profile retry overrides (connection/empty response/same-provider safe window). Per-layer attempts:'),
('0=继承全局策略 | -1=关闭该层重试 | >0=次数；interval_ms: 0=用默认指数退避 |','0=inherit global policy | -1=disable that retry layer | >0=attempt count; interval_ms: 0=default exponential backoff |'),
('>0=改用该固定毫秒间隔。全 0 = 完全跟随全局，即历史行为。','>0=fixed interval in milliseconds. All zeros follow the global policy, preserving historical behavior.')]
}
receipt=[]
for name,changes in blocks.items():
 p=R/'source/server'/name;text=p.read_text()
 for a,b in changes:
  if a not in text: raise ValueError((name,a))
  text=text.replace(a,b);receipt.append({'path':'server/'+name,'old':a,'new':b})
 p.write_text(text)
(R/'server-evidence/comment-translations.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print('Translated',len(receipt),'comment segments')
