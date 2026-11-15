# SkyNet Pocket → SkyNet Main HTTPS uplink

This implementation lives in draft [Pocket PR #12](https://github.com/BlockChain-BailBonds/SkyNet/pull/12). It adds a bounded HTTPS heartbeat sender to the **original CYD ESP32-2432S028R (N4)**, a separate Python receiver, SQLite receipts, anti-replay checks, unit tests, and read-only evidence in the operator console. It does **not** flash or modify the GOOUUU S3.

## Trust boundaries

```text
CYD (authorized Wi-Fi) --TLS 1.2+ / HMAC-SHA256--> HTTPS proxy on public DNS
    -> loopback :8790 Pocket gateway -> SQLite replay keys and receipts
       -> authenticated /api/pocket/status and /api/pocket/receipts
       -> SkyNet Main GitHub Pages operator UI (browser read-only)
```

GitHub Pages is **not** the telemetry receiver. HTTPS ingress requires a separately operated host, public DNS, valid TLS, a consented device registration and uptime. WSS is **not required** for this HTTPS-only heartbeat channel. No live hosted gateway or enrolled board is claimed by committing this code.

The device signs the exact UTF-8 request body, using a 32-byte random per-device secret and HMAC-SHA256. The canonical ASCII string is the lines `POST`, `/api/pocket/heartbeat`, `device_id`, decimal Unix seconds, lowercase 16-byte random nonce (hex), and SHA-256 of the body (hex), separated by LF characters without a trailing newline. Headers: `X-SkyNet-Device`, `X-SkyNet-Timestamp`, `X-SkyNet-Nonce`, `X-SkyNet-Signature`. The server enforces ±300-second clock skew, 1,024-byte limit, exact JSON schema, active operator consent registration, constant-time HMAC comparison, and persistent nonce uniqueness in SQLite. It returns a SHA-256 receipt digest only for accepted reports.

**Evidence limits:** A signed report authenticates possession of the enrolled *software secret*, not a tamper-proof physical chip. Keys reside in NVS, which is not assured to be encrypted on an ordinary CYD. A valid `s3_http_ok` or `ruview_api_ok` flag means the CYD reached a configured JSON endpoint; it does not prove CSI capture, human detection, location, or camera origin. No raw CSI, image, address or participant identity is uploaded.

## 1. Register an authorized device on the gateway host

Install Python 3.10+ and clone the project onto a trusted Linux server. Do not enable a device unless its owner explicitly authorizes telemetry and the consent reference and expiry are documented. Create the private registry with local interactive input:

```bash
install -d -m 700 "$HOME/.config/skynet" "$HOME/.local/share/skynet"
umask 077
python3 - <<'PY'
import json, secrets, time, re
from pathlib import Path
identity=input("Device ID (8-64 letters/digits/_/-): ").strip()
consent=input("Actual approved consent-record reference: ").strip()
days=int(input("Consent validity days (1-365): ").strip())
if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", identity):
    raise SystemExit("Invalid device ID")
if not 3 <= len(consent) <= 128 or not 1 <= days <= 365:
    raise SystemExit("Invalid consent record or expiry")
secret=secrets.token_hex(32)
p=Path.home()/".config/skynet/devices.json"
with p.open("x", encoding="utf-8") as f:
    json.dump({"devices": {identity: {
        "secret_hex": secret, "consent_ref": consent,
        "consent_expires_unix": int(time.time()) + days*86400,
        "enabled": True
    }}}, f, indent=2)
p.chmod(0o600)
print("Store this device secret only on the actual CYD during its local provisioning:")
print(secret)
print("Private registry:", p)
PY
```

This is a one-time *new registry* example; its exclusive file creation fails rather than overwriting enrolled devices. For additional devices, use a secure local administrative workflow to add a unique ID, key, approval and expiry to the private file. Never commit the registry, secrets, consent documents or database to GitHub. Revoke by setting `enabled: false` and restarting the gateway. Keep backups restricted to the operator.

Generate a separate operator token of at least 32 characters using `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` and store it in a secure credential manager.

## 2. Start receiver on loopback

```bash
export SKYNET_POCKET_CONFIG="$HOME/.config/skynet/devices.json"
export SKYNET_POCKET_DB="$HOME/.local/share/skynet/pocket.sqlite3"
export SKYNET_POCKET_DASHBOARD_ORIGIN="https://blockchain-bailbonds.github.io"
read -r -s -p 'Operator token: ' SKYNET_POCKET_OPERATOR_TOKEN
printf '\n'
export SKYNET_POCKET_OPERATOR_TOKEN
python3 -m pocket.gateway --check
python3 -m pocket.gateway --host 127.0.0.1 --port 8790
```

The server refuses a non-loopback bind. Put it behind a trusted HTTPS reverse proxy that preserves `/api/pocket/heartbeat`, `/api/pocket/status`, `/api/pocket/receipts`, and `/api/health`; terminate TLS with a publicly trusted certificate for the actual gateway DNS host. Keep port 8790 inaccessible externally and forward only the intended routes. Use restricted process/service permissions, secure storage, firewall and reverse-proxy rate limits. Securely manage process environment credentials (not in code or public logs). Keep TLS verification enabled on the CYD.

A sample Caddy site block, after configuring the actual DNS record, is:

```caddyfile
gateway.example.org {
    reverse_proxy 127.0.0.1:8790
}
```

`gateway.example.org` is **illustrative, not an existing SkyNet endpoint**. A DNS host and trusted HTTPS certificate must actually be provisioned by the operator.

## 3. Provision the CYD only (after reviewing the new firmware image)

Build in the CYD workflow; compare the CI artifact hash to the image you intend to flash, back up the existing CYD image first, and verify the physical board variant. **Do not flash the GOOUUU S3.** The touchscreen SETUP page enables the randomized WPA2 `SKYNET-CYD` access point; open `http://192.168.4.1` on a phone connected to that temporary AP.

Enter the normal authorized Wi-Fi and S3 settings. For uplink, supply the real gateway **DNS host only** (without `https://`), TLS port (usually 443), the exact registered device ID, its 64-character lowercase hex secret, and the PEM root CA certificate chain trust anchor appropriate to the HTTPS server. The CYD calls `WiFiClientSecure.setCACert`; **there is no insecure TLS fallback**. A CA trust anchor is public data; keep the device secret private. Device flash/NVS credentials are not automatically encrypted without the appropriate ESP32 security features.

After Wi-Fi and NTP synchronize, the CYD attempts one small HTTPS heartbeat every 60 seconds. The STATUS screen shows `Uplink: ACK RECEIVED` only after HTTPS response 201, expected acknowledgment schema and a 64-character receipt. Rejection, missing clock, invalid CA or network errors remain explicit. HTTP 200 on the S3 is *not* an uplink acknowledgment.

## 4. Verify read-only gateway evidence

From the operator workstation:

```bash
curl --fail-with-body --show-error "https://YOUR_ACTUAL_GATEWAY_DNS/api/health"
curl --fail-with-body --show-error --header "Authorization: Bearer $SKYNET_POCKET_OPERATOR_TOKEN" "https://YOUR_ACTUAL_GATEWAY_DNS/api/pocket/status"
curl --fail-with-body --show-error --header "Authorization: Bearer $SKYNET_POCKET_OPERATOR_TOKEN" "https://YOUR_ACTUAL_GATEWAY_DNS/api/pocket/receipts"
```

Replace the example host with the actual configured gateway DNS name before executing; there is no bundled production gateway address.

Open `https://blockchain-bailbonds.github.io/SkyNet/static/ops/` after the review and deployment. Enter the authorized HTTPS gateway origin and operator token **at check time only**, then click **Probe read-only routes**. The updated dashboard defaults to `/api/pocket/status` and `/api/pocket/receipts`. It verifies the gateway's authenticated report and freshness (≤180 seconds), and clears the token input immediately. It never retains credentials in HTML, browser storage, telemetry or exported reports.

The gateway status is `VERIFIED` only for a fresh authenticated ingress receipt from a currently permitted device. **Consent legal proof, physical board ID, signed firmware provenance, CSI detection and camera provenance remain separate evidence gates.** A no-data backend must show BLOCKED, never a fictional connected Pocket.

## 5. Local tests and failure handling

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_pocket_uplink -v
```

Test valid signatures, tampering, invalid/expired consent, oversized/malformed payloads, time skew, stale heartbeat and replay after SQLite reopen. The CYD firmware CI must compile the exact changed branch with PlatformIO and package a checksum-listed 4 MB flash image. CI completion is **not** direct hardware proof.

- `CLOCK BLOCKED`: verify Internet/NTP reachability and clock. Do not widen the ±5-minute replay window.
- `TLS/NETWORK ERROR` or `TLS BLOCKED`: verify public DNS, certificate issuer/CA, 443 forwarding, proxy access, and Wi-Fi; do not disable TLS validation.
- `HTTP 401`: check device ID, clock, key and signature canonicalization.
- `HTTP 403`: check registration, `enabled` state, consent validity and expiry.
- `HTTP 409`: replay nonce rejected; investigate cloned credentials or duplicated request.
- `ACK RECEIVED` with stale dashboard: check authenticated status route, current server time, 180-second freshness, operator token, HTTPS and CORS origin.
- Loss of S3 polling, camera or touch after flashing: roll back the backed-up CYD firmware and inspect the build and serial traces. The S3 remains unchanged.
