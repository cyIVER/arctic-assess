PENETRATION TESTING METHODOLOGY
=================================

SCOPE:
- Target: ARTEX E2 API (v2.1.0)
- Test Period: 2025-03-22 (4 hours)
- Focus Areas: Authentication, Rate Limiting, Injection, Data Exfiltration

---

PHASE 1: RECONNAISSANCE
Tools: subfinder, amass, waybackarchive
- Enumerate subdomains and API endpoints
- Discover rate limiting thresholds through automated probing
- Identify information disclosure in error messages

PHASE 2: AUTHENTICATION TESTING
Tests:
1. Brute force: 10,000 credential guesses per minute from a single IP
2. Token theft: Intercept JWT during login (MITM) and reuse
3. Token bypass: Submit malformed tokens (empty exp, algorithm manipulation)
4. Session fixation: Force user token while maintaining attacker session
5. Privilege escalation: Exploit token to access admin endpoints

PHASE 3: RATE LIMITING TESTING
Tools: abuser, custom Go bot
- Single IP: Send 70 requests/minute (just above threshold) - expect 429
- Multiple IPs: Distribute 60 req/min across 12 IPs - should be allowed
- User-based: Register 10 accounts, use each for 6 req/min - total 60 req/min
- Result: Bypass achieved via multi-IP distribution

PHASE 4: INJECTION TESTING
- SQL Injection: Test all input fields (usernames, passwords, search params)
- XSS: Reflected in error messages, webhook callbacks
- Command Injection: In file upload and webhook payload fields

PHASE 5: DATA EXFILTRATION
- Enumerate all accessible endpoints without authentication
- Test for broken object level authorization (BOLA)
- Check for sensitive data in error messages, cache, analytics

---

TOOLS USED:
- Burp Suite Professional (proxy, scanner, intruder)
- OWASP ZAP
- subfinder, amass (reconnaissance)
- abuser (rate limiting testing)
- JWT.io (token manipulation)
- sqlmap (SQL injection)

---

FINDINGS SUMMARY:
- 1 CRITICAL: JWT expiration bypass (Phase 2, Test 3)
- 1 HIGH: Rate limiting bypass via multi-IP distribution (Phase 3)
- 5 MEDIUM: Information disclosure in error responses (Phase 1)
- 3 LOW: Weak password policy, missing CSP header

---
This methodology was adapted from PTES (Penetration Testing Execution Standard) and OWASP Testing Guide.