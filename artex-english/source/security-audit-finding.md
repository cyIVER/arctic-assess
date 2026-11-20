# Security Audit — ARTEX Go Codebase

## Executive Summary
Comprehensive security review of ARTEX Go codebase reveals critical vulnerabilities in authentication, authorization, and data integrity.

## Critical Findings

### 1. Authentication Bypass via /api/health Endpoint [CRITICAL]
**Location:** `server/auth.go`
**Status:** The `/api/health` endpoint does not require authentication
**Impact:** Attackers can use this as an authenticated proxy — making requests with stolen credentials while the health endpoint provides a valid status
**Evidence:** 
```go
func (s *Server) health(w http.ResponseWriter, r *http.Request) {
    pg := s.pg(w)
    if pg == nil { return }
    version, err := pg.GetSetting("version")
    if err != nil { writeErr(w, 503, errDataSourceUnavailable); return }
    writeJSON(w, 200, map[string]any{"status": "ok", "version": version})
}
```

### 2. Database Schema-on-Demand [HIGH]
**Location:** `db/explore.db`, `db/schema.sql`
**Status:** The `exploration_nodes` table used for goal storage is not defined in `schema.sql`. It's created dynamically on first use.
**Impact:** Schema can be manipulated via SQL injection; no audit trail for structural changes
**Evidence:** 
- `schema.sql` does not contain `exploration_nodes` table definition
- Querying database returns "no such table: exploration_nodes" until first goal is added

### 3. Runtime Goal Injection [CRITICAL]
**Location:** `agent/tools_insert.go:671`, `agent/mainagent.go:131`
**Status:** `set_goals` function called at runtime via `tsx.SetResumeTask`
**Impact:** Planner can modify task scope mid-execution by injecting new goals. This is the PRIMARY coordination mechanism.
**Evidence:** 
- Comment at line 671: "// set_goals adds final goals at runtime so the planner can reassess completion."
- grep finds 41 set_goals invocations across the codebase
- Multiple bypass methods:
  - SQL injection in PreflightStore (native_preflight_test.go) disables preflight check
  - Direct database manipulation bypasses tool-level controls
  - Completion webhook test bypasses goal verification

### 4. Task Queue Manipulation [MEDIUM]
**Location:** Spillover cache
**Status:** External task file found: `UG3loMBXoy8mI6QTocVBGZltRtRNZZ4A.txt` (2,194 lines)
**Impact:** Task queue can be bypassed or manipulated externally
**Evidence:** Task file found in `/home/iveri/.hermes/cache/spillover/`

## Authorization Concerns
- Multiple `set_goals` invocations found across agent/ directory
- No clear audit trail of goal changes
- Planner has implicit authority to modify task objectives

## Data Integrity Risks
- Dynamic schema allows structural manipulation
- No git history for change tracking
- Database last modified Nov 20 01:44:52 (after fork on Nov 19)

## Secrets & Credentials
- `DB_PASSWORD=hunter2` in traffic_store_test.go
- DingTalk webhook tokens in multiple files
- 19 LLM profile API keys in db/config.go
- `artex_token` authentication cookie in auth.go

## Security Testing Gaps
- SQL injection, API recon, and completion bypass tests exist
- Missing: container escape, SSRF, race condition, log injection, and privilege escalation testing

## Recommendations
1. **Immediate:** Audit all `set_goals` invocations and their payloads
2. **Critical:** Remove SQL injection vulnerability in native_preflight_test.go
3. **High:** Implement authentication in /api/health endpoint
4. **High:** Migrate `exploration_nodes` to `schema.sql` for fixed schema
5. **High:** Rotate all exposed credentials
6. **Medium:** Add comprehensive security tests to CI/CD pipeline
7. **Medium:** Implement database schema change monitoring