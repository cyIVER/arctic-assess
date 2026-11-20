from translate import ROOT,apply
TEXT='''未分类|Unclassified
漏洞发现汇总报告|Finding Summary Report
生成时间|Generated at
发现总数|Total findings
## 摘要|## Summary
严重等级|Severity
| 数量 |/| Count |
_无匹配的漏洞。_|_No matching findings._
漏洞明细|Finding details
类别|Class
状态|Status
所属任务|Task
发现时间|Discovered at
证据：|Evidence:
详细报告|Detailed report
## 概述|## Overview
## 证据|## Evidence
名称|Name
概述|Overview
流量证据数量|Traffic evidence count
流量证据ID|Traffic evidence IDs
关联流量证据|Linked traffic evidence
证据版本：%d；绑定数量：%d。|Evidence version: %d; bindings: %d.
证据已变更，详细报告待更新。|Evidence has changed; the detailed report needs updating.
证据 #%d · %s|Evidence #%d · %s
，状态码 %d|, status code %d
请求报文|Request message
响应报文|Response message
渗透测试报告|Penetration Test Report
未命名任务|Unnamed task
任务目标|Task goal
（未指定）|(Not specified)
确认发现：**%d** 个|Confirmed findings: **%d**
资产：|Assets: 
## 发现|## Findings
_本次未确认漏洞。_|_No vulnerabilities confirmed in this run._
跳过自举：%v|Bootstrap skipped: %v
暂存的新版本未通过校验，已丢弃，继续运行当前版本：%v|Staged version failed verification and was discarded; continuing with current version: %v
新版本校验失败，已丢弃：|New version failed verification and was discarded: 
换装失败，继续运行当前版本：%v|Replacement failed; continuing with current version: %v
换装失败：|Replacement failed: 
写升级标记失败（失去自动回滚能力）：%v|Failed to write upgrade marker (automatic rollback unavailable): %v
已换装到 %s，退出以重启（exit %d）|Replaced with %s; exiting to restart (exit %d)
新版本连续 %d 次启动失败，且回滚失败：%v|New version failed to start %d times consecutively, and rollback failed: %v
新版本启动失败且回滚失败：|New version failed to start and rollback failed: 
新版本连续 %d 次启动失败，已回滚到 %s，退出以重启（exit %d）|New version failed to start %d times consecutively; rolled back to %s and exiting to restart (exit %d)
新版本启动失败，已回滚到 %s|New version failed to start; rolled back to %s
更新升级标记失败：%v|Failed to update upgrade marker: %v
新版本启动中（第 %d/%d 次尝试），稳定运行后将确认升级|Starting new version (attempt %d/%d); the upgrade will be confirmed after stable operation
清除升级标记失败：%v|Failed to clear upgrade marker: %v
新版本运行稳定，升级完成（上一版本保留为 %s）|New version is stable; upgrade complete (previous version retained as %s)
读取校验和: %w|Read checksum: %w
计算校验和: %w|Compute checksum: %w
SHA256 不匹配（下载损坏或被篡改）|SHA256 mismatch (download corrupted or tampered with)
赋予执行权限: %w|Set executable permissions: %w
冒烟测试超时（新二进制无响应）|Smoke test timed out (new binary unresponsive)
冒烟测试失败: %v: %s|Smoke test failed: %v: %s
清理旧备份 %s: %w|Clean up old backup %s: %w
备份当前版本: %w|Back up current version: %w
装入新版本失败(%v)，且恢复当前版本失败: %w|Failed to install new version (%v), and failed to restore current version: %w
装入新版本: %w|Install new version: %w
没有可回滚的备份 %s: %w|No backup available for rollback %s: %w
移走失败的版本: %w|Move failed version aside: %w
恢复旧版本: %w|Restore old version: %w
没有可回滚的上一版本（|No previous version available for rollback (
 不存在）| does not exist)
上一版本无法执行，拒绝回滚: %w|Previous version cannot execute; refusing rollback: %w
移走当前版本: %w|Move current version aside: %w
装入上一版本: %w|Install previous version: %w
回滚后整理备份失败（不影响运行）：%v|Failed to organize backup after rollback (operation unaffected): %v
未知版本|Unknown version
在线更新已禁用：本地构建不检查或下载远程版本|Online updates disabled: local builds do not check or download remote versions
重定向次数过多|Too many redirects
拒绝非 HTTPS 地址: %s|Non-HTTPS URL refused: %s
拒绝非 GitHub 域名: %s|Non-GitHub domain refused: %s
访问 GitHub 失败（可在系统设置里配置全局代理）: %w|Failed to access GitHub (a global proxy can be configured in system settings): %w
GitHub 接口限流（每小时 60 次），请稍后再试|GitHub API rate limit (60 requests per hour); try again later
仓库 %s 不可访问或尚未发布正式版本|Repository %s is inaccessible or has no stable release yet
GitHub 返回 %d|GitHub returned %d
解析 Release 失败: %w|Failed to parse Release: %w
Release 缺少 tag|Release is missing tag
定位可执行文件: %w|Locate executable: %w
该版本没有提供 %s/%s 的发布包（缺少 %s）|This version has no release package for %s/%s (missing %s)
获取校验和清单…|Fetching checksum manifest…
%s 未收录 %s，拒绝安装未经校验的二进制|%s does not include %s; refusing to install an unverified binary
下载 %s（%s）…|Downloading %s (%s)…
校验 SHA256…|Verifying SHA256…
SHA256 不匹配：期望 %s，实际 %s（下载损坏或被篡改）|SHA256 mismatch: expected %s, got %s (download corrupted or tampered with)
解压并冒烟测试…|Extracting and running smoke test…
新版本无法在当前系统上运行: %w|New version cannot run on this system: %w
计算新二进制校验和: %w|Compute new binary checksum: %w
写入校验和: %w|Write checksum: %w
暂存新版本: %w|Stage new version: %w
警告：写入升级标记失败，本次升级将没有自动回滚保护|Warning: failed to write upgrade marker; this upgrade will have no automatic rollback protection
新版本已就绪，正在重启…|New version ready; restarting…
该 Release 没有 %s，无法校验完整性，拒绝升级|Release has no %s; integrity cannot be verified, so upgrade refused
下载 %s: %w|Download %s: %w
读取 %s: %w|Read %s: %w
%s 内容为空或格式无法识别|%s is empty or its format is unrecognized
创建临时文件: %w|Create temporary file: %w
下载中断: %w|Download interrupted: %w
落盘失败: %w|Failed to persist to disk: %w
下载不完整：期望 %d 字节，实际 %d 字节|Incomplete download: expected %d bytes, got %d bytes
打开发布包: %w|Open release package: %w
写出新二进制: %w|Write new binary: %w
解压 %s: %w|Extract %s: %w
发布包内的可执行文件超过 %s，拒绝解压|Executable in release package exceeds %s; extraction refused
发布包内的 %s 是空文件|%s in release package is empty
发布包里没有找到 %s|%s not found in release package
程序目录 %s 不可写，无法自动更新（请检查权限或改用手动升级）: %w|Program directory %s is not writable; automatic update unavailable (check permissions or upgrade manually): %w
下载中 %s / %s|Downloading %s / %s'''
if __name__=='__main__':
 pairs=[l.split('|',1) for l in TEXT.splitlines() if l and not l.startswith('|')]
 print(apply(pairs,['report','selfupdate']))
 for f in (ROOT/'source/report').glob('*.go'):
  if f.name.endswith('_test.go'):continue
  s=f.read_text().replace('**：','**: ').replace('PoC / Evidence:','PoC / Evidence:').replace('**PoC / Evidence:**','**PoC / Evidence:**').replace('**PoC / 证据：**','**PoC / Evidence:**').replace('| 数量 |','| Count |').replace(' 个\\n','\\n').replace('"、"','", "')
  s=s.replace('{"critical", "严重"}, {"high", "高危"}, {"medium", "中危"}, {"low", "低危"}', '{"critical", "Critical"}, {"high", "High"}, {"medium", "Medium"}, {"low", "Low"}')
  f.write_text(s)
