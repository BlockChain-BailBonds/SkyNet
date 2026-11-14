"""HAARP doc evidence cannot become fake live sensor telemetry."""
import unittest
from sensor_agents.report import assemble
from forecast.space_weather import collect
from tests.test_solar_agents import NOW, fixture_fetch


class ReportTests(unittest.TestCase):
    def test_all_13_agents_have_independent_training_statuses(self):
        solar = collect(fetch=fixture_fetch(), now=NOW)
        haarp = {
            "source_documents": {
                "HAARP diagnostic catalog": {"sha256": "a" * 64},
                "HAARP transmission notices": {"sha256": "b" * 64},
                "HAARP SAGO riometer chart": {"sha256": "c" * 64},
            }
        }
        report = assemble(solar, haarp, "2026-11-14T06:00:00Z")
        self.assertEqual(report["agent_count"], 13)
        self.assertEqual(len(report["agents"]), 13)
        self.assertEqual(len({agent["id"] for agent in report["agents"]}), 13)
        self.assertFalse(report["training"]["autonomous_model_promotion"])
        haarp_agents = [x for x in report["agents"] if x["id"].startswith("HAARP.")]
        self.assertEqual(len(haarp_agents), 9)
        self.assertTrue(all(x["training_candidate"] is None for x in haarp_agents))
        self.assertTrue(all(x["output_count"] == 0 for x in haarp_agents))
        self.assertTrue(all(x["last_status"] != "VERIFIED" for x in haarp_agents))
        self.assertTrue(any(x["metadata_count"] == 1 for x in haarp_agents))
        self.assertIn("TRAIN_CANDIDATE", [e["direction"] for e in report["monitors"]["NOAA"]["events"]])

    def test_unreachable_haarp_is_blocked_not_falsified(self):
        solar = collect(fetch=fixture_fetch(), now=NOW)
        report = assemble(solar, {}, "2026-11-14T06:00:00Z")
        self.assertTrue(all(x["last_status"] == "BLOCKED"
                            for x in report["agents"] if x["id"].startswith("HAARP.")))

    def test_missing_noaa_audit_rejected(self):
        with self.assertRaises(ValueError):
            assemble({}, {}, "2026-11-14T06:00:00Z")


if __name__ == "__main__":
    unittest.main()
