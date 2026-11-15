"""Acceptance and rejection tests for the Pocket uplink trust boundary."""
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path

from pocket.gateway import PocketStore, UplinkError, SCHEMA, load_devices


class PocketUplinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "pocket.sqlite3")
        self.device = "pocket-n4-0001"
        self.secret = bytes(range(32))
        self.token = "operator-" + "a" * 40
        self.now = int(time.time())
        self.devices = {
            self.device: {
                "secret_hex": self.secret.hex(),
                "consent_ref": "approved-consent-2026-001",
                "consent_expires_unix": self.now + 3600,
                "enabled": True,
            }
        }
        self.store = PocketStore(self.db, self.devices, self.token, "https://example.org")

    def signed(self, value=None, timestamp=None, nonce=None, key=None):
        payload = {
            "schema": SCHEMA, "kind": "heartbeat", "device_id": self.device,
            "firmware_id": "pocket-cyd-1", "uptime_ms": 70001,
            "wifi_rssi_dbm": -52, "s3_http_ok": True,
            "ruview_api_ok": False,
        }
        if value:
            payload.update(value)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ts = str(self.now if timestamp is None else timestamp)
        nonce = nonce or "ab" * 16
        digest = hashlib.sha256(raw).hexdigest()
        text = f"POST\n/api/pocket/heartbeat\n{self.device}\n{ts}\n{nonce}\n{digest}"
        signature = hmac.new(key or self.secret, text.encode("ascii"), hashlib.sha256).hexdigest()
        return {
            "content-type": "application/json",
            "x-skynet-device": self.device,
            "x-skynet-timestamp": ts,
            "x-skynet-nonce": nonce,
            "x-skynet-signature": signature,
        }, raw

    def test_accepts_real_signature_and_returns_receipt(self):
        headers, body = self.signed()
        out = self.store.accept(headers, body, self.now)
        self.assertTrue(out["accepted"])
        self.assertEqual(len(out["receipt"]), 64)
        self.assertEqual(self.store.status(self.now)["devices"][0]["ingress_status"], "VERIFIED")
        self.assertEqual(self.store.receipts()["receipts"][0]["device_id"], self.device)

    def test_rejects_tampered_body(self):
        headers, body = self.signed()
        with self.assertRaisesRegex(UplinkError, "Authentication"):
            self.store.accept(headers, body.replace(b"-52", b"-51"), self.now)

    def test_rejects_wrong_key(self):
        headers, body = self.signed(key=b"X" * 32)
        with self.assertRaises(UplinkError) as raised:
            self.store.accept(headers, body, self.now)
        self.assertEqual(raised.exception.status, 401)

    def test_replay_rejected_even_after_service_restart(self):
        headers, body = self.signed()
        self.store.accept(headers, body, self.now)
        restarted = PocketStore(self.db, self.devices, self.token)
        with self.assertRaises(UplinkError) as raised:
            restarted.accept(headers, body, self.now)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(len(restarted.receipts()["receipts"]), 1)

    def test_rejects_clock_skew(self):
        headers, body = self.signed(timestamp=self.now - 301)
        with self.assertRaises(UplinkError) as raised:
            self.store.accept(headers, body, self.now)
        self.assertEqual(raised.exception.status, 401)

    def test_rejects_revoked_consent(self):
        self.devices[self.device]["enabled"] = False
        headers, body = self.signed()
        with self.assertRaises(UplinkError) as raised:
            self.store.accept(headers, body, self.now)
        self.assertEqual(raised.exception.status, 403)

    def test_rejects_expired_consent(self):
        self.devices[self.device]["consent_expires_unix"] = self.now
        headers, body = self.signed()
        with self.assertRaises(UplinkError):
            self.store.accept(headers, body, self.now)

    def test_rejects_boolean_as_uptime(self):
        headers, body = self.signed({"uptime_ms": True})
        with self.assertRaisesRegex(UplinkError, "uptime"):
            self.store.accept(headers, body, self.now)

    def test_rejects_unexpected_payload_fields(self):
        headers, body = self.signed({"camera_image": "unapproved"})
        with self.assertRaisesRegex(UplinkError, "schema"):
            self.store.accept(headers, body, self.now)

    def test_rejects_oversized_body(self):
        headers, body = self.signed()
        with self.assertRaises(UplinkError) as raised:
            self.store.accept(headers, body + b"X" * 1100, self.now)
        self.assertEqual(raised.exception.status, 413)

    def test_rejects_duplicate_json_keys(self):
        headers, body = self.signed()
        body = body[:-1] + b',"schema":"skynet-pocket-heartbeat/v1"}'
        digest = hashlib.sha256(body).hexdigest()
        ts = headers["x-skynet-timestamp"]
        nonce = headers["x-skynet-nonce"]
        canonical = f"POST\n/api/pocket/heartbeat\n{self.device}\n{ts}\n{nonce}\n{digest}"
        headers["x-skynet-signature"] = hmac.new(self.secret, canonical.encode(), hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(UplinkError, "Malformed"):
            self.store.accept(headers, body, self.now)

    def test_freshness_is_independent_from_ingestion(self):
        headers, body = self.signed()
        self.store.accept(headers, body, self.now)
        st = self.store.status(self.now + 181)["devices"][0]
        self.assertEqual(st["ingress_status"], "BLOCKED")
        self.assertEqual(st["reason"], "heartbeat_missing_or_stale")

    def test_operator_status_token_required(self):
        self.assertTrue(self.store.authorize(self.token))
        self.assertFalse(self.store.authorize("bad-token"))

    def test_private_registry_rejects_permissive_file(self):
        path = Path(self.tmp.name) / "devices.json"
        path.write_text(json.dumps({"devices": self.devices}))
        path.chmod(0o644)
        if __import__("os").name == "posix":
            with self.assertRaises(ValueError):
                load_devices(str(path))
        path.chmod(0o600)
        self.assertEqual(load_devices(str(path)), self.devices)


if __name__ == "__main__":
    unittest.main()
