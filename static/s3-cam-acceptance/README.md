# SkyNet / GOOUUU ESP32-S3 N16R8-CAM acceptance console

**Scope:** Browser-based, evidence-first guided operator console. Source under `static/s3-cam-acceptance/`. The existing SkyNet Pages workflow copies `static/` to the deployable artifact; after an approved merge and a successful external Pages deployment the console path is `/SkyNet/static/s3-cam-acceptance/`. This path is **not** proof that deployment is currently live.

**No embedded flasher.** This page does not erase, write, upload firmware, enumerate USB by itself, send serial commands, capture a physical frame, operate RuView, or run a background service. All embedded controls are local parsing, provenance bookkeeping, explicit browser fetch, export, and approved POST only. Existing production workflows remain unchanged.

## Exact-device isolation

1. **Primary target:** new GOOUUU ESP32-S3 **N16R8-CAM**. Verify chip, actual flash capacity, camera module, revision, model pins and power wiring before creating a firmware image or obtaining write approval.
2. **Already-flashed separate S3:** preserve existing firmware; the S3-CAM image must not be flashed to this board. This profile has independent session evidence, read-only checks, and **no flash approval**.
3. **Original ESP32E N4 CYD:** ESP32-2432S028R, ESP32E/N4, ILI9341 touchscreen; separate build, firmware and pin mappings. No camera-S3 image or pin assumptions. Its reported screen evidence is not camera-origin or CSI evidence.

Neither a CH340 USB bridge VID/PID nor an N16R8 marketing label establishes a camera pin map. The interface requires a revision-specific schematic or primary hardware evidence, with the observed camera sensor ID. **No unverified GPIO assignments are built into this console.**

## Recommended smallest-first sequence

| Step | Operation | Boundary |
| --- | --- | --- |
| 1. Enumerate | Read-only USB bridge and actual chip ID using operator host tools; attach timestamped log | Doesn't modify flash or validate camera sensor |
| 2. Pinout | Record exact silkscreen/revision and observed sensor, schema, and source URL | Never use generic third-party S3 pin tables without exact-board corroboration |
| 3. Firmware | Select exact local image, declared SHA-256, source manifest and flash offset; recompute digest | File match does not prove it is running on device |
| 4. Readback | Save an authorized existing firmware readback, its SHA-256 and redacted trace | Browser hash validates bytes, not chip provenance |
| 5. Human gate | Enter exact chip ID and APPROVE FLASH after reviewing all prerequisites | **No erase or flash command available**; operator must separately approve any actual flash |
| 6. Boot | Capture physical boot/firmware ID trace and exact chip identifier | Token/ID checks are scope-limited to operator-supplied log |
| 7. HTTP status | Check live HTTPS `/api/v1/status` or equivalent read-only JSON | Requires exact `device_id`, timestamp <90 seconds old, non-synthetic source |
| 8. Commands | Send `STATUS`, `CAM STATUS`, `CAM CAPTURE` using an independently authorized serial terminal; paste returned trace | Browser **copies commands** but does not transmit them |
| 9. JPEG | Reconstruct `CAM_BEGIN`/sequential `CAM_DATA`/`CAM_END`; check size, CRC32, SOI/EOI | No complete frame or decoder failure means no camera acceptance |
| 10. Visual | Compare two distinct, fully received frames of a deliberately changed, consented scene, and correlate source ID/time with boot trace | Operator-attested, not independently authenticated image origin |
| 11. Gateway | Export scrubbed receipt; optionally POST only to operator-specified HTTPS ingestion URL with transient bearer token | HTTPS acknowledgment is **not** proof of backend storage, RuView/CSI, or live enrollment |

The console distinguishes `VERIFIED`, `UNVERIFIED`, `BLOCKED`, and `FAILED` and labels `HOST`, `DEVICE` (operator-supplied physical trace), and `SIMULATED`. A simulated record is never allowed to verify device behavior. A manually entered VERIFIED mark requires a source URL, a rationale, and previously identified device scope. These marks are **review records**, not a cryptographic attestation of physical provenance. Session records are held in memory and can be exported; no credentials are persisted.

## Serial JPEG framing contract

The console's strict, deterministic framing is:

```text
CAM_BEGIN id=frame-001 bytes=12345 crc32=1234ABCD
CAM_DATA id=frame-001 seq=0 b64=<base64 encoded first contiguous byte chunk>
CAM_DATA id=frame-001 seq=1 b64=<base64 encoded next contiguous byte chunk>
CAM_END id=frame-001 bytes=12345 crc32=1234ABCD
```

