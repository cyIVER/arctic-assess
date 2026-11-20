from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent.parent
# Exact textual substitutions: only human prose, never schema/tool/route keys.
PAIRS='''环境变量 ARTEX_PG_DSN|environment variable ARTEX_PG_DSN
配置文件 |configuration file 
 (database 字段)| (database fields)
未找到数据库配置：environment variable ARTEX_PG_DSN 未设置，且configuration file %s 未提供 database（dsn 或 host/user/dbname）。请创建该配置文件或设置环境变量后重试|Database configuration not found: environment variable ARTEX_PG_DSN is unset and configuration file %s does not provide database (dsn or host/user/dbname). Create this configuration file or set the environment variable and retry
dnsx 初始化失败，DNS 解析停用：%v|dnsx initialization failed; DNS resolution disabled: %v
队列已满，丢弃任务 kind=%d id=%d|Queue full; dropping job kind=%d id=%d
证据正文校验失败: %s|Evidence body verification failed: %s
正文不完整: 预期 %d 字节，读取 %d 字节|Incomplete body: expected %d bytes, read %d bytes
原始流量正文哈希不匹配|Raw traffic body hash mismatch
side 必须为 request 或 response|side must be request or response
归档证据快照元数据哈希不匹配|Archived evidence snapshot metadata hash mismatch
LLM 轮询：所有配置均不可用|LLM failover: all profiles unavailable
配置 %q(%s) 已熔断：%s|Profile %q(%s) circuit open: %s
LLM 故障转移：%q(%s) → %q(%s)，原因：%s|LLM failover: %q(%s) → %q(%s), reason: %s
轮询链已耗尽(%d 个配置全部失败)，最后错误：%s|Failover chain exhausted (all %d profiles failed), last error: %s
缺少 Webhook 地址|Missing Webhook URL
Webhook 地址无效: %w|Invalid Webhook URL: %w
查看详情|View details
在平台中查看全部|View all in platform
解析钉钉响应失败: %w (%s)|Failed to parse DingTalk response: %w (%s)
钉钉返回错误 %d: %s|DingTalk returned error %d: %s
解析 Webhook 地址失败: %s|Failed to parse Webhook URL: %s
地址无法解析（%s）|Cannot parse URL (%s)
只支持 http/https，收到 %q|Only http/https are supported, got %q
缺少主机名|Missing hostname
拒绝投递到本机/链路本地地址 %s（如确需投递到本机服务，设置 %s=1）|Delivery to local/link-local address %s refused (if delivery to a local service is required, set %s=1)
缺少 SMTP 服务器地址|Missing SMTP server address
SMTP 端口无效（应为 1-65535）|Invalid SMTP port (must be 1-65535)
缺少发件人地址|Missing sender address
至少需要一个收件人地址|At least one recipient address is required
STARTTLS 失败: %w|STARTTLS failed: %w
拒发凭据：连接未加密。请启用 TLS，或改用 465 端口(隐式 TLS)，或把「启用 TLS」勾上 (%w)|Refusing to send credentials over an unencrypted connection. Enable TLS, use port 465 (implicit TLS), or select Enable TLS (%w)
SMTP 认证失败: %w|SMTP authentication failed: %w
发件人 %s 被拒|Sender %s rejected
收件人 %s 被拒|Recipient %s rejected
SMTP DATA 失败: %w|SMTP DATA failed: %w
写入邮件正文失败: %w|Failed to write email body: %w
提交邮件失败: %w|Failed to submit email: %w
连接 SMTP 服务器失败: %w|Failed to connect to SMTP server: %w
SMTP 握手失败: %w|SMTP handshake failed: %w
(未命名漏洞)|(Unnamed finding)
解析飞书响应失败: %w (%s)|Failed to parse Feishu response: %w (%s)
飞书返回错误 %d: %s|Feishu returned error %d: %s
最低级别 %q 无效，可选：low / medium / high / critical，或留空表示不限|Invalid minimum severity %q; choose low / medium / high / critical, or leave empty for no limit
近 %d 分钟新增 %d 个漏洞|%d minutes: %d new findings
新增 %d 个漏洞|%d new findings
状态变更|Status change
**类型**：|**Type**: 
**资产**：|**Assets**: 
**摘要**：|**Summary**: 
<b>类型</b>：|<b>Type</b>: 
<b>资产</b>：|<b>Assets</b>: 
<b>摘要</b>：|<b>Summary</b>: 
**Status change**：|**Status change**: 
<b>Status change</b>：|<b>Status change</b>: 
无法解析目标地址 %q|Cannot resolve destination address %q
重定向次数过多|Too many redirects
拒绝跨主机重定向（%s → %s）|Cross-host redirect refused (%s → %s)
构造请求体失败: %w|Failed to build request body: %w
请求地址非法: %s|Invalid request URL: %s
请求失败: %s|Request failed: %s
读取响应失败: %w|Failed to read response: %w
对方限流或超时 (HTTP %d): %s|Remote rate limit or timeout (HTTP %d): %s
对方服务异常 (HTTP %d): %s|Remote server error (HTTP %d): %s
对方拒绝请求 (HTTP %d): %s|Remote request rejected (HTTP %d): %s
(地址不可解析)|(Unparseable address)
未知错误|Unknown error
漏洞汇总 · 共 %d 条|Finding digest · %d total
漏洞通知|Finding notification
（本条显示前 %d 条，其余 %d 条将在下一条消息继续）| (showing the first %d; the remaining %d will follow in the next message)
目标地址（|Destination fields (
）已变更，请同时重新填写凭据字段（|) changed; re-enter credential fields (
）：填入新值，或显式留空表示不再需要凭据。|): provide a new value, or explicitly leave empty if credentials are no longer needed. 
原凭据只对旧地址有效，继续沿用等于把它交给新地址。|The original credentials were authorized only for the old destination; reusing them would disclose them to the new destination.
渠道类型 %q 未注册|Channel kind %q is not registered
字段 %s 的内容里含掩码标记 %q：该字段只能整体留空表示沿用、或整体提交新值，不能在结构体内部夹带掩码占位|Field %s contains mask marker %q: leave the entire field empty to retain its value, or submit a complete new value; embedded mask placeholders are not allowed
🔴 严重|🔴 Critical
🟠 高危|🟠 High
🟡 中危|🟡 Medium
🔵 低危|🔵 Low
待处理|Pending
处理中|In progress
已确认|Confirmed
已处理|Resolved
已修复|Fixed
误报|False positive
忽略|Ignored
重复|Duplicate
风险接受|Risk accepted
 等 | (
 个\"| total)\"
缺少 Bot Token|Missing Bot Token
缺少 Chat ID|Missing Chat ID
API 地址无效: %w|Invalid API URL: %w
解析 Telegram 响应失败: %w (%s)|Failed to parse Telegram response: %w (%s)
Telegram 限流: %s|Telegram rate limit: %s
Telegram 返回错误 %d: %s|Telegram returned error %d: %s
拼接 API 地址失败（API 地址：%s）|Failed to construct API URL (API URL: %s)
（显示前 %d 条，其余 %d 条下一条继续）| (showing the first %d; the remaining %d will follow in the next message)
近 %d 分钟 · %s|Last %d minutes · %s
缺少目标 URL|Missing destination URL
目标 URL 无效: %w|Invalid destination URL: %w
不支持的方法 %s（可用 GET/POST/PUT/PATCH）|Unsupported method %s (use GET/POST/PUT/PATCH)
请求体模板语法错误: %w|Request body template syntax error: %w
请求体模板渲染结果不是合法 JSON|Rendered request body template is not valid JSON
渲染请求体模板失败: %w|Failed to render request body template: %w
解析企业微信响应失败: %w (%s)|Failed to parse WeCom response: %w (%s)
企业微信限流 %d: %s|WeCom rate limit %d: %s
企业微信返回错误 %d: %s|WeCom returned error %d: %s'''

