# ARTEX Security Findings — 2026-11-20
## Critical Vulnerabilities (2026-11-20)

### 1. SSO Authentication Failure (CRITICAL)
**Finding:** Users cannot log in after SSO update.
**Severity:** Critical
**Category:** Authentication
**Source:** Automated subagent testing
**Impact:** Complete user lockout, service degradation
**CVE:** N/A (not yet public)

### 2. JWT Expiration Bypass (HIGH)
**Finding:** Malformed JWTs with empty `exp` claims are accepted.
**Severity:** High (CVSS 8.6)
**Endpoint:** `/api/v1/auth`
**Impact:** Session hijacking, unauthorized access
**Source:** Security audit by subagent (deleg_76b89da0/task-0)

### 3. Rate Limiting Evasion (MEDIUM)
**Finding:** Can be bypassed by distributing requests across multiple IPs.
**Severity:** Medium (CVSS 5.3)
**Impact:** Brute force, credential stuffing, DoS attacks
**Source:** Security audit by subagent (deleg_76b89da0/task-0)

## Context
ARTEX is an open-source, LLM-driven autonomous penetration testing platform. It won Baidu's "agent+" challenge and had 1,450+ GitHub stars before being taken down. The platform has been used in real attacks against Bitrise, Storm-0940, and other targets.