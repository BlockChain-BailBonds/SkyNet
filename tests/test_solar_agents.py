"""Offline deterministic solar sensor-agent and training-gate tests."""
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

from forecast.space_weather import BASE, ENDPOINTS, SourceError, collect, normalize_scales
from sensor_agents.runtime import NOAA_SPECS, HAARP_SPECS, SensorSpec, Supervisor, sha


NOW = datetime(2026, 11, 14, 6, 0, tzinfo=timezone.utc)


def mk_swpc():
    kp = []
    start = NOW - timedelta(hours=3 * 44)
    for index in range(44):
        date = start + timedelta(hours=3 * index)
        kp.append({"time_tag": date.replace(tzinfo=None).isoformat(timespec="seconds"),
                   "Kp": float(1 + index % 5) / 2, "station_count": 8})
    return {
        "scales": {"0": {"DateStamp": "2026-11-14", "TimeStamp": "05:55:00",
                         "G": {"Scale": "1"}, "R": {"Scale": "2"}, "S": {"Scale": "0"}}},
        "kp": kp,
        "flare": [{"max_time": "2026-11-14T05:46:00Z", "max_class": "C1.3",
                   "satellite": 18, "end_time": "Unk"}],
        "bulletins": [
            {"issue_datetime": "2026-11-14 05:03:51.727", "product_id": "EF3A",
             "message": "CONTINUED ALERT: Electron 2MeV Integral Flux exceeded threshold"}
        ],
    }


def fixture_fetch(overrides=None):
    fixtures = mk_swpc()
    if overrides:
        fixtures.update(overrides)
    reverse = {BASE + path: name for name, path in ENDPOINTS.items()}

    def get(url):
        return json.dumps(fixtures[reverse[url]], separators=(",", ":")).encode()
    return get


class SpaceWeatherTests(unittest.TestCase):
    def test_all_four_agents_monitor_inbound_and_outbound(self):
        report = collect(fetch=fixture_fetch(), now=NOW)
        self.assertEqual(report["status"], "VERIFIED")
        self.assertEqual(report["current_scales"]["levels"], {"G": 1, "R": 2, "S": 0})
        self.assertEqual(report["planetary_kp"]["value"], 2.0)
        self.assertEqual(report["latest_flare"]["latest"]["peak_class"], "C1.3")
        self.assertEqual(len(report["sources"]), 4)
        audit = report["agent_monitor"]
        self.assertEqual(len(audit["agents"]), 4)
        self.assertEqual(sum(x["input_count"] for x in audit["agents"]), 4)
        self.assertEqual(sum(x["output_count"] for x in audit["agents"]), 4)
        self.assertTrue(all(x["status"] == "VERIFIED" for x in report["sources"]))
        prev = "0" * 64
        for event in audit["events"]:
            self.assertEqual(event["prev_hash"], prev)
            prev = event["chain_hash"]
            self.assertEqual(prev, sha({k: v for k, v in event.items() if k != "chain_hash"}))
        self.assertEqual(audit["chain_head"], prev)
        kp_agent = next(a for a in audit["agents"] if a["id"] == "NOAA.KP")
        self.assertEqual(kp_agent["learning"], "SHADOW_TRAINED_NOT_PROMOTED")
        model = kp_agent["training_candidate"]
        self.assertGreaterEqual(model["training_samples"], 24)
        self.assertGreaterEqual(model["holdout_samples"], 6)
        self.assertFalse(model["alerts_enabled"])
        self.assertEqual(model["promotion"], "AWAITING_OPERATOR_APPROVAL")

    def test_invalid_scale_cannot_produce_verified_live_alert(self):
        data = mk_swpc()
        data["scales"]["0"]["G"]["Scale"] = "9"
        report = collect(fetch=fixture_fetch(data), now=NOW)
        self.assertEqual(report["status"], "UNVERIFIED")
        source = report["sources"][0]
        self.assertEqual(source["status"], "BLOCKED")
        self.assertEqual(report["agent_monitor"]["agents"][0]["last_status"], "BLOCKED")
        self.assertIsNone(report["current_scales"])

    def test_old_scale_does_not_represent_now(self):
        scale = mk_swpc()["scales"]
        scale["0"]["DateStamp"] = "2026-11-12"
        report = collect(fetch=fixture_fetch({"scales": scale}), now=NOW)
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(report["sources"][0]["status"], "UNVERIFIED")

    def test_empty_bulletins_are_history_not_current_alerts(self):
        report = collect(fetch=fixture_fetch({"bulletins": []}), now=NOW)
        self.assertEqual(report["bulletins"]["recent"], [])
        self.assertFalse(report["bulletins"]["fresh"])

    def test_untrusted_future_and_out_of_bounds_kp_fail(self):
        data = mk_swpc()
        data["kp"][0]["Kp"] = 999
        report = collect(fetch=fixture_fetch({"kp": data["kp"]}), now=NOW)
        self.assertEqual(report["sources"][1]["status"], "BLOCKED")
        agent = report["agent_monitor"]["agents"][1]
        self.assertIsNone(agent["training_candidate"])

    def test_training_requires_multiple_validated_points(self):
        manager = Supervisor(NOAA_SPECS, "2026-11-14T06:00:00Z")
        self.assertIsNone(manager.candidate("NOAA.KP",
            [{"observed_at": "2026-11-14T05:00:00Z", "value": 2.0}]))
        self.assertEqual(manager.states["NOAA.KP"]["learning"], "INSUFFICIENT_VALIDATED_SAMPLES")
        self.assertIsNone(manager.candidate("NOAA.GRS", []))
        self.assertEqual(manager.states["NOAA.GRS"]["learning"], "NO_NUMERIC_MEASUREMENT")

    def test_sensitive_payload_is_never_serialized_in_monitor(self):
        m = Supervisor(NOAA_SPECS, "2026-11-14T06:00:00Z")
        raw = b'{"value":1,"access_token":"super-private-do-not-store"}'
        m.ingress("NOAA.GRS", raw)
        output = json.dumps(m.public_report())
        self.assertNotIn("super-private-do-not-store", output)
        self.assertIn(hashlib.sha256(raw).hexdigest(), output)
        with self.assertRaises(ValueError):
            m.ingress("NOAA.GRS", b"X" * 1_000_001)

    def test_monitored_sources_have_unique_identifiers(self):
        specs = NOAA_SPECS + HAARP_SPECS
        self.assertEqual(len(specs), len({s.sensor_id for s in specs}))
        self.assertGreaterEqual(len(specs), 13)
        with self.assertRaises(ValueError):
            Supervisor([specs[0], specs[0]], "2026-11-14T06:00:00Z")
        with self.assertRaises(ValueError):
            SensorSpec("unsafe/", "http://example.com")


if __name__ == "__main__":
    unittest.main()
