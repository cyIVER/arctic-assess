"""Stdlib-only offline evidence readiness. No authority or runtime admission."""
import hashlib
import json
from pathlib import Path
import re


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def _bools(report, fields):
    for field in fields:
        _require(type(report.get(field)) is bool, 'invalid_bool:' + field)


def _counts(report, fields):
    for field in fields:
        value = report.get(field)
        _require(type(value) is int and value >= 0, 'invalid_counter:' + field)


def _read(ref, root, attachment=False):
    _require(type(ref) is dict, 'invalid_reference')
    allowed = ('local_log',) if attachment else ('unit', 'canary', 'native')
    _require(ref.get('kind') in allowed, 'unknown_report_kind')
    _require(ref.get('provenance') in ('SYNTHETIC', 'ACTUAL_FROZEN_INPUT'),
             'unknown_provenance')
    _require(type(ref.get('bytes')) is int and ref['bytes'] >= 0, 'invalid_byte_count')
    digest = ref.get('sha256')
    _require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'invalid_hash')
    name = ref.get('path')
    _require(type(name) is str and name != '', 'invalid_path')
    relative = Path(name)
    _require(not relative.is_absolute() and '..' not in relative.parts, 'unconfined_path')
    path = root
    for part in relative.parts:
        path = path / part
        _require(not path.is_symlink(), 'symlink_input')
    _require(path.is_file(), 'missing_report')
    raw = path.read_bytes()  # Hash and parse the same bytes; no timestamp normalization.
    _require(len(raw) == ref['bytes'], 'byte_count_mismatch')
    _require(hashlib.sha256(raw).hexdigest() == digest, 'report_hash_mismatch')
    if attachment:
        return None  # Bound opaque local bytes; never a runtime pass signal.
    report = json.loads(raw, object_pairs_hook=_object)
    _require(type(report) is dict, 'report_not_object')
    return report


def validate(bundle, root):
    """Return BLOCKED/FAILED/REVIEW_REQUIRED; acceptance flags are always False.

    root must be a parent-selected frozen local directory. Hashes establish byte
    binding, NOT authenticity, provenance, freshness, approval or safe execution.
    Only the narrow documented fields are checked; this is not a full audit.
    """
    result = {'readiness': 'REVIEW_REQUIRED', 'evidence_class': 'UNIT_ONLY',
              'guest_accepted': False, 'assessment_accepted': False,
              'runtime_accepted': False, 'reasons': []}
    try:
        _require(type(bundle) is dict, 'invalid_bundle')
        _require(type(bundle.get('schema_version')) is int
                 and bundle['schema_version'] == 1, 'invalid_schema_version')
        refs = bundle.get('reports')
        _require(type(refs) is list and len(refs) > 0, 'missing_reports')
        root = Path(root).resolve(strict=True)
        attachments = bundle.get('attachments', [])
        _require(type(attachments) is list, 'invalid_attachments')
        for ref in attachments:
            _read(ref, root, attachment=True)
        for ref in refs:
            report = _read(ref, root)
            kind = ref['kind']
            if ref['provenance'] == 'ACTUAL_FROZEN_INPUT':
                result['evidence_class'] = 'FROZEN_INPUT_ONLY'
            if kind == 'unit':
                _bools(report, ('synthetic', 'runtime_proof'))
                _counts(report, ('tests', 'failures', 'errors', 'skips'))
                _require(report['synthetic'] is True
                         and ref['provenance'] == 'SYNTHETIC', 'unit_fixture_label_required')
                _require(report['runtime_proof'] is False, 'unit_cannot_claim_runtime')
                _require(report['tests'] > 0 and all(report[k] == 0 for k in
                         ('failures', 'errors', 'skips')), 'incomplete_or_failing_unit_evidence')
            elif kind == 'canary':
                _bools(report, ('runtime_proof',))
                _require(report.get('verdict') in ('PASS', 'BLOCKED', 'FAILED'), 'invalid_canary_verdict')
                if report['verdict'] == 'FAILED':
                    raise ValueError('canary_report_failed')
                if report['verdict'] != 'PASS' or report['runtime_proof'] is not True:
                    result['reasons'].append('canary_runtime_not_qualified')
            else:
                _bools(report, ('limited_owned_chat_workflow_acceptance',
                               'standalone_acceptance_claimed', 'whole_operational_goal_complete'))
                _counts(report, ('schema_version', 'native_logical_calls', 'workflow_submissions'))
                _require(report['schema_version'] == 1, 'invalid_native_schema_version')
                _require(type(report.get('status')) is str, 'missing_native_status')
                if (report['limited_owned_chat_workflow_acceptance'] is True
                        or report['standalone_acceptance_claimed'] is not True
                        or report['whole_operational_goal_complete'] is not True):
                    result['reasons'].append('limited_native_not_full_assessment')
        if result['reasons']:
            result['readiness'] = 'BLOCKED'
    except (ValueError, TypeError, OSError, RecursionError):
        # Do not disclose paths, document contents or OS diagnostics.
        result['readiness'] = 'FAILED'
        result['reasons'].append('invalid_or_unavailable_evidence')
    return result
