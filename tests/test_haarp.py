"""Network-free HAARP metadata/antenna evidence contract tests."""
import unittest
from forecast.haarp import (
    collect, fetch_public, DIAGNOSTICS_URL, TRANSMISSIONS_URL,
    RIOMETER_URL, OBLIQUE_URL,
)

DIAG = b"<html><body><h1>Diagnostic Suite</h1><p>Ionosonde</p><p>SAGO Riometer</p></body></html>"
NOTICES = b"""<html><body><h1>Transmission Notices</h1>
<a href="https://drive.google.com/file/d/abc/view">October 2026</a>
<a href="javascript:alert(1)">20 malicious</a>
<a href="https://attacker.example/phish">November 2026</a></body></html>"""


class HAARPTests(unittest.TestCase):
    def test_source_documents_are_not_confused_with_live_array_state(self):
        samples = {
            DIAGNOSTICS_URL: DIAG,
            TRANSMISSIONS_URL: NOTICES,
            RIOMETER_URL: b"<html><img src='/plot.png'></html>",
            OBLIQUE_URL: b"<html><img src='/plot2.png'></html>",
        }
        record, statuses = collect(fetch=samples.__getitem__, checked_at="2026-11-13T23:00:00Z")
        iri = record["iri_antenna_array"]
        self.assertEqual(iri["element_count"], 180)
        self.assertEqual(iri["layout"], [12, 15])
        self.assertEqual(iri["actual_transmission_state"], "UNKNOWN")
        self.assertIsNone(iri["current_power_mw"])
        self.assertIsNone(iri["beam_direction"])
        self.assertEqual(iri["remote_control"], "NOT_AVAILABLE")
        self.assertEqual(iri["last_transmission_notice"]["title"], "October 2026")
        self.assertEqual(len(iri["transmission_notices"]), 1)
        self.assertEqual(len(record["source_documents"]), 4)
        self.assertEqual([s["status"] for s in statuses], ["VERIFIED"] * 4 + ["UNVERIFIED"])
        self.assertTrue(all(s["measurement_status"] == "UNVERIFIED" for s in record["sensors"]))
        self.assertTrue(all(s["measurement_time"] is None for s in record["sensors"]))
        self.assertFalse(any("raw_payload" in s for s in record["source_documents"].values()))

    def test_blocked_sources_do_not_invent_telemetry(self):
        def refused(_):
            raise OSError("offline")
        record, statuses = collect(fetch=refused, checked_at="2026-11-13T23:00:00Z")
        self.assertEqual([s["status"] for s in statuses], ["BLOCKED"] * 4 + ["UNVERIFIED"])
        self.assertIsNone(record["iri_antenna_array"]["last_transmission_notice"])
        self.assertEqual(record["iri_antenna_array"]["actual_transmission_state"], "UNKNOWN")
        self.assertTrue(all(s["catalog_status"] == "BLOCKED" for s in record["sensors"]))

    def test_bounded_payload_validation(self):
        def oversized(_):
            return b"X" * 1_000_001
        record, statuses = collect(fetch=oversized)
        self.assertEqual(len(record["source_documents"]), 0)
        self.assertEqual(sum(s["status"] == "BLOCKED" for s in statuses), 4)

    def test_disallow_unapproved_endpoints(self):
        with self.assertRaises(ValueError):
            fetch_public("http://haarp.gi.alaska.edu/diagnostic-suite")
        with self.assertRaises(ValueError):
            fetch_public("https://example.com/data")


if __name__ == "__main__":
    unittest.main()
