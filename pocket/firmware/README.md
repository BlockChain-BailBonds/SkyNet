# SkyNet Pocket firmware — CYD ESP32-2432S028R (N4)

**Status: source integration candidate; actual hardware operation UNVERIFIED.** This package builds for the original single-micro-USB ILI9341/XPT2046 CYD with 4 MB flash and no PSRAM. Some dual-USB CYDs use a different LCD controller and require their own profile. This is **not** the GOOUUU ESP32-S3 firmware.

## Features

- 320x240 landscape touchscreen dashboard (ILI9341 on HSPI, backlight GPIO21).
- XPT2046 touch on its own VSPI bus (CLK25, MOSI32, MISO39, CS33, IRQ36).
- WPA2 device-local first-boot provisioning AP, `SKYNET-CYD`. Device screen supplies a randomized setup password. Visit `http://192.168.4.1` while connected.
- Configure authorized Wi-Fi, S3 private IPv4 and HTTP port, read-only RuView JSON path, and optional JPEG snapshot path.
- Poll `/api/status` on the S3. RuView defaults to `/api/ruview` but is explicitly **UNVERIFIED** until it actually responds. A 200 JSON response verifies endpoint availability, not live CSI sensing.
- Camera tab can fetch one ordinary JPEG snapshot (max 64 KiB, content-length required) from the separately configured S3 path. It does not support MJPEG, RTSP or WebRTC.
- No Github token, no production deployment, no CSI signal analysis on the original ESP32, and no automatic public uplink.

## Build

```bash
python3 -m pip install "platformio>=6.1,<7" "esptool>=4.7,<5"
pio run -d pocket/firmware -e esp32-2432S028R
```

The pull request also runs `.github/workflows/cyd-pocket.yml`, uploading the exact 4 MB image and checksums. A completed CI build is **compile evidence only**; it cannot demonstrate touch registration, Wi-Fi or actual camera/CSI operation.

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
6. Inspect read-only backend logs and sensor output before classifying anything as verified. For production SkyNet Main reporting, the S3/back-end needs separately authenticated HTTPS/WSS ingestion, consent and provenance.

Touch **SETUP** then the upper screen area to enter the provisioning AP again. In setup mode, the device stops normal S3 polling. The S3 firmware remains untouched.
