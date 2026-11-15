"""SkyNet Pocket authenticated HTTP receiver, for deployment *behind* a TLS proxy.

The process binds to loopback by default. The published GitHub Pages site is
never the telemetry receiver. This service accepts only small, signed health
summaries and does not ingest raw camera frames, CSI traces or location.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "skynet-pocket-heartbeat/v1"
MAX_BODY = 1024
MAX_SKEW = 300
FRESHNESS = 180
RETENTION_SECONDS = 7 * 86400
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
HEX32_RE = re.compile(r"^[a-f0-9]{32}$")
HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
ALLOWED_FIELDS = {
    "schema", "kind", "device_id", "firmware_id", "uptime_ms",
    "wifi_rssi_dbm", "s3_http_ok", "ruview_api_ok",
}


class UplinkError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utc_string(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat(timespec="seconds")


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def validate_heartbeat(value, identity: str):
    if not isinstance(value, dict) or set(value) != ALLOWED_FIELDS:
        raise UplinkError("Invalid heartbeat schema")
    if value["schema"] != SCHEMA or value["kind"] != "heartbeat" or value["device_id"] != identity:
        raise UplinkError("Heartbeat identity or version mismatch")
    fw = value["firmware_id"]
    if not isinstance(fw, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", fw):
        raise UplinkError("Invalid firmware identifier")
    uptime = value["uptime_ms"]
    rssi = value["wifi_rssi_dbm"]
    if type(uptime) is not int or not 0 <= uptime <= 4294967295:
        raise UplinkError("Invalid uptime")
    if type(rssi) is not int or not -127 <= rssi <= 0:
        raise UplinkError("Invalid RSSI")
    if type(value["s3_http_ok"]) is not bool or type(value["ruview_api_ok"]) is not bool:
        raise UplinkError("Invalid source reachability")
    return value


def load_devices(path: str):
    config_file = Path(path)
    if not config_file.is_file():
        raise ValueError("SKYNET_POCKET_CONFIG must point to an existing private JSON file")
    if os.name == "posix" and (config_file.stat().st_mode & 0o077):
        raise ValueError("Private device configuration must have permissions 0600")
    raw = json.loads(config_file.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
    devices = raw.get("devices") if isinstance(raw, dict) else None
    if not isinstance(devices, dict) or not devices:
        raise ValueError("Device registry requires at least one registered device")
    for identity, row in devices.items():
        if not DEVICE_RE.fullmatch(identity) or not isinstance(row, dict):
            raise ValueError("Invalid device registry entry")
        if not HEX64_RE.fullmatch(row.get("secret_hex", "")):
            raise ValueError("Every device requires a random 32-byte lowercase hex secret")
        if not isinstance(row.get("consent_ref"), str) or not 3 <= len(row["consent_ref"]) <= 128:
            raise ValueError("Every device requires an operator-controlled consent reference")
        if type(row.get("enabled")) is not bool:
            raise ValueError("Every device requires explicit enabled true or false")
        if type(row.get("consent_expires_unix")) is not int:
            raise ValueError("Every device requires a consent expiry in Unix seconds")
    return devices


class PocketStore:
    def __init__(self, database: str, devices: dict, operator_token: str, allowed_origin: str = ""):
        if len(operator_token) < 32:
            raise ValueError("SKYNET_POCKET_OPERATOR_TOKEN must be at least 32 characters")
        if allowed_origin and (not allowed_origin.startswith("https://") or
                               urlsplit(allowed_origin).path or
                               urlsplit(allowed_origin).query or
                               urlsplit(allowed_origin).fragment or
                               not urlsplit(allowed_origin).hostname):
            raise ValueError("Dashboard origin must be an HTTPS origin")
        self.database = database
        self.devices = devices
        self.operator_token = operator_token
        self.allowed_origin = allowed_origin.rstrip("/")
        self.lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.database, timeout=8)
        try:
            db.execute("PRAGMA busy_timeout=8000")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init_db(self):
        with self._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nonces (
                device TEXT NOT NULL, nonce TEXT NOT NULL, seen_at INTEGER NOT NULL,
                PRIMARY KEY(device,nonce))""")
            db.execute("""CREATE TABLE IF NOT EXISTS receipts (
                receipt TEXT PRIMARY KEY, device TEXT NOT NULL,
                received_at INTEGER NOT NULL, firmware TEXT NOT NULL,
                uptime_ms INTEGER NOT NULL, rssi INTEGER NOT NULL,
                s3_http_ok INTEGER NOT NULL, ruview_api_ok INTEGER NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS receipt_latest ON receipts(device,received_at DESC)")

    def authorize(self, token: str) -> bool:
        return hmac.compare_digest(token, self.operator_token)

    def accept(self, headers: dict, raw: bytes, observed_at: int | None = None):
        now = int(time.time()) if observed_at is None else int(observed_at)
        if not 1 <= len(raw) <= MAX_BODY:
            raise UplinkError("Heartbeat body length rejected", 413)
        if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise UplinkError("Expected application/json", 415)
        identity = headers.get("x-skynet-device", "")
        stamp = headers.get("x-skynet-timestamp", "")
        nonce = headers.get("x-skynet-nonce", "")
        signature = headers.get("x-skynet-signature", "")
        if not DEVICE_RE.fullmatch(identity) or not stamp.isascii() or not stamp.isdigit() or len(stamp) > 12:
            raise UplinkError("Invalid authentication headers", 401)
        if not HEX32_RE.fullmatch(nonce) or not HEX64_RE.fullmatch(signature):
            raise UplinkError("Invalid authentication headers", 401)
        if abs(now - int(stamp)) > MAX_SKEW:
            raise UplinkError("Device clock outside permitted window", 401)
        row = self.devices.get(identity)
        if not row or not row["enabled"] or row["consent_expires_unix"] <= now:
            raise UplinkError("Device enrollment or consent inactive", 403)
        digest = hashlib.sha256(raw).hexdigest()
        canonical = f"POST\n/api/pocket/heartbeat\n{identity}\n{stamp}\n{nonce}\n{digest}"
        expected = hmac.new(bytes.fromhex(row["secret_hex"]), canonical.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise UplinkError("Authentication rejected", 401)
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate_keys)
        except (UnicodeError, ValueError):
            raise UplinkError("Malformed JSON")
        validate_heartbeat(payload, identity)
        receipt = hashlib.sha256((identity + "\n" + stamp + "\n" + nonce + "\n" + digest).encode("ascii")).hexdigest()
        with self.lock, self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM nonces WHERE seen_at < ?", (now - MAX_SKEW * 3,))
            db.execute("DELETE FROM receipts WHERE received_at < ?", (now - RETENTION_SECONDS,))
            try:
                db.execute("INSERT INTO nonces VALUES (?,?,?)", (identity, nonce, now))
            except sqlite3.IntegrityError:
                raise UplinkError("Replay rejected", 409)
            db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?)",
                       (receipt, identity, now, payload["firmware_id"], payload["uptime_ms"],
                        payload["wifi_rssi_dbm"], int(payload["s3_http_ok"]),
                        int(payload["ruview_api_ok"])))
        return {"schema": "skynet-pocket-ack/v1", "accepted": True,
                "receipt": receipt, "received_at": utc_string(now)}

    def status(self, observed_at: int | None = None):
        now = int(time.time()) if observed_at is None else int(observed_at)
        with self.lock, self._connection() as db:
            latest = db.execute("""SELECT r.device,r.receipt,r.received_at,r.firmware,
                    r.uptime_ms,r.rssi,r.s3_http_ok,r.ruview_api_ok,
                    (SELECT count(*) FROM receipts z WHERE z.device=r.device)
                    FROM receipts r
                    WHERE r.rowid=(SELECT z.rowid FROM receipts z
                                   WHERE z.device=r.device ORDER BY z.received_at DESC,z.rowid DESC LIMIT 1)""").fetchall()
        by_id = {r[0]: r for r in latest}
        result = []
        for identity, registration in sorted(self.devices.items()):
            rec = by_id.get(identity)
            age = now - rec[2] if rec else None
            active = registration["enabled"] and registration["consent_expires_unix"] > now
            fresh = active and age is not None and 0 <= age <= FRESHNESS
            result.append({
                "device_id": identity, "ingress_status": "VERIFIED" if fresh else "BLOCKED",
                "reason": "recent_authenticated_heartbeat" if fresh else
                          ("consent_inactive" if not active else "heartbeat_missing_or_stale"),
                "consent_ref": registration["consent_ref"] if active else None,
                "last_seen_at": utc_string(rec[2]) if rec else None,
                "age_seconds": age, "receipt_count": rec[8] if rec else 0,
                "last_receipt": rec[1] if rec else None,
                "firmware_id": rec[3] if rec else None,
                "wifi_rssi_dbm": rec[5] if rec else None,
                "s3_http_ok": bool(rec[6]) if rec else None,
                "ruview_api_ok": bool(rec[7]) if rec else None,
            })
        return {"schema": "skynet-pocket-status/v1", "observed_at": utc_string(now),
                "scope": "authenticated_gateway_ingress_only_not_physical_sensing",
                "devices": result}

    def receipts(self, limit: int = 20):
        with self.lock, self._connection() as db:
            rows = db.execute("""SELECT receipt,device,received_at,firmware,
                                      rssi,s3_http_ok,ruview_api_ok
                                 FROM receipts ORDER BY received_at DESC,rowid DESC LIMIT ?""",
                              (min(50, max(1, limit)),)).fetchall()
        return {"schema": "skynet-pocket-receipts/v1", "receipts": [
            {"receipt": r[0], "device_id": r[1], "received_at": utc_string(r[2]),
             "firmware_id": r[3], "wifi_rssi_dbm": r[4],
             "s3_http_ok": bool(r[5]), "ruview_api_ok": bool(r[6]),
             "authenticated": True} for r in rows]}


def handler_for(store: PocketStore):
    class PocketHandler(BaseHTTPRequestHandler):
        server_version = "SkyNetPocketGateway/1.0"
        def log_message(self, fmt, *args):
            # Never log request headers, tokens, secrets or raw device payloads.
            return

        def reply(self, status, payload):
            data = b"" if status == 204 else json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin", "")
            if store.allowed_origin and origin == store.allowed_origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            if self.path in ("/api/pocket/status", "/api/pocket/receipts") and self.headers.get("Origin", "") == store.allowed_origin and store.allowed_origin:
                self.reply(204, {})
            else:
                self.reply(403, {"error": "CORS origin rejected"})

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self.reply(200, {"status": "ok", "service": "skynet-pocket-gateway", "telemetry": "not_implied"})
            if path not in ("/api/pocket/status", "/api/pocket/receipts"):
                return self.reply(404, {"error": "Unknown read-only route"})
            header = self.headers.get("Authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            if not store.authorize(token):
                return self.reply(401, {"error": "Operator authentication required"})
            if path == "/api/pocket/status":
                return self.reply(200, store.status())
            return self.reply(200, store.receipts())

        def do_POST(self):
            if self.path != "/api/pocket/heartbeat":
                return self.reply(404, {"error": "Unknown ingestion route"})
            try:
                signed_headers = ("Content-Length", "Content-Type", "X-SkyNet-Device",
                                  "X-SkyNet-Timestamp", "X-SkyNet-Nonce", "X-SkyNet-Signature")
                if any(len(self.headers.get_all(name, [])) != 1 for name in signed_headers):
                    raise UplinkError("Missing or duplicate signed transport headers", 400)
                if self.headers.get("Transfer-Encoding"):
                    raise UplinkError("Chunked request body rejected", 400)
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 1 or length > MAX_BODY:
                    raise UplinkError("Body length rejected", 413)
                self.connection.settimeout(8)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise UplinkError("Incomplete request body", 400)
                headers = {key.lower(): value for key, value in self.headers.items()}
                return self.reply(201, store.accept(headers, raw))
            except UplinkError as exc:
                return self.reply(exc.status, {"error": str(exc)})
            except (ValueError, OSError):
                return self.reply(400, {"error": "Invalid request"})
    return PocketHandler


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Loopback-only SkyNet Pocket receiver; terminate TLS at a trusted HTTPS reverse proxy")
    parser.add_argument("--check", action="store_true", help="validate config and initialize SQLite, then exit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("Refusing public plaintext bind; use an HTTPS reverse proxy and loopback backend")
    config = os.environ.get("SKYNET_POCKET_CONFIG", "")
    token = os.environ.get("SKYNET_POCKET_OPERATOR_TOKEN", "")
    dbpath = os.environ.get("SKYNET_POCKET_DB", "pocket-telemetry.sqlite3")
    devices = load_devices(config)
    store = PocketStore(dbpath, devices, token, os.environ.get("SKYNET_POCKET_DASHBOARD_ORIGIN", ""))
    if os.name == "posix":
        os.chmod(dbpath, 0o600)
    if args.check:
        print("Pocket gateway configuration and storage validated; no listener started")
        return
    server = ThreadingHTTPServer((args.host, args.port), handler_for(store))
    print(f"SkyNet Pocket gateway listening on loopback port {args.port}; external TLS proxy required", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
