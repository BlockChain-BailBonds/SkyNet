"""Real loopback HTTP acceptance tests; no external network or devices required."""
import hashlib
import hmac
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pocket.gateway import PocketStore, handler_for, SCHEMA


class PocketHttpTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.identity = "pocket-n4-http"
        self.key = bytes(range(32))
        self.operator = "operator" + "B" * 48
        self.store = PocketStore(
            str(Path(self.temp.name) / "receipts.sqlite3"),
            {self.identity: {"secret_hex": self.key.hex(), "consent_ref": "approved-http-test",
                             "consent_expires_unix": int(time.time()) + 3600,
                             "enabled": True}},
            self.operator,
            "https://blockchain-bailbonds.github.io",
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path, method="GET", data=None, headers=None):
        request = Request(self.url + path, method=method, data=data, headers=headers or {})
        try:
            with urlopen(request, timeout=4) as response:
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as error:
            return error.code, dict(error.headers.items()), error.read()

    def signed_heartbeat(self):
        data = json.dumps({"schema": SCHEMA, "kind": "heartbeat",
                           "device_id": self.identity, "firmware_id": "test-n4-1",
                           "uptime_ms": 20000, "wifi_rssi_dbm": -45,
                           "s3_http_ok": True, "ruview_api_ok": False},
                          separators=(",", ":")).encode("utf-8")
        stamp = str(int(time.time()))
        nonce = "ba" * 16
        digest = hashlib.sha256(data).hexdigest()
        msg = f"POST\n/api/pocket/heartbeat\n{self.identity}\n{stamp}\n{nonce}\n{digest}"
        signature = hmac.new(self.key, msg.encode("ascii"), hashlib.sha256).hexdigest()
        return data, {"Content-Type": "application/json", "X-SkyNet-Device": self.identity,
                      "X-SkyNet-Timestamp": stamp, "X-SkyNet-Nonce": nonce,
                      "X-SkyNet-Signature": signature}

    def test_http_health_not_telemetry(self):
        status, _, body = self.request("/api/health")
        self.assertEqual(status, 200)
        info = json.loads(body)
        self.assertEqual(info["telemetry"], "not_implied")

    def test_http_requires_admin_token_and_supports_cors(self):
        status, _, _ = self.request("/api/pocket/status")
        self.assertEqual(status, 401)
        headers = {"Authorization": "Bearer " + self.operator,
                   "Origin": "https://blockchain-bailbonds.github.io"}
        status, response_headers, raw = self.request("/api/pocket/status", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(response_headers["Access-Control-Allow-Origin"],
                         "https://blockchain-bailbonds.github.io")
        self.assertEqual(json.loads(raw)["devices"][0]["ingress_status"], "BLOCKED")
        bad_headers = {"Authorization": "Bearer " + self.operator,
                       "Origin": "https://untrusted.example"}
        status, response_headers, _ = self.request("/api/pocket/status", headers=bad_headers)
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)

    def test_http_real_hmac_accept_replay_and_receipt(self):
        payload, headers = self.signed_heartbeat()
        status, _, result = self.request("/api/pocket/heartbeat", method="POST", data=payload, headers=headers)
        self.assertEqual(status, 201, result)
        receipt = json.loads(result)
        self.assertTrue(receipt["accepted"])
        self.assertEqual(len(receipt["receipt"]), 64)
        status, _, result = self.request("/api/pocket/heartbeat", method="POST", data=payload, headers=headers)
        self.assertEqual(status, 409, result)
        admin = {"Authorization": "Bearer " + self.operator}
        status, _, result = self.request("/api/pocket/status", headers=admin)
        self.assertEqual(status, 200, result)
        self.assertEqual(json.loads(result)["devices"][0]["ingress_status"], "VERIFIED")
        status, _, result = self.request("/api/pocket/receipts", headers=admin)
        self.assertEqual(status, 200, result)
        self.assertEqual(len(json.loads(result)["receipts"]), 1)

    def test_http_rejects_noncanonical_signed_route(self):
        payload, headers = self.signed_heartbeat()
        status, _, _ = self.request("/api/pocket/heartbeat?ignored=1", method="POST",
                                     data=payload, headers=headers)
        self.assertEqual(status, 404)
        self.assertEqual(self.store.receipts()["receipts"], [])

    def test_http_rejects_oversized_payload(self):
        status, _, _ = self.request("/api/pocket/heartbeat", method="POST",
                                    data=b"x" * 1025, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 413)

    def test_http_preflight_only_allows_configured_origin(self):
        status, _, body = self.request("/api/pocket/status", method="OPTIONS",
                                       headers={"Origin": "https://blockchain-bailbonds.github.io"})
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        status, _, _ = self.request("/api/pocket/status", method="OPTIONS",
                                    headers={"Origin": "https://untrusted.example"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
