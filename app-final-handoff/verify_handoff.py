"""Bounded local byte reconciliation only. Never executes artifacts/peer code.
Path confinement and duplicate-key rejection follow the existing offline
acceptance validator's _read/_object rules; that validator is not imported.
Pins establish selected byte identities, not authenticity or runtime approval.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def object_unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def read_json(path):
    try:
        result = json.loads(path.read_bytes(), object_pairs_hook=object_unique)
    except (OSError, ValueError) as e:
        raise ValueError('invalid_json:' + str(path) + ':' + str(e)) from e
    require(type(result) is dict, 'json_not_object')
    return result


def confined(root, name):
    require(type(name) is str and name != '', 'invalid_path')
    rel = Path(name)
    require(not rel.is_absolute() and '..' not in rel.parts, 'unconfined_path')
    path = root
    require(not path.is_symlink(), 'symlink_root')
    for part in rel.parts:
        path /= part
        require(not path.is_symlink(), 'symlink_input:' + name)
    require(path.is_file(), 'missing_file:' + name)
    return path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_map(root, manifest):
    require(type(manifest) is dict and bool(manifest), 'invalid_manifest')
    for name, digest in sorted(manifest.items()):
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'invalid_hash')
        path = confined(root, name)
        require(sha(path) == digest, 'hash_mismatch:' + name)
    return len(manifest)


def required_gaps(events, required):
    terminals = {}
    for event in events:
        if event.get('Test') and event.get('Action') in ('pass', 'skip', 'fail'):
            terminals.setdefault(event['Test'], []).append(event['Action'])
    return sorted(name if name not in terminals else name + ':' + ','.join(terminals[name])
                  for name in required if terminals.get(name) != ['pass'])


def exact_files(root, manifest):
    actual = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink_tree:' + str(path))
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(manifest), 'file_set_mismatch:' + str(root))


def reconcile(root, pins):
    verify_map(root, pins['references'])
    load = lambda name: read_json(confined(root, name))
    admission = load('artex-worker-admission/source-manifest.json')
    baseline = load('artex-worker-admission/baseline-source-manifest.json')
    ui = load('artex-ui-asset-final/source-inventory.json')['files']
    original_ui = load('artex-native-app-final-build/guest-static-assets.json')['files']
    require(ui == original_ui, 'original_ui_mismatch')
    build = load('artex-ui-asset-final/local-build-receipt.json')
    canonical = hashlib.sha256(json.dumps(admission, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(canonical == build['frozen_tree_sha256'], 'build_source_pin_mismatch')
    require(len(admission) == build['source_files_verified'] and len(ui) == build['ui_count'], 'build_count_mismatch')
    overlay = {'server/webui/dist/' + k: v for k, v in ui.items()}
    require(build['overlay_only_delta'] == overlay, 'overlay_receipt_mismatch')
    require(not (set(admission) & set(overlay)), 'overlay_source_collision')
    maps = [('admission', 'artex-worker-admission/source', admission, True),
            ('baseline', 'artex-worker-operational/source', baseline, True),
            ('runner', 'artex-worker-assessment-runner', load('artex-worker-assessment-runner/runner-source-manifest.json'), False),
            ('ui', 'artex-ui-asset-final/assets', ui, True),
            ('generated_build_source', 'artex-ui-asset-final/build-source', admission | overlay, True)]
    counts = {}
    for label, directory, manifest, exact in maps:
        base = root / directory
        counts[label] = verify_map(base, manifest)
        if exact:
            exact_files(base, manifest)
    bins = build['binaries']
    preflight = confined(root, 'artex-ui-asset-final/bin/artex-native-preflight')
    require(sha(preflight) == bins['artex-native-preflight']['sha256'], 'preflight_mismatch')
    archive = confined(root, 'artex-ui-asset-final/bin/artex.gz')
    require(sha(archive) == bins['artex']['durable_compressed_artifact']['sha256'], 'gzip_hash_mismatch')
    h = hashlib.sha256()
    size = 0
    with gzip.open(archive, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            size += len(chunk)
            require(size <= bins['artex']['bytes'], 'gzip_expansion_exceeds_receipt')
            h.update(chunk)
    require(size == bins['artex']['bytes'] and h.hexdigest() == bins['artex']['sha256'], 'production_binary_mismatch')
    historical = confined(root, 'artex-ui-asset-final/report.json')
    try:
        read_json(historical)
    except ValueError as e:
        historical_error = str(e)
    else:
        raise ValueError('historical_invalid_report_unexpectedly_valid')
    require(load('artex-ui-asset-final/session-result.json')['success'] is True, 'export_not_successful')
    require(all(v['exit_code'] == 0 for v in bins.values()), 'historical_build_failed')
    events = []
    for name in ('20261119-215904-3998898.log', '20261119-215926-3999758.log'):
        path = confined(root, 'artex-worker-admission/receipts/' + name)
        events.extend(json.loads(line, object_pairs_hook=object_unique) for line in path.read_text().splitlines() if line.startswith('{'))
    required = ['TestNativeNormaNonStreamingEmptyTools', 'TestNativeGoPythonSynthetic']
    gaps = required_gaps(events, required)
    skips = [{'test': name, 'reason': ''.join(e.get('Output', '') for e in events if e.get('Test') == name and e.get('Action') == 'output')}
             for name in required if name + ':skip' in gaps]
    ledger = load('artex-standing-cost-ledger.json')
    proposal = load('artex-ui-asset-final/ledger-proposed.json')
    return {'local_byte_verification': 'PASS', 'runtime_accepted': False,
            'assessment_accepted': False, 'activation_authorized': False,
            'verified_file_counts': counts, 'source_pin': canonical,
            'production_binary_sha256': h.hexdigest(), 'production_binary_bytes': size,
            'historical_invalid_report': {'path': 'artex-ui-asset-final/report.json', 'sha256': sha(historical), 'error': historical_error},
            'required_test_gaps': gaps, 'required_skips': skips,
            'qualification_complete': False,
            'cost_ledger': {'last_settled_session': ledger['last_settled_session'],
                            'proposal_session': proposal['session_id'],
                            'proposal_additional_compute_estimate_usd': proposal['additional_compute_estimate_usd'],
                            'proposal_unsettled': proposal['session_id'] != ledger['last_settled_session'],
                            'ledger_modified': False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        result = reconcile(args.root, read_json(Path(__file__).with_name('pins.json')))
    except (OSError, ValueError, KeyError, TypeError, EOFError) as e:
        print(json.dumps({'local_byte_verification': 'FAIL', 'error': str(e), 'runtime_accepted': False}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0  # Byte reconciliation success is deliberately NOT runtime acceptance.


if __name__ == '__main__':
    raise SystemExit(main())