def apply(pairs,dirs):
 changes=[]
 for d in dirs:
  for f in (ROOT/'source'/d).rglob('*.go'):
   if f.name.endswith('_test.go'):continue
   s=f.read_text();old=s
   for a,b in pairs:s=s.replace(a,b)
   if s!=old:f.write_text(s);changes.append(str(f.relative_to(ROOT)))
 return changes
if __name__=='__main__':
 pairs=[l.split('|',1) for l in PAIRS.splitlines() if l]
 # Keep replacements specific; presentation list separators are not protocol delimiters.
 pairs=[(a,b) for a,b in pairs if a not in [' 等 ',' 个"']]
 print(apply(pairs,'config enrich evidence llmpool notify'.split()))
 f=ROOT/'source/notify/render.go';s=f.read_text().replace('strings.Join(assets, "、")','strings.Join(assets, ", ")').replace('strings.Join(assets[:limit], "、") + " 等 " + itoa(len(assets)) + " 个"','strings.Join(assets[:limit], ", ") + " (" + itoa(len(assets)) + " total)"');f.write_text(s)
 f=ROOT/'source/notify/mask.go';s=f.read_text().replace('strings.Join(e.Changed, "、")','strings.Join(e.Changed, ", ")').replace('strings.Join(e.Missing, "、")','strings.Join(e.Missing, ", ")');f.write_text(s)
