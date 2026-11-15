# SkyNet Pocket firmware — CYD ESP32-2432S028R (N4)

**Baseline status: compiled successfully in GitHub Actions; the new HTTPS-uplink revision requires fresh CI and hardware validation.** This package builds for the original single-micro-USB ILI9341/XPT2046 CYD with 4 MB flash and no PSRAM. Some dual-USB CYDs use a different LCD controller and require their own profile. This is **not** the GOOUUU ESP32-S3 firmware.

## Features

- 320x240 landscape touchscreen dashboard (ILI9341 on HSPI, backlight GPIO21).
- XPT2046 touch on its own VSPI bus (CLK25, MOSI32, MISO39, CS33, IRQ36).
- WPA2 device-local first-boot provisioning AP, `SKYNET-CYD`. Device screen supplies a randomized setup password. Visit `http://192.168.4.1` while connected.
- Configure authorized Wi-Fi, S3 private IPv4 and HTTP port, read-only RuView JSON path, and optional JPEG snapshot path.
- Poll `/api/status` on the S3. RuView defaults to `/api/ruview` but is explicitly **UNVERIFIED** until it actually responds. A 200 JSON response verifies endpoint availability, not live CSI sensing.
- Camera tab can fetch one ordinary JPEG snapshot (max 64 KiB, content-length required) from the separately configured S3 path. It does not support MJPEG, RTSP or WebRTC.
- No GitHub token, no production deployment, and no CSI signal analysis on the original ESP32. An **optional signed HTTPS heartbeat uplink** to a separately deployed gateway is now implemented; automatic live ingestion is **not verified** without gateway receipts.

## Build

```bash
python3 -m pip install "platformio>=6.1,<7" "esptool>=4.7,<5"
pio run -d pocket/firmware -e esp32-2432S028R
```

**Verified CI evidence:** [14 November 2026, GitHub Actions CYD build #2](https://github.com/BlockChain-BailBonds/SkyNet/actions/runs/43585114254) completed successfully for commit `5f80c3ef4265e68740bbd1ac4bba4c8384aeba7b`. PlatformIO reported **883,673 B** of program flash (42.1% of 2 MB application partition) and **50,872 B** of static RAM (15.5% of 320 KB). The uploaded [artifact `skynet-pocket-cyd-esp32-n4`](https://github.com/BlockChain-BailBonds/SkyNet/actions/runs/43585114254/artifacts/14110680177) includes `skynet-cyd-esp32-4mb-merged.bin`, the bootloader, partitions, app binary and `SHA256SUMS.txt`. The CI artifact expires 30 days after 14 November 2026. A completed build is **compile/packaging evidence only**; it cannot demonstrate touch registration, Wi-Fi or actual camera/CSI operation.

**Note:** Firmware changes remain in [draft PR #12](https://github.com/BlockChain-BailBonds/SkyNet/pull/12), not merged into `main`. The existing GOOUUU S3 firmware is untouched.

## Flash after verifying chip, backing up flash and reviewing the image

**Do not flash the GOOUUU S3.** Connect only the original 4 MB CYD to USB and identify its actual port:

```bash
python3 -m esptool --chip esp32 --port /dev/ttyUSB0 flash_id
python3 -m esptool --chip esp32 --port /dev/ttyUSB0 read_flash 0x0 0x400000 original-cyd-backup.bin
sha256sum original-cyd-backup.bin
```

Download the `skynet-pocket-cyd-esp32-n4` Actions artifact, extract it and verify `sha256sum -c SHA256SUMS.txt`. Flash the **merged image** at offset zero:

```bash
python3 -m esptool --chip esp32 --port /dev/ttyUSB0 --baud 115200 write_flash 0x0 skynet-cyd-esp32-4mb-merged.bin
```

Or use `pio run -d pocket/firmware -t upload --upload-port /dev/ttyUSB0` after building locally. Reboot and monitor `115200` baud.

## Setup and acceptance

1. Confirm LCD boot, rotation, four corners and all three lower touch buttons. Touch coordinate mapping is a reference baseline, not device-calibrated evidence.
2. Connect a phone to the **temporary** `SKYNET-CYD` WPA2 AP using the on-screen key. The local setup page is intentionally HTTP over this isolated, password-protected AP; provisioning credentials persist in ESP32 NVS for reconnection and are not placed in GitHub, the public frontend, or logs. NVS is not assured to be encrypted unless flash encryption is provisioned.
3. Enter your authorized 2.4 GHz Wi-Fi network and the S3's **actual currently reachable RFC1918 IPv4 address**. The S3 status API must support JSON at `/api/status`.
4. Enter a RuView JSON path only if the S3 firmware has it. A `/api/ruview` 404 means unsupported path, **not** verified RuView sensing.
5. Enter an actual S3 camera JPEG snapshot path only if it provides a bounded `image/jpeg` response with Content-Length. No path is presumed to exist; `/capture` is only an example.
6. For optional Pocket-to-Main HTTPS uplink, follow [the complete gateway deployment and device-provisioning runbook](../../docs/pocket-uplink.md). Supply an enrolled device ID, unique 32-byte HMAC key and trusted HTTPS CA PEM via the local setup form. HTTPS heartbeat transport does **not** require WSS.
7. Inspect read-only backend receipts, raw board serial traces and real sensor output before classifying anything as physically verified. A green CI or gateway response is not proof of RuView CSI or camera capture provenance.

Touch **SETUP** then the upper screen area to enter the provisioning AP again. In setup mode, the device stops normal S3 polling. The S3 firmware remains untouched.

## HTTPS heartbeat acceptance gate

The CYD sends bounded JSON status summaries to `POST /api/pocket/heartbeat` every 60 seconds **only after** configuring the public gateway DNS, port, device identity, per-device HMAC secret and trusted TLS CA certificate. Firmware requires NTP time; it signs method, route, device ID, timestamp, nonce and SHA-256 body hash. A trusted 201 acknowledgment with receipt ID is shown as `ACK RECEIVED`. Failed TLS, clock, authentication or transport do not silently downgrade. See [gateway code](../../pocket/gateway.py) and [uplink runbook](../../docs/pocket-uplink.md).

The gateway process is not deployed by this firmware build. Registration/consent, a hosted HTTPS proxy, operator status authentication and direct device telemetry receipt are prerequisites to marking SkyNet Main uplink VERIFIED. Keep S3 firmware unchanged and retain CYD backup.
