import json
from pathlib import Path
import unittest
from chimera.fusion import fuse, annotate, license_review
from chimera.github_client import sha256, slug_from_input, validate_slugs, GitHubClient, GitHubError

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / 'fixtures' / 'repositories.json').read_text())

class FusionTest(unittest.TestCase):
    def test_demo_produces_ranked_concepts(self):
        result = fuse([dict(r, source_type='fixture') for r in FIXTURE])
        self.assertEqual(result['source_mode'], 'fixture')
        self.assertEqual(len(result['repositories']), 8)
        self.assertEqual(len(result['proposals']), 12)
        self.assertEqual(result['proposals_total'], 56)
        scores = [r['score'] for r in result['proposals']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(p['validation_status'] == 'concept_only_unverified' for p in result['proposals']))
        self.assertTrue(all(len(p['repos']) == 3 for p in result['proposals']))
        self.assertEqual(len(result['analysis_sha256']), 64)

    def test_licenses_are_not_legal_approval(self):
        r = license_review([{'license': 'MIT'}, {'license':'BSD-3-Clause'}])
        self.assertEqual(r['status'], 'preliminary_permissive_only')
        self.assertFalse(r['legal_conclusion'])
        r = license_review([{'license': 'MIT'}, {'license':'AGPL-3.0'}])
        self.assertIn('manual', r['status'])
        self.assertEqual(license_review([{'license':'UNKNOWN'}, {'license':'MIT'}])['status'], 'blocked_pending_manual_license_review')

    def test_metadata_classification_is_heuristic(self):
        r = annotate(FIXTURE[0])
        self.assertIn('sensing', r['capabilities'])
        self.assertIn('mqtt', r['ports'])
        self.assertEqual(r['classification_status'], 'keyword_heuristic_only')

    def test_slug_validation_prevents_non_github_fetch(self):
        self.assertEqual(slug_from_input('https://github.com/networkx/networkx/'), 'networkx/networkx')
        for bad in ['https://example.com/a/b', 'http://github.com/a/b', 'https://github.com/a/b/tree/main', 'a', '../evil', 'https://github.com@evil.com/a/b', 'https://github.com/a/b?x=1']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                slug_from_input(bad)
        self.assertEqual(len(validate_slugs(['a/b', 'a/b', 'c/d'])), 2)
        with self.assertRaises(ValueError):
            validate_slugs(['a/b'])

    def test_hash_stable_key_order(self):
        self.assertEqual(sha256({'b': 2, 'a': 1}), sha256({'a': 1, 'b': 2}))

    def test_client_prevents_arbitrary_endpoints(self):
        c = GitHubClient(cache_file='/tmp/chimera-test-isolated.sqlite3', token='')
        with self.assertRaises(GitHubError):
            c._read_api('/users/secret')

if __name__ == '__main__':
    unittest.main()
