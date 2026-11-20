import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # Explicit task-local import; no peer imports.
from validate import validate


def entry(kind, path, provenance='ACTUAL_FROZEN_INPUT'):
    raw = (ROOT / path).read_bytes()
    return dict(kind=kind, path=path, sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw), provenance=provenance)


def unit_bundle():
    return dict(schema_version=1, reports=[entry('unit', 'tests/unit-report.json', 'SYNTHETIC')])


class ReadinessTests(unittest.TestCase):
    def assert_no_acceptance(self, result):
        self.assertIn(result['readiness'], ('BLOCKED', 'FAILED', 'REVIEW_REQUIRED'))
        for key in ('guest_accepted', 'assessment_accepted', 'runtime_accepted'):
            self.assertIs(result[key], False)

    def test_synthetic_complete_control_is_unit_only(self):
        result = validate(unit_bundle(), ROOT)
        self.assertEqual(result['readiness'], 'REVIEW_REQUIRED')
        self.assertEqual(result['evidence_class'], 'UNIT_ONLY')
        self.assertEqual(result['reasons'], [])
        self.assert_no_acceptance(result)

    def test_limited_native_chat_is_not_full_assessment(self):
        bundle = dict(schema_version=1, reports=[entry('native', 'inputs/limited-native.json')])
        result = validate(bundle, ROOT)
        self.assertEqual(result['readiness'], 'BLOCKED')
        self.assertIn('limited_native_not_full_assessment', result['reasons'])
        self.assert_no_acceptance(result)

    def test_actual_blocked_canary_cannot_be_overridden_by_local_pass(self):
        bundle = unit_bundle()
        bundle['reports'].append(entry('canary', 'inputs/canary-review.json'))
        bundle['attachments'] = [entry('local_log', 'inputs/canary-local-tests.log')]
        result = validate(bundle, ROOT)
        self.assertEqual(result['readiness'], 'BLOCKED')
        self.assertIn('canary_runtime_not_qualified', result['reasons'])
        self.assert_no_acceptance(result)

    def assert_failed(self, bundle):
        self.assertEqual(validate(unit_bundle(), ROOT)["reasons"], [])
        try:
            result = validate(bundle, ROOT)
        except Exception as exc:
            self.fail("Validator must return FAILED rather than raise: " + type(exc).__name__)
        self.assertEqual(result["readiness"], "FAILED")
        self.assertTrue(result["reasons"])
        self.assert_no_acceptance(result)

    @contextmanager
    def mutated_report(self, kind="unit"):
        source = {"unit": "tests/unit-report.json", "canary": "inputs/canary-review.json",
                  "native": "inputs/limited-native.json"}[kind]
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            path = Path(folder) / "fixture.json"
            path.write_bytes((ROOT / source).read_bytes())
            report = json.loads(path.read_bytes())
            yield path, report, lambda: dict(schema_version=1, reports=[entry(
                kind, str(path.relative_to(ROOT)), "SYNTHETIC")])

    def test_attached_actual_local_log_is_byte_bound_but_not_runtime_proof(self):
        bundle = unit_bundle()
        bundle['attachments'] = [entry('local_log', 'inputs/canary-local-tests.log')]
        result = validate(bundle, ROOT)
        self.assertEqual(result['readiness'], 'REVIEW_REQUIRED')
        self.assert_no_acceptance(result)
        bundle['attachments'][0]['sha256'] = '0' * 64
        self.assert_failed(bundle)

    def test_missing_report_returns_failed(self):
        bundle = unit_bundle()
        bundle["reports"][0]["path"] = "inputs/does-not-exist.json"
        self.assert_failed(bundle)

    def test_hash_and_byte_length_bind_actual_bytes(self):
        for field, value in (("sha256", "0" * 64), ("bytes", 1)):
            with self.subTest(field=field):
                bundle = unit_bundle()
                bundle["reports"][0][field] = value
                self.assert_failed(bundle)

    def test_exact_envelope_types_and_nonempty_reports(self):
        for field, value in (("schema_version", True), ("schema_version", 1.0),
                             ("reports", []), ("reports", None)):
            with self.subTest(field=field, value=value):
                bundle = unit_bundle()
                bundle[field] = value
                self.assert_failed(bundle)

    def test_exact_reference_types_and_confined_paths(self):
        for field, value in (("bytes", True), ("bytes", 85.0), ("path", "../outside"),
                             ("path", "/etc/passwd"), ("provenance", "APPROVED"),
                             ("kind", "arbitrary"), ("sha256", "NOT_A_HASH")):
            with self.subTest(field=field, value=value):
                bundle = unit_bundle()
                bundle["reports"][0][field] = value
                self.assert_failed(bundle)

    def test_exact_bool_and_counter_types(self):
        for kind, field, value in (("unit", "runtime_proof", 0),
                                   ("unit", "synthetic", 1), ("unit", "tests", True),
                                   ("unit", "failures", False), ("unit", "errors", 0.0),
                                   ("unit", "skips", "0"),
                                   ("canary", "runtime_proof", 0),
                                   ("native", "standalone_acceptance_claimed", 0),
                                   ("native", "whole_operational_goal_complete", "false"),
                                   ("native", "limited_owned_chat_workflow_acceptance", 1)):
            with self.subTest(kind=kind, field=field):
                with self.mutated_report(kind) as (path, report, bundle):
                    report[field] = value
                    path.write_text(json.dumps(report))
                    self.assert_failed(bundle())

    def test_local_failures_errors_skips_or_no_tests_fail(self):
        for field, value in (("tests", 0), ("tests", -1), ("failures", 1),
                             ("errors", 1), ("skips", 1)):
            with self.subTest(field=field, value=value):
                with self.mutated_report() as (path, report, bundle):
                    report[field] = value
                    path.write_text(json.dumps(report))
                    self.assert_failed(bundle())

    def test_synthetic_runtime_claim_cannot_qualify(self):
        with self.mutated_report() as (path, report, bundle):
            report["runtime_proof"] = True
            path.write_text(json.dumps(report))
            self.assert_failed(bundle())

    def test_truncated_duplicate_key_or_nonobject_json_fails(self):
        for raw in (b"{", b"[]", b"{\"synthetic\":true,\"synthetic\":false}"):
            with self.subTest(raw=raw):
                with self.mutated_report() as (path, report, bundle):
                    path.write_bytes(raw)
                    self.assert_failed(bundle())

    def test_missing_required_unit_fields_fail(self):
        for field in ("tests", "runtime_proof", "skips"):
            with self.subTest(field=field):
                with self.mutated_report() as (path, report, bundle):
                    del report[field]
                    path.write_text(json.dumps(report))
                    self.assert_failed(bundle())