`CAM_DATA` may alternatively contain `hex=<even-length hex chunk>`. The first sequence is zero and must be contiguous. Frame IDs must match when repeated. `bytes` means decoded JPEG bytes, **not** base64 character count; CRC32 uses standard reflected polynomial 0xEDB88320 on the complete byte array and is represented as eight uppercase or lowercase hexadecimal digits. The end CRC is mandatory; the begin CRC is optional but must agree when present.

The parser rejects missing BEGIN/END, overlapping frames, duplicate fields, empty chunks, missing/duplicate sequences, out-of-order chunks, payload overflow, mismatched size/CRC, malformed base64/hex, absent JPEG SOI (`FF D8`) or EOI (`FF D9`), and trailing bytes after EOI. It checks **JPEG markers**, then requires separate browser image decoding for visual acceptance. A complete transport record doesn't establish live sensor origin or distinguish a replay by itself. Multiple frames are accepted only when each is individually complete. The current parser is deliberately bounded to 3 million log characters, 4 million decoded bytes/frame, and 8192 chunks/frame. Logs exceeding these limits require a more appropriate binary acquisition tool, not silent truncation.

### Match your firmware, do not assume this framing exists

The GOOUUU board's currently flashed firmware may produce a different line grammar, binary transfer, UART setting, or HTTP route. If so, treat this parser as **BLOCKED**, capture the real serial protocol and implement an explicit tested adapter. Do not rewrite unknown serial data to make it appear accepted. There is no evidence here that physical `CAM CAPTURE` has been observed.

## Status API expected source contract

The configured status JSON should supply:

```json
{
  "device_id": "exact operator-observed chip or device identifier",
  "timestamp": "2026-11-14T20:00:00Z",
  "online": true,
  "source_type": "physical-device"
}
```

A successful request with matching ID and fresh timestamp is reported as **fresh matching API response** only. The UI rejects mismatched identities, future clocks, synthetic/mock/fixture markers, offline flags, expired timestamps, invalid data, HTTP errors and broken/CORS-blocked connections. Freshness is not a trusted hardware attestation by itself. Do not accept timestamps solely from an intermediate cache pretending to be the physical device.

Use HTTPS, except explicit loopback `localhost`/`127.0.0.1` for authorized local development. Browsers enforce CORS. An HTTPS GitHub Pages page cannot make an insecure arbitrary HTTP request; implement a separate TLS-enabled gateway when necessary. The bearer token is read only for the initiated fetch and immediately cleared from the form. Do not include tokens in URLs.

## Integration / security

SkyNet Pages remains static; the live HTTPS/WSS gateway, authentication, device telemetry, camera streaming, RuView sensing, and server-side storage **must run separately**. The export schema is `skynet.s3cam.acceptance.v1`. It carries selected profile, current step statuses, hashes, approved image offset, optional approval record, report timestamps, and evidence summaries, but excludes JPEG frames, raw serial/CSI logs, network credentials, personally identifying scenes, raw location and bearer tokens.

An optional explicit POST goes to an operator-specified URL only and returns the result of that request. HTTP 2xx without a structured `receipt_id` is **UNVERIFIED**; even a `receipt_id` is a transport acknowledgment pending gateway audit, not production ingestion evidence. No RuView detection or CSI claim is inferred from a generic API response, and no device is auto-enrolled. Sensor enrollment should require informed consent and authenticated gateway-side control.

**External evidence pointers:** [SkyNet project](https://github.com/BlockChain-BailBonds/SkyNet), [main README evidence boundary](https://github.com/BlockChain-BailBonds/SkyNet/blob/main/README.md), [CI workflows](https://github.com/BlockChain-BailBonds/SkyNet/actions), [Pages deployment workflow](https://github.com/BlockChain-BailBonds/SkyNet/actions/workflows/pages.yml). Do not publish unreduced MAC addresses, Wi-Fi SSIDs/passwords, IP addresses, device secrets, faces, raw camera scenes, or raw CSI on public GitHub links. The evidence panel accepts HTTPS URLs; use sanitized public or properly permissioned sources.

## Tests

Run from repository root:

```sh
node --test tests/test_s3cam_protocol.mjs
python -m unittest tests/test_s3cam_console.py -v
```

The Python wrapper includes the Node parser regression suite in SkyNet's existing `python -m unittest discover -s tests -v` CI gate. The browser also provides in-memory self-tests, clearly labeled host-only. Tests include standard CRC/SHA vectors, complete/multiple/hex captures, truncation, missing sequence, mismatched CRC, invalid JPEG markers, stale/future/synthetic status, identity mismatch, and HTTPS validation. No test here claims a successful physical flash or camera frame.
