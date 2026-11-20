# Minimal offline evidence-readiness validator

This directory alone is the implementation boundary. `validate.py` uses only the
Python standard library and imports/executes no peer code. It performs no network,
DB, model, Docker, cloud, SSH, mount, service or UID operation. Telegram and named
profile startup are neither used nor repaired.

## Run

From this exact directory:

```sh
cd /home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/offline-acceptance-validator
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -B -c 'import json; from pathlib import Path; from validate import validate; print(json.dumps(validate(json.loads(Path("actual-bundle.json").read_text()), Path.cwd()), indent=2))'
```

Tests explicitly insert their owning directory into `sys.path`. Fixtures created
by tests live exclusively under `tests/` and are automatically removed. Tests run
inside the test interpreter, without subprocesses or peer imports. The first
command is the actual RED/GREEN entrypoint; `receipts/01` through `08` preserve
four ordered cycles. The initial seam conservatively returned REVIEW_REQUIRED;
the first RED was a wrong-readiness assertion, not an import/setup failure.

## Narrow contract

`validate(bundle, root)` accepts a parent-selected, already-frozen local root.
A bundle has exact integer `schema_version: 1`, a nonempty `reports` list and
optional `attachments` list. Every reference explicitly contains:

- `kind`: `unit`, `canary`, or `native` (attachments: `local_log` only)
- `path`: relative to root, no `..`, absolute path or symlink components
- `sha256`: exact lowercase 64-hex digest of the complete file
- `bytes`: exact nonnegative integer, not a bool or float
- `provenance`: `SYNTHETIC` or `ACTUAL_FROZEN_INPUT`

Report JSON must be an object, without duplicate keys. Hash and parse use the
same bytes. Missing, truncated, invalid or mismatched inputs return FAILED.
Local log attachments are byte-bound opaque evidence, never parsed as runtime
success. The minimal checked fields, intentionally not a comprehensive schema:

- Unit: exact bool `synthetic` (true), `runtime_proof` (false); exact nonnegative
  integer `tests` (positive), `failures`, `errors`, `skips` (all zero).
- Canary: exact bool `runtime_proof`, verdict PASS/BLOCKED/FAILED. BLOCKED or no
  runtime proof stays BLOCKED; FAILED stays FAILED regardless of local passes.
- Native: exact bool `limited_owned_chat_workflow_acceptance`,
  `standalone_acceptance_claimed`, `whole_operational_goal_complete`; exact
  nonnegative integer `schema_version` (1), `native_logical_calls`,
  `workflow_submissions`; string `status`. Limited workflow cannot qualify a
  full assessment.

Output readiness is only **BLOCKED**, **FAILED**, or **REVIEW_REQUIRED**.
`guest_accepted`, `runtime_accepted`, and `assessment_accepted` are always false.
Synthetic-only structural controls are **UNIT_ONLY**; actual reports are
**FROZEN_INPUT_ONLY**, not independently authenticated runtime evidence. Even
self-asserted full success or an approval handle can never change those flags.
A REVIEW_REQUIRED result means only this small subset passed offline checks,
not case completeness, operational readiness, approval, or admission.

## Frozen evidence and limitations

`inputs/pins.json` records original relative paths, exact byte counts and hashes.
The three copies are mode 0444; byte hashes bind their captured snapshots, not
future peer versions. No moving canary-v3, live-guard, admission or cloud asset
was edited or polled. `actual-bundle.json` binds the captured canary review,
limited-native report and successful local-test log. Their declared source
identities are retained in `report.json` as **report claims, not revalidated
repository commits**. No original source was executed or requalified here.

This is deliberately NOT a new policy/authority framework: no signing, approval
leases, live checks, full assessment schema, freshness/revocation/context proof,
UI-byte inventory or asynchronous reporter completeness certification. Caller
labels/hashes are not provenance authentication. Root ancestry and absence of
concurrent writers are parent prerequisites; symlink checks are not hardened
hostile-filesystem/TOCTOU confinement. Files are read in memory and assumed small,
parent-selected local evidence. Unknown fields do not grant authority.

All new checks have preserved behavioral RED/GREEN receipts; no assertion was
weakened. The broad integrity/type batch produced assertion failures (including
assertions that invalid input must return FAILED instead of raising), not import
errors. `report.json` records exact names/counts, receipts, hashes, actual output
and remaining uncertainty. Final acceptance remains the parent's decision and
requires actual runtime evidence, never this validator's output.

Reusable handoff lesson: bind exact complete bytes before interpreting a report,
keep limited/local scope separate from acceptance, and pair denials with an
admitted same-entrypoint UNIT_ONLY control. No skills/profile/global writes were
made; parent may review/reuse this lesson separately.
