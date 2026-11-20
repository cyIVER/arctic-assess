"""Synthetic stdlib fixtures only; no peer code or runtime execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import verify_handoff as v


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'a').write_bytes(b'actual')
        self.manifest = {'a': hashlib.sha256(b'actual').hexdigest()}

    def test_valid_actual_map(self):
        self.assertEqual(v.verify_map(self.root, self.manifest), 1)

    def test_missing_file(self):
        (self.root / 'a').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            v.verify_map(self.root, self.manifest)

    def test_hash_mismatch(self):
        (self.root / 'a').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            v.verify_map(self.root, self.manifest)

    def test_malformed_manifest(self):
        for manifest in ({'a': 'not-a-hash'}, {'../a': '0' * 64}, [], {}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                v.verify_map(self.root, manifest)

    def test_symlink_rejected(self):
        (self.root / 'link').symlink_to('a')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            v.verify_map(self.root, {'link': self.manifest['a']})

    def test_missing_json(self):
        with self.assertRaises(ValueError):
            v.read_json(self.root / 'absent')

    def test_truncated_and_duplicate_json(self):
        for raw in ('{"success":', '{"x":1,"x":2}', '[1]'):
            (self.root / 'receipt').write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                v.read_json(self.root / 'receipt')

    def test_required_pass_positive(self):
        events = [{'Test': 'required', 'Action': 'pass'}]
        self.assertEqual(v.required_gaps(events, ['required']), [])

    def test_required_skips_and_missing_not_accepted(self):
        self.assertEqual(v.required_gaps([{'Test': 'required', 'Action': 'skip'}], ['required', 'missing']), ['missing', 'required:skip'])

    def test_required_fail_not_accepted(self):
        self.assertEqual(v.required_gaps([{'Test': 'required', 'Action': 'fail'}], ['required']), ['required:fail'])


if __name__ == '__main__':
    unittest.main()
