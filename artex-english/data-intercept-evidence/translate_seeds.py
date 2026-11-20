from pathlib import Path
import json
R=Path(__file__).resolve().parent.parent;p=R/'source/db/db.go';s=p.read_text()
m={
'目标拆解':'Goal decomposition','把渗透任务目标拆解成若干独立、可验证的子目标。':'Decompose penetration-test goals into independent, verifiable subgoals.',
'任务描述（测试对象/背景）':'Task description (test target/background)','测试 example.com 站点':'Test the example.com site',
'"规划"':'"Planner"','读取态势、判定目标，只在确有未覆盖的新方向时补充探索意图（每任务一个规划循环）。':'Read the situation and assess goals; add exploration intents only for genuinely uncovered directions (one planning loop per task).',
'任务总目标':'Overall task goal','拿下 example.com 的管理员权限':'Obtain administrator access on example.com','资产计数/类型分布摘要(可选)':'Asset counts/type distribution summary (optional)',
'"主"':'"Main"','人机接口：观察进展，把人的意图落成 hint 或高优先级意图。':'Human interface: observe progress and convert human intent into hints or high-priority intents.',
'当前任务目标':'Current task goal','开局态势摘要(可选)':'Initial situation summary (optional)','已确认漏洞摘要(可选)':'Confirmed findings summary (optional)',
'"执行"':'"Worker"','领取一条意图执行，把发现的事实/漏洞写回知识图谱后停止。':'Claim and execute one intent, write discovered facts/findings to the knowledge graph, then stop.',
'记录代理地址(驱动 if 双文案)':'Recording proxy address (selects conditional prompt text)','worker 自我标识(可选)':'Worker self-identifier (optional)',
'平台操作助手：用工具管理任务(建/看/暂停/给提示)与资产，并可创建/修改 skill、自定义工具、MCP。':'Platform assistant: use tools to manage tasks (create/view/pause/hint) and assets, and create/edit skills, custom tools, and MCP servers.',
'"渗透测试"':'"Penetration test"','独立渗透 agent：一人从侦察→找攻击面→深入利用→验证→收尾走完整条链，自己规划、自己执行、自己对抗式验证。':'Independent penetration-test agent: run the full reconnaissance, attack-surface discovery, exploitation, verification, and wrap-up chain with self-directed planning, execution, and adversarial verification.',
'[内置] 政府网站':'[Built-in] Government website','[内置] 教育网站':'[Built-in] Education website',
'[内置] 递归强制删除 rm -rf':'[Built-in] Recursive forced deletion rm -rf','禁止执行递归强制删除（rm -rf / rm --recursive），可能永久损坏系统或靶机环境':'Recursive forced deletion (rm -rf / rm --recursive) is prohibited; it may permanently damage the system or target environment',
'[内置] 删除系统关键目录':'[Built-in] Delete critical system directories','禁止删除系统关键路径':'Deleting critical system paths is prohibited',
'[内置] 磁盘格式化 mkfs':'[Built-in] Disk formatting mkfs','禁止格式化磁盘（mkfs）':'Disk formatting (mkfs) is prohibited',
'[内置] 覆写磁盘设备 dd':'[Built-in] Overwrite disk devices dd','禁止使用 dd 覆写磁盘设备':'Overwriting disk devices with dd is prohibited',
'[内置] Fork 炸弹':'[Built-in] Fork bomb','禁止执行 Fork 炸弹':'Fork bombs are prohibited',
'[内置] 关机 / 重启':'[Built-in] Shutdown / reboot','禁止执行关机或重启命令':'Shutdown and reboot commands are prohibited',
'[内置] 杀死全部进程':'[Built-in] Kill all processes','禁止 kill -9 -1 或 killall -9（杀死所有进程）':'kill -9 -1 or killall -9 (killing all processes) is prohibited',
'[内置] 磁盘擦除 shred / wipe':'[Built-in] Disk erasure shred / wipe','禁止对磁盘设备执行 shred/wipe 擦除':'Erasing disk devices with shred/wipe is prohibited',
'[内置] 清空防火墙规则':'[Built-in] Clear firewall rules','禁止清空防火墙规则（iptables -F / nft flush）':'Clearing firewall rules (iptables -F / nft flush) is prohibited',
'[内置] SQL DROP DATABASE / TABLE / SCHEMA':'[Built-in] SQL DROP DATABASE / TABLE / SCHEMA','禁止执行 DROP 操作，可能不可逆地销毁数据库对象':'DROP is prohibited; it may irreversibly destroy database objects',
'[内置] SQL TRUNCATE':'[Built-in] SQL TRUNCATE','禁止执行 TRUNCATE，可能清空数据表所有数据':'TRUNCATE is prohibited; it may clear all table data',
'[内置] MongoDB drop / dropDatabase':'[Built-in] MongoDB drop / dropDatabase','禁止执行 MongoDB drop 操作':'MongoDB drop operations are prohibited',
'[内置] Redis FLUSHALL / FLUSHDB':'[Built-in] Redis FLUSHALL / FLUSHDB','禁止执行 Redis FLUSHALL / FLUSHDB，可能清空全部缓存数据':'Redis FLUSHALL / FLUSHDB is prohibited; it may clear all cached data',
'[内置] curl / wget 发送 DELETE 请求':'[Built-in] curl / wget DELETE requests','禁止通过 curl/wget 发送 HTTP DELETE 请求，可能删除目标系统数据':'HTTP DELETE via curl/wget is prohibited; it may delete target-system data',
'[内置] Python HTTP 客户端 DELETE（requests/httpx/aiohttp）':'[Built-in] Python HTTP client DELETE (requests/httpx/aiohttp)','禁止使用 Python HTTP 客户端发送 DELETE 请求':'Sending DELETE requests using Python HTTP clients is prohibited',
'[内置] 脚本中声明 HTTP DELETE 方法（JS/通用）':'[Built-in] Script HTTP DELETE method (JS/general)','禁止在脚本中声明并发送 HTTP DELETE 请求':'Declaring and sending HTTP DELETE requests in scripts is prohibited',
'[内置] 批量清空 / 清除接口路径':'[Built-in] Bulk clear / erase endpoint paths','禁止调用批量清空或销毁类接口（/clear /wipe /flush /purge 等）':'Bulk-clear or destruction endpoints (/clear /wipe /flush /purge etc.) are prohibited',
'[内置] 破坏性系统命令':'[Built-in] Destructive system commands','破坏性命令被拒绝（rm -rf / / mkfs / dd / fork bomb / 关机重启 / 覆写磁盘设备）':'Destructive command denied (rm -rf / / mkfs / dd / fork bomb / shutdown or reboot / disk overwrite)',
'[内置] 数据外泄管道':'[Built-in] Data exfiltration pipeline','疑似数据外泄管道被拒绝（命令输出经 curl/wget/nc 外传）':'Suspected data exfiltration pipeline denied (command output sent via curl/wget/nc)',
'禁止调用删除类接口（/delete /remove /unlink /erase 等），不论使用哪种 HTTP 方法——多数应用的删除接口用 GET/POST 就能触发，同样会真实删除目标数据':'Deletion endpoints (/delete /remove /unlink /erase etc.) are prohibited regardless of HTTP method; many applications trigger deletion through GET/POST and still delete real target data',
'// Package db is the PostgreSQL data source for ARTEX (取代旧 graph 单文件 SQLite)。':'// Package db is the PostgreSQL data source for ARTEX (replacing the old single-file graph SQLite store).',
'// 它打开连接、应用 schema、并 seed 内置 agent 与变量目录。':'// It opens connections, applies the schema, and seeds built-in agents and variable catalogs.'}
# Preserve V3 legacy name as its persisted identity/idempotence key, not new display prose.
for a,b in m.items():s=s.replace(a,b)
p.write_text(s)
# Extend only the existing source classifier; do not rewrite historical reason text or add a migration.
p=R/'source/db/schema.sql';s=p.read_text();s=s.replace("WHEN reason LIKE '[模型]%' THEN 'model'", "WHEN reason LIKE '[Model]%' OR reason LIKE '[模型]%' THEN 'model'");p.write_text(s)
(R/'data-intercept-evidence/seed-translations.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
print('Translated seed display strings; preserved V3 legacy identity and all patterns/settings/limits')
