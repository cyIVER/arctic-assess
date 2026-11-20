# Codex coordinator → ARTEX/Qwen operator: bounded DVWA task

This document is an operator-side planning artifact, not an ARTEX system prompt, credential, approval lease or runtime result. Use only after the exact owner/operator authorizes the live run and the private target is installed and independently verified reachable from ARTEX's isolated application network.

## Target binding (to be filled from actual live readback)
- Target identity: reviewed DVWA image digest and observed Docker container ID: **PENDING**.
- Exact private origin: **PENDING** (expected an internal DNS name on the owned app network, never a public URL/IP).
- Root scope: only the target origin above. No other host, port, metadata endpoint, file outside task workspace, private subnet exploration or public internet.
- One task, one operator worker, no competing live task, max 30 minutes inclusive of setup/cleanup under the original provider STOP; no hidden retries/fallback.

## High-level task for ARTEX UI (after filling origin)
"Assess only the explicitly owned DVWA training application at TARGET_ORIGIN. Autonomously identify and verify at least one non-destructive security finding using your own choice of in-scope investigation steps. Create a finding with actual, reproducible request/response evidence and a remediation explanation; then produce a task report that includes it. Do not brute-force authentication, upload files, change passwords or configuration, run SQL writes or destructive payloads, execute shell commands on the target, escalate host/container privileges, enumerate neighboring services, access cloud metadata, follow links away from TARGET_ORIGIN, or access any other host. Preserve actual tool-call/result, target HTTP evidence, finding ID and report identity as separate receipts. If a required gate or observation fails, stop and state the narrower result rather than inventing a finding."

The literal TARGET_ORIGIN must be replaced only with the live verified allowlisted internal origin. Reject if ARTEX's ordinary tool path permits off-origin requests or host-level effects without an external enforcement boundary. A model instruction alone is not confinement. Do not seed a fake intent/result/finding merely to make UI activity appear complete.

## Codex role and verification
Codex/JARVIS defines task/scope, reviews independent target and model tool receipts, checks UI state and normal report persistence, diagnoses source defects locally and decides whether evidence supports an E2E pass. Qwen alone is selected as the ARTEX execution model via the original OpenAI-compatible provider. Neither model may change approval scope or provider STOP. No Codex OAuth credentials enter the ARTEX runtime.

Before declaring success: verify actual app-authenticated task/exploration identity; selected Qwen route, one structured tool call and tool-result consumption through ARTEX, real target-only effect in an independent DVWA HTTP log/ledger, user-visible English UI activity, a durable finding/report if produced, model-off restart and same-record readback, no off-target effect, and exact cloud STOP with retained disk. If any part is missing, report the narrower observed milestone.
