"""Offline acceptance and adversarial data tests for CERN public metadata agents."""
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forecast import cern


def payload():
    return json.dumps({
        "hits": {"total": {"value": 42}, "hits": [
            {"id": 1234, "metadata": {"title": "Collision data example"}},
            {"recid": "4567", "metadata": {"title": "Second sample"}},
        ]}
    }).encode()


def good_fetch(url):
    return payload() if "api/records/" in url else b"<!doctype html><html><head><title>CERN</title></head></html>"


class CERNIngestTests(unittest.TestCase):
    def test_six_agents_and_metadata_not_live_physics(self):
        report = cern.make_report("2026-11-14T06:30:00Z", good_fetch)
        self.assertEqual(report["sources_checked"], 6)
        self.assertEqual(report["metadata_retrievals_verified"], 6)
        self.assertEqual(report["numeric_physics_observations"], 0)
        self.assertEqual(report["correlation_status"], "BLOCKED")
        self.assertTrue(all(not a["live_sensor_access"] for a in report["agents"]))
        self.assertEqual(report["agents"][0]["metadata"]["matched_records"], 42)
        self.assertEqual(report["agents"][0]["response_sha256"], hashlib.sha256(payload()).hexdigest())
        self.assertEqual(report["agents"][0]["metadata"]["sampled_records"][0]["url"],
                         "https://opendata.cern.ch/record/1234")
        self.assertEqual(report["evidence"][1]["prev_hash"], report["evidence"][0]["chain_hash"])

    def test_untrusted_metadata_rejected_not_executed(self):
        p = json.loads(payload())
        p["hits"]["hits"][0]["id"] = "http://privatehost/admin"
        with self.assertRaises(cern.SourceRejected):
            cern.normalize_catalog(json.dumps(p).encode())
        with self.assertRaises(cern.SourceRejected):
            cern.normalize_catalog(b'{"hits":{"hits":[]}}')
        with self.assertRaises(cern.SourceRejected):
            cern.normalize_catalog(b'{"hits":{"hits":[{"id":1}],"total":2e999}}')
        with self.assertRaises(cern.SourceRejected):
            cern.normalize_page(b"<script>alert(1)</script>")
        spec = cern.AGENTS[0]
        result = cern.collect_one(spec, "2026-11-14T06:30:00Z", lambda _: b'{"error":"forbidden"}')
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["response_sha256"])
        self.assertEqual(result["reason"], "SCHEMA_REJECTED")

    def test_fail_closed_and_no_secrets_or_fake_training(self):
        def broken(url):
            if "CMS" in url:
                raise TimeoutError("private token not to be logged")
            return good_fetch(url)
        report = cern.make_report("2026-11-14T06:30:00Z", broken)
        self.assertEqual(report["metadata_retrievals_verified"], 5)
        self.assertEqual(report["agents"][0]["reason"], "FETCH_FAILED")
        self.assertNotIn("private token", json.dumps(report))
        self.assertEqual(report["learning_policy"], "METADATA_ONLY_NO_TRAINING")

    def test_response_cap_and_fixed_allowlist(self):
        with self.assertRaises(cern.SourceRejected):
            cern.fetch_bytes("https://example.com/data")
        a = cern.collect_one(cern.AGENTS[0], "2026-11-14T06:30:00Z",
                             lambda _: b"x" * (cern.MAX_BYTES + 1))
        self.assertEqual(a["reason"], "PAYLOAD_REJECTED")
        self.assertEqual(cern.stamp(datetime(2026, 11, 14, tzinfo=timezone.utc)),
                         "2026-11-14T00:00:00Z")
        with self.assertRaises(ValueError):
            cern.stamp(datetime(2026, 11, 14))

    def test_safe_atomic_snapshot(self):
        report = cern.make_report("2026-11-14T06:30:00Z", good_fetch)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "public" / "cern-status.json"
            cern.save(report, target)
            self.assertEqual(json.loads(target.read_text()), report)
            self.assertFalse(target.with_suffix(".tmp").exists())

    def test_ui_and_publish_hook(self):
        html = (ROOT / "index.html").read_text()
        js = (ROOT / "static" / "assets" / "cern.js").read_text()
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text()
        self.assertIn('id="cern"', html)
        self.assertIn('data-view="cern"', html)
        self.assertIn("cern-status.json", js)
        self.assertIn("forecast.cern --allow-blocked", workflow)
        self.assertIn("cache: 'no-store'", js)


if __name__ == "__main__":
    unittest.main()
